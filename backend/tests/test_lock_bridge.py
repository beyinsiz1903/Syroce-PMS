"""Targeted tests for the lock-bridge command queue + connector auth.

Pinned contract:
  * enqueue_lock_command is idempotent per (tenant, dedup_key) — a retried
    lifecycle event never produces a duplicate physical-card action.
  * claim_commands is a per-document compare-and-set (pending->claimed): a
    command is handed to exactly one poll, never double-delivered.
  * ack_command is tenant-scoped: success -> done; failure -> re-queued for
    retry; foreign-tenant / already-terminal -> rejected.
  * Connector auth is fail-closed: unknown / inactive / empty key -> no tenant,
    and the tenant is resolved from the stored record, never from client input.
  * The connector wire view carries no guest PII.

Uses an in-memory fake DB (no live Mongo), mirroring tests/test_door_reader.py.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from domains.pms.lock_bridge import service as svc
from domains.pms.lock_bridge import connector_router as cr


class DuplicateKeyError(Exception):
    """Stand-in for pymongo's DuplicateKeyError (matched by class name)."""


def _match(doc: dict, flt: dict) -> bool:
    for k, v in flt.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in v):
                return False
            continue
        if isinstance(v, dict):
            if "$in" in v and doc.get(k) not in v["$in"]:
                return False
            if "$nin" in v and doc.get(k) in v["$nin"]:
                return False
            if "$ne" in v and doc.get(k) == v["$ne"]:
                return False
            if "$lt" in v:
                cur = doc.get(k)
                if cur is None or not (cur < v["$lt"]):
                    return False
        elif doc.get(k) != v:
            return False
    return True


def _strip(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


class _Coll:
    def __init__(self):
        self.docs: list[dict] = []
        self._unique: list[list[str]] = []

    async def create_index(self, keys, unique=False, name=None):
        if unique:
            self._unique.append([k for k, _ in keys])

    async def insert_one(self, doc):
        for fields in self._unique:
            for d in self.docs:
                if all(d.get(f) == doc.get(f) for f in fields):
                    raise DuplicateKeyError(name="dup")
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id="x")

    async def find_one(self, flt, projection=None, sort=None):
        candidates = [d for d in self.docs if _match(d, flt)]
        if sort:
            for field, direction in reversed(sort):
                candidates.sort(key=lambda d: d.get(field), reverse=direction < 0)
        return _strip(candidates[0]) if candidates else None

    async def update_one(self, flt, update):
        for d in self.docs:
            if _match(d, flt):
                if "$set" in update:
                    d.update(update["$set"])
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        d[k] = (d.get(k) or 0) + v
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


class _FakeDB:
    def __init__(self):
        self._colls: dict[str, _Coll] = {}

    def __getattr__(self, name):
        colls = self.__dict__.setdefault("_colls", {})
        if name not in colls:
            colls[name] = _Coll()
        return colls[name]


TENANT = "tenant-A"
OTHER = "tenant-B"


@pytest.fixture()
async def fake():
    db = _FakeDB()
    await svc.ensure_lock_bridge_indexes(db)
    return db


# ---------------------------------------------------------------------------
# Idempotent enqueue
# ---------------------------------------------------------------------------
async def test_enqueue_is_idempotent(fake):
    first = await svc.enqueue_lock_command(
        fake, tenant_id=TENANT, command=svc.CMD_ENCODE, keycard_id="kc1", room_number="101"
    )
    second = await svc.enqueue_lock_command(
        fake, tenant_id=TENANT, command=svc.CMD_ENCODE, keycard_id="kc1", room_number="101"
    )
    assert first is True
    assert second is False
    assert len(fake.lock_commands.docs) == 1


async def test_encode_and_revoke_are_distinct(fake):
    await svc.enqueue_lock_command(fake, tenant_id=TENANT, command=svc.CMD_ENCODE, keycard_id="kc1")
    await svc.enqueue_lock_command(fake, tenant_id=TENANT, command=svc.CMD_REVOKE, keycard_id="kc1")
    assert len(fake.lock_commands.docs) == 2


async def test_enqueue_rejects_unknown_command(fake):
    ok = await svc.enqueue_lock_command(fake, tenant_id=TENANT, command="explode", keycard_id="kc1")
    assert ok is False
    assert len(fake.lock_commands.docs) == 0


# ---------------------------------------------------------------------------
# Claim (compare-and-set)
# ---------------------------------------------------------------------------
async def test_claim_marks_claimed_and_not_redelivered(fake):
    await svc.enqueue_lock_command(fake, tenant_id=TENANT, command=svc.CMD_ENCODE, keycard_id="kc1")
    first = await svc.claim_commands(fake, tenant_id=TENANT)
    second = await svc.claim_commands(fake, tenant_id=TENANT)
    assert len(first) == 1
    assert second == []
    assert fake.lock_commands.docs[0]["status"] == "claimed"


async def test_claim_is_tenant_scoped(fake):
    await svc.enqueue_lock_command(fake, tenant_id=TENANT, command=svc.CMD_ENCODE, keycard_id="kc1")
    assert await svc.claim_commands(fake, tenant_id=OTHER) == []


async def test_claim_respects_limit(fake):
    for i in range(5):
        await svc.enqueue_lock_command(fake, tenant_id=TENANT, command=svc.CMD_ENCODE, keycard_id=f"kc{i}")
    claimed = await svc.claim_commands(fake, tenant_id=TENANT, limit=2)
    assert len(claimed) == 2


async def test_claim_view_has_no_pii(fake):
    await svc.enqueue_lock_command(
        fake, tenant_id=TENANT, command=svc.CMD_ENCODE, keycard_id="kc1",
        room_number="101", card_number="RFID-101", booking_id="B1",
    )
    [cmd] = await svc.claim_commands(fake, tenant_id=TENANT)
    for forbidden in ("guest_name", "guest_id", "email", "tenant_id", "claimed_by"):
        assert forbidden not in cmd
    assert cmd["command"] == svc.CMD_ENCODE


async def test_fresh_claim_not_reclaimed_within_lease(fake):
    await svc.enqueue_lock_command(fake, tenant_id=TENANT, command=svc.CMD_ENCODE, keycard_id="kc1")
    await svc.claim_commands(fake, tenant_id=TENANT, connector_id="conn-A", lease_seconds=120)
    # A second poll within the lease window must NOT reclaim the held command.
    again = await svc.claim_commands(fake, tenant_id=TENANT, connector_id="conn-B", lease_seconds=120)
    assert again == []


async def test_stale_claim_is_reclaimed_after_lease(fake):
    await svc.enqueue_lock_command(fake, tenant_id=TENANT, command=svc.CMD_ENCODE, keycard_id="kc1")
    await svc.claim_commands(fake, tenant_id=TENANT, connector_id="conn-A")
    # Connector A crashed before ack; with a zero-ish lease the command becomes
    # reclaimable so the physical card is not stuck forever.
    again = await svc.claim_commands(fake, tenant_id=TENANT, connector_id="conn-B", lease_seconds=0)
    assert len(again) == 1
    assert fake.lock_commands.docs[0]["claimed_by"] == "conn-B"


async def test_ack_rejected_after_lease_reclaim(fake):
    await svc.enqueue_lock_command(fake, tenant_id=TENANT, command=svc.CMD_ENCODE, keycard_id="kc1")
    [cmd] = await svc.claim_commands(fake, tenant_id=TENANT, connector_id="conn-A")
    # Lease expires, connector B reclaims it.
    await svc.claim_commands(fake, tenant_id=TENANT, connector_id="conn-B", lease_seconds=0)
    # The original connector's late ack must be rejected (it no longer holds it).
    stale = await svc.ack_command(
        fake, tenant_id=TENANT, command_id=cmd["id"], success=True, connector_id="conn-A"
    )
    assert stale is False
    # The current holder can still ack.
    ok = await svc.ack_command(
        fake, tenant_id=TENANT, command_id=cmd["id"], success=True, connector_id="conn-B"
    )
    assert ok is True


# ---------------------------------------------------------------------------
# Ack
# ---------------------------------------------------------------------------
async def test_ack_success_marks_done(fake):
    await svc.enqueue_lock_command(fake, tenant_id=TENANT, command=svc.CMD_ENCODE, keycard_id="kc1")
    [cmd] = await svc.claim_commands(fake, tenant_id=TENANT)
    ok = await svc.ack_command(fake, tenant_id=TENANT, command_id=cmd["id"], success=True)
    assert ok is True
    assert fake.lock_commands.docs[0]["status"] == "done"


async def test_ack_failure_requeues_for_retry(fake):
    await svc.enqueue_lock_command(fake, tenant_id=TENANT, command=svc.CMD_ENCODE, keycard_id="kc1")
    [cmd] = await svc.claim_commands(fake, tenant_id=TENANT)
    ok = await svc.ack_command(fake, tenant_id=TENANT, command_id=cmd["id"], success=False, detail="dll error")
    assert ok is True
    assert fake.lock_commands.docs[0]["status"] == "pending"
    # Re-claimable after a failed ack.
    again = await svc.claim_commands(fake, tenant_id=TENANT)
    assert len(again) == 1


async def test_ack_foreign_tenant_rejected(fake):
    await svc.enqueue_lock_command(fake, tenant_id=TENANT, command=svc.CMD_ENCODE, keycard_id="kc1")
    [cmd] = await svc.claim_commands(fake, tenant_id=TENANT)
    ok = await svc.ack_command(fake, tenant_id=OTHER, command_id=cmd["id"], success=True)
    assert ok is False


async def test_ack_already_terminal_rejected(fake):
    await svc.enqueue_lock_command(fake, tenant_id=TENANT, command=svc.CMD_ENCODE, keycard_id="kc1")
    [cmd] = await svc.claim_commands(fake, tenant_id=TENANT)
    await svc.ack_command(fake, tenant_id=TENANT, command_id=cmd["id"], success=True)
    second = await svc.ack_command(fake, tenant_id=TENANT, command_id=cmd["id"], success=True)
    assert second is False


# ---------------------------------------------------------------------------
# Connector auth (fail-closed)
# ---------------------------------------------------------------------------
async def test_register_and_authenticate(fake):
    key = await svc.register_connector(fake, tenant_id=TENANT, name="Resepsiyon PC")
    assert isinstance(key, str) and len(key) > 20
    assert await svc.authenticate_connector(fake, key) == TENANT


async def test_authenticate_wrong_key_is_none(fake):
    await svc.register_connector(fake, tenant_id=TENANT, name="Resepsiyon PC")
    assert await svc.authenticate_connector(fake, "not-the-key") is None


async def test_authenticate_empty_key_is_none(fake):
    assert await svc.authenticate_connector(fake, None) is None
    assert await svc.authenticate_connector(fake, "") is None


async def test_authenticate_inactive_connector_is_none(fake):
    key = await svc.register_connector(fake, tenant_id=TENANT, name="Resepsiyon PC")
    fake.lock_bridge_connectors.docs[0]["active"] = False
    assert await svc.authenticate_connector(fake, key) is None


async def test_plaintext_key_never_stored(fake):
    key = await svc.register_connector(fake, tenant_id=TENANT, name="Resepsiyon PC")
    stored = fake.lock_bridge_connectors.docs[0]
    assert key not in stored.values()
    assert "key_hash" in stored


# ---------------------------------------------------------------------------
# Connector router dependency (fail-closed)
# ---------------------------------------------------------------------------
async def test_router_dependency_rejects_unknown_key(fake, monkeypatch):
    monkeypatch.setattr(cr, "db", fake)
    with pytest.raises(cr.HTTPException) as exc:
        await cr._require_connector(x_lock_bridge_key="bad")
    assert exc.value.status_code == 401


async def test_router_dependency_resolves_tenant(fake, monkeypatch):
    monkeypatch.setattr(cr, "db", fake)
    key = await svc.register_connector(fake, tenant_id=TENANT, name="Resepsiyon PC")
    resolved = await cr._require_connector(x_lock_bridge_key=key)
    assert resolved["tenant_id"] == TENANT
    assert resolved["connector_id"]
