"""Targeted tests for Spa & Golf → folio posting idempotency (Modül 3).

Pinned contract:
  * Completing an appointment/booking that is charge-to-room posts exactly
    ONE folio_postings row, deduped on (tenant_id, dedup_key). A second
    "completed" transition or a retry never double-charges and never
    re-publishes the Xchange POSTING_CHARGE event.
  * Status transition is an atomic CAS: only the request that flips the
    status from the observed value runs the side effects (the loser returns
    idempotent without re-posting).
  * RBAC unchanged: "completed" is finance-impacting and requires a finance
    grade role; a spa-ops-only role is rejected with 403 and no charge.
  * Terminal-state guard preserved: completing an already-completed record
    is a 409, never a second charge.

In-memory fake-DB approach mirrors tests/test_minibar_consume.py so these
run without a live Mongo. The fake models the partial-unique index by only
enforcing the compound key when every key value is a non-null string.
"""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from domains.golf import router as golf
from domains.spa import router as spa
from models.enums import UserRole

TENANT = "tenant-A"


# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------
def _match(doc: dict, flt: dict) -> bool:
    for k, v in flt.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif isinstance(v, dict) and "$ne" in v:
            if doc.get(k) == v["$ne"]:
                return False
        elif isinstance(v, dict):
            return False
        elif doc.get(k) != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            d = next(self._it)
        except StopIteration:
            raise StopAsyncIteration
        return {kk: vv for kk, vv in d.items() if kk != "_id"}


class _Coll:
    def __init__(self, unique_keys=None):
        self.docs: list[dict] = []
        self.insert_calls = 0
        self.unique_keys = unique_keys

    def find(self, flt=None, proj=None, session=None):
        flt = flt or {}
        return _Cursor([d for d in self.docs if _match(d, flt)])

    async def find_one(self, flt, proj=None, sort=None, session=None):
        for d in self.docs:
            if _match(d, flt):
                return {kk: vv for kk, vv in d.items() if kk != "_id"}
        return None

    async def insert_one(self, doc, session=None):
        if self.unique_keys:
            # Model the partial-unique index: only enforce when EVERY key
            # value is a non-null string (matches partialFilter $type string).
            vals = [doc.get(k) for k in self.unique_keys]
            if all(isinstance(v, str) for v in vals):
                for d in self.docs:
                    if all(d.get(k) == doc.get(k) for k in self.unique_keys):
                        raise DuplicateKeyError("duplicate compound key")
        self.insert_calls += 1
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id", "x"))

    async def update_one(self, flt, update, upsert=False, session=None):
        for d in self.docs:
            if _match(d, flt):
                if "$set" in update:
                    d.update(update["$set"])
                if "$unset" in update:
                    for k in update["$unset"]:
                        d.pop(k, None)
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, flt, session=None):
        for i, d in enumerate(self.docs):
            if _match(d, flt):
                self.docs.pop(i)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    async def create_index(self, *a, **k):
        return "idx"


class _FakeDB:
    def __init__(self):
        self.spa_appointments = _Coll()
        self.golf_tee_bookings = _Coll()
        self.folio_postings = _Coll(unique_keys=("tenant_id", "dedup_key"))

    def __getitem__(self, name):
        return getattr(self, name)


def _user(role=UserRole.FRONT_DESK, *, tenant=TENANT):
    return SimpleNamespace(
        id="u1", user_id="u1", tenant_id=tenant, role=role,
        is_super_admin=False, username="staff", name="Staff",
        email="s@example.com", roles=[],
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = _FakeDB()

    monkeypatch.setattr(spa, "get_system_db", lambda: fake)
    monkeypatch.setattr(golf, "get_system_db", lambda: fake)

    # ensure_compound_unique is imported lazily inside _post_to_folio; patch
    # it on its home module so both routers pick up the noop.
    from shared_kernel import pos_idem

    async def _noop_ensure(*a, **k):
        return None

    monkeypatch.setattr(pos_idem, "ensure_compound_unique", _noop_ensure)

    # Stub the Xchange bus (lazily imported) so we can count publishes and
    # avoid real I/O.
    publishes: list[dict] = []

    bus_mod = types.ModuleType("integrations.xchange.bus")

    class _Bus:
        async def publish(self, **kwargs):
            publishes.append(kwargs)

    bus_mod.bus = _Bus()
    schemas_mod = types.ModuleType("integrations.xchange.schemas")
    schemas_mod.MessageType = SimpleNamespace(POSTING_CHARGE="POSTING_CHARGE")
    monkeypatch.setitem(sys.modules, "integrations.xchange.bus", bus_mod)
    monkeypatch.setitem(sys.modules, "integrations.xchange.schemas", schemas_mod)

    fake.publishes = publishes
    return fake


# ---------------------------------------------------------------------------
# Spa
# ---------------------------------------------------------------------------
def _seed_appt(fake, *, status="scheduled", charge=True, res="RES1", aid="A1"):
    fake.spa_appointments.docs.append({
        "id": aid, "tenant_id": TENANT, "status": status,
        "service_name": "İsveç Masajı", "price": 1500.0, "currency": "TRY",
        "charge_to_room": charge, "reservation_id": res,
    })


async def test_spa_post_to_folio_idempotent_direct(_patch):
    appt = {"id": "A1", "tenant_id": TENANT, "service_name": "X",
            "price": 1500.0, "currency": "TRY", "reservation_id": "RES1"}
    await spa._post_to_folio(TENANT, appt)
    await spa._post_to_folio(TENANT, appt)  # retry / concurrent second call
    assert _patch.folio_postings.insert_calls == 1
    assert len(_patch.folio_postings.docs) == 1
    # Xchange published exactly once (no duplicate event on the dedup no-op).
    assert len(_patch.publishes) == 1
    assert _patch.folio_postings.docs[0]["dedup_key"] == "spa_module:A1"


async def test_spa_complete_posts_single_charge(_patch):
    _seed_appt(_patch, status="scheduled")
    res = await spa.change_status(
        "A1", spa.StatusUpdate(status="completed"),
        current_user=_user(), _perm=None,
    )
    assert res["status"] == "completed"
    assert _patch.folio_postings.insert_calls == 1
    assert _patch.spa_appointments.docs[0]["status"] == "completed"


async def test_spa_complete_terminal_guard_no_double_charge(_patch):
    _seed_appt(_patch, status="completed")
    with pytest.raises(HTTPException) as exc:
        await spa.change_status(
            "A1", spa.StatusUpdate(status="completed"),
            current_user=_user(), _perm=None,
        )
    assert exc.value.status_code == 409
    assert _patch.folio_postings.insert_calls == 0


async def test_spa_complete_rbac_denies_non_finance(_patch):
    _seed_appt(_patch, status="scheduled")
    with pytest.raises(HTTPException) as exc:
        await spa.change_status(
            "A1", spa.StatusUpdate(status="completed"),
            current_user=_user(role=UserRole.STAFF), _perm=None,
        )
    assert exc.value.status_code == 403
    assert _patch.folio_postings.insert_calls == 0


async def test_spa_complete_cas_loser_is_idempotent(_patch):
    """If the row already moved to completed under us (CAS filter misses),
    the request returns idempotent without a second charge."""
    _seed_appt(_patch, status="scheduled")

    real_update = _patch.spa_appointments.update_one
    calls = {"n": 0}

    async def _racy_update(flt, update, **k):
        # First CAS attempt: simulate a concurrent winner by flipping the
        # stored status out from under the filter, so modified_count == 0.
        if calls["n"] == 0 and flt.get("status") == "scheduled":
            calls["n"] += 1
            _patch.spa_appointments.docs[0]["status"] = "completed"
            return SimpleNamespace(matched_count=0, modified_count=0)
        return await real_update(flt, update, **k)

    _patch.spa_appointments.update_one = _racy_update

    res = await spa.change_status(
        "A1", spa.StatusUpdate(status="completed"),
        current_user=_user(), _perm=None,
    )
    assert res.get("idempotent") is True
    assert res["status"] == "completed"


async def test_spa_complete_post_failure_reverts_status(_patch):
    """Fail-closed: if the folio post errors after the CAS win, the completion
    is rolled back so no completed-without-charge record can stand."""
    _seed_appt(_patch, status="scheduled")

    async def _boom(doc, session=None):
        raise RuntimeError("folio db down")

    _patch.folio_postings.insert_one = _boom

    with pytest.raises(RuntimeError):
        await spa.change_status(
            "A1", spa.StatusUpdate(status="completed"),
            current_user=_user(), _perm=None,
        )
    appt = _patch.spa_appointments.docs[0]
    assert appt["status"] == "scheduled"
    assert "completed_at" not in appt


# ---------------------------------------------------------------------------
# Golf
# ---------------------------------------------------------------------------
def _seed_booking(fake, *, status="checked_in", charge=True, res="RES1", bid="B1"):
    fake.golf_tee_bookings.docs.append({
        "id": bid, "tenant_id": TENANT, "status": status,
        "course_name": "Championship", "party_size": 2, "price": 3600.0,
        "currency": "TRY", "charge_to_room": charge, "reservation_id": res,
    })


async def test_golf_post_to_folio_idempotent_direct(_patch):
    bk = {"id": "B1", "tenant_id": TENANT, "course_name": "C",
          "party_size": 2, "price": 3600.0, "currency": "TRY",
          "reservation_id": "RES1"}
    await golf._post_to_folio(TENANT, bk)
    await golf._post_to_folio(TENANT, bk)
    assert _patch.folio_postings.insert_calls == 1
    assert len(_patch.publishes) == 1
    assert _patch.folio_postings.docs[0]["dedup_key"] == "golf_module:B1"


async def test_golf_complete_posts_single_charge(_patch):
    _seed_booking(_patch, status="checked_in")
    res = await golf.change_booking_status(
        "B1", golf.GolfStatusUpdate(status="completed"),
        current_user=_user(), _perm=None,
    )
    assert res["status"] == "completed"
    assert _patch.folio_postings.insert_calls == 1
    assert _patch.golf_tee_bookings.docs[0]["status"] == "completed"


async def test_golf_complete_terminal_guard_no_double_charge(_patch):
    _seed_booking(_patch, status="completed")
    with pytest.raises(HTTPException) as exc:
        await golf.change_booking_status(
            "B1", golf.GolfStatusUpdate(status="completed"),
            current_user=_user(), _perm=None,
        )
    assert exc.value.status_code == 409
    assert _patch.folio_postings.insert_calls == 0


async def test_golf_complete_rbac_denies_non_finance(_patch):
    _seed_booking(_patch, status="checked_in")
    with pytest.raises(HTTPException) as exc:
        await golf.change_booking_status(
            "B1", golf.GolfStatusUpdate(status="completed"),
            current_user=_user(role=UserRole.STAFF), _perm=None,
        )
    assert exc.value.status_code == 403
    assert _patch.folio_postings.insert_calls == 0


async def test_golf_complete_post_failure_reverts_status(_patch):
    """Fail-closed: golf completion rolls back if the folio post errors."""
    _seed_booking(_patch, status="checked_in")

    async def _boom(doc, session=None):
        raise RuntimeError("folio db down")

    _patch.folio_postings.insert_one = _boom

    with pytest.raises(RuntimeError):
        await golf.change_booking_status(
            "B1", golf.GolfStatusUpdate(status="completed"),
            current_user=_user(), _perm=None,
        )
    bk = _patch.golf_tee_bookings.docs[0]
    assert bk["status"] == "checked_in"
    assert "completed_at" not in bk


async def test_folio_postings_partial_index_ignores_no_dedup_rows(_patch):
    """Postings without a dedup_key (e.g. mice_module) are NOT subject to the
    compound-unique guard — two such rows coexist."""
    await _patch.folio_postings.insert_one(
        {"id": "m1", "tenant_id": TENANT, "source": "mice_module",
         "reference": "E1"})
    await _patch.folio_postings.insert_one(
        {"id": "m2", "tenant_id": TENANT, "source": "mice_module",
         "reference": "E1"})
    assert _patch.folio_postings.insert_calls == 2
