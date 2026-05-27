"""Regression tests for `create_kitchen_order` idempotency_key support.

Task #28 / F8Z.2 spec step D: `POST /api/fnb/kitchen-order` must honor
a client-supplied `idempotency_key` so that an accidental double-tap on
a flaky tablet does not produce two kitchen tickets (and therefore two
prints in the kitchen).

Contract pinned here:

  * First call with a key inserts a new row, persists the key on the
    document and returns the order.
  * A replay with the same (tenant_id, idempotency_key) pair returns the
    original order with `idempotent_replay=True` — NOT a new row.
  * A concurrent racer that loses on the unique partial index
    (DuplicateKeyError) re-reads and returns the winning row instead of
    bubbling the error.
  * Keys are scoped per-tenant: tenant-B replaying tenant-A's key does
    not see tenant-A's ticket.
  * An oversize key (>128 chars) is rejected with 400.
  * If the unique partial index cannot be confirmed, keyed writes fail
    closed with 503 rather than fall back to an unsafe find→insert.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from domains.pms.pos_fnb_router import kitchen


class _FakeKitchenColl:
    def __init__(self):
        self.docs: list[dict] = []
        self.insert_calls = 0
        self.raise_dup_on_insert = False

    async def find_one(self, flt, _proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                return {k: v for k, v in d.items() if k != "_id"}
        return None

    async def insert_one(self, doc):
        self.insert_calls += 1
        if self.raise_dup_on_insert:
            return self._raise_dup()
        # Enforce the unique (tenant_id, idempotency_key) partial index in-memory.
        key = doc.get("idempotency_key")
        if key is not None:
            for d in self.docs:
                if (
                    d.get("tenant_id") == doc.get("tenant_id")
                    and d.get("idempotency_key") == key
                ):
                    self._raise_dup()
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id="x")

    def _raise_dup(self):
        raise DuplicateKeyError("duplicate idempotency_key")


class _FakeDB:
    def __init__(self):
        self.kitchen_orders = _FakeKitchenColl()


@pytest.fixture
def fake_user():
    return SimpleNamespace(
        id="u1", tenant_id="tenant-A", name="Server One"
    )


@pytest.fixture
def fake_user_b():
    return SimpleNamespace(
        id="u2", tenant_id="tenant-B", name="Server Two"
    )


@pytest.fixture(autouse=True)
def _patch_kitchen(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr(kitchen, "db", fake_db)

    async def _ok_index():
        return True
    monkeypatch.setattr(kitchen, "_ensure_kitchen_idemp_index", _ok_index)

    async def _noop_broadcast(_tenant_id):
        return None
    monkeypatch.setattr(kitchen, "_broadcast_kitchen_queue", _noop_broadcast)

    counter = {"n": 0}

    async def _next_num(_tenant_id):
        counter["n"] += 1
        return f"K-{counter['n']}"
    monkeypatch.setattr(kitchen, "_next_kitchen_order_number", _next_num)

    return fake_db


async def _create(user, key=None, item_name="burger"):
    payload = {
        "items": [{"name": item_name, "quantity": 1}],
        "table_number": "T1",
    }
    if key is not None:
        payload["idempotency_key"] = key
    return await kitchen.create_kitchen_order(
        order_data=payload, current_user=user, _perm=None,
    )


async def test_replay_with_same_key_returns_same_ticket(_patch_kitchen, fake_user):
    r1 = await _create(fake_user, key="IDEM-1")
    r2 = await _create(fake_user, key="IDEM-1")
    assert r1["order"]["id"] == r2["order"]["id"]
    assert r2.get("idempotent_replay") is True
    assert _patch_kitchen.kitchen_orders.insert_calls == 1
    assert len(_patch_kitchen.kitchen_orders.docs) == 1


async def test_no_key_always_creates_new(_patch_kitchen, fake_user):
    r1 = await _create(fake_user, key=None)
    r2 = await _create(fake_user, key=None)
    assert r1["order"]["id"] != r2["order"]["id"]
    assert _patch_kitchen.kitchen_orders.insert_calls == 2


async def test_blank_key_is_treated_as_no_key(_patch_kitchen, fake_user):
    r1 = await _create(fake_user, key="   ")
    r2 = await _create(fake_user, key="")
    assert r1["order"]["id"] != r2["order"]["id"]
    # Stored docs must not carry an empty-string key (would clash under the
    # partial unique index across unrelated rows).
    for d in _patch_kitchen.kitchen_orders.docs:
        assert "idempotency_key" not in d


async def test_key_is_tenant_scoped(_patch_kitchen, fake_user, fake_user_b):
    r_a = await _create(fake_user, key="SAME")
    r_b = await _create(fake_user_b, key="SAME")
    assert r_a["order"]["id"] != r_b["order"]["id"]
    assert r_a["order"]["tenant_id"] == "tenant-A"
    assert r_b["order"]["tenant_id"] == "tenant-B"


async def test_oversize_key_rejected(_patch_kitchen, fake_user):
    with pytest.raises(HTTPException) as exc:
        await _create(fake_user, key="x" * 129)
    assert exc.value.status_code == 400


async def test_index_unavailable_fails_closed(monkeypatch, fake_user, _patch_kitchen):
    async def _no_index():
        return False
    monkeypatch.setattr(kitchen, "_ensure_kitchen_idemp_index", _no_index)
    with pytest.raises(HTTPException) as exc:
        await _create(fake_user, key="IDEM-X")
    assert exc.value.status_code == 503
    # No row should have been inserted on the unsafe path.
    assert _patch_kitchen.kitchen_orders.insert_calls == 0


async def test_duplicate_key_race_returns_winner(_patch_kitchen, fake_user):
    """Simulate the racer-losing case: another worker inserted the row
    between our find_one and our insert_one. The handler must re-read
    and return the winner instead of bubbling DuplicateKeyError."""
    # Seed the "winning" row directly so a re-read finds it.
    winning = {
        "id": "winner-id",
        "tenant_id": "tenant-A",
        "idempotency_key": "RACE",
        "order_number": "K-0",
        "items": [{"name": "burger", "quantity": 1}],
    }
    _patch_kitchen.kitchen_orders.docs.append(dict(winning))
    # Force the next insert to raise as if the unique index fired.
    _patch_kitchen.kitchen_orders.raise_dup_on_insert = True

    # Bypass the find_one short-circuit by patching it to miss once.
    real_find = _patch_kitchen.kitchen_orders.find_one
    calls = {"n": 0}

    async def _find(flt, proj=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # pretend we didn't see the winner pre-insert
        return await real_find(flt, proj)

    _patch_kitchen.kitchen_orders.find_one = _find  # type: ignore[assignment]

    result = await _create(fake_user, key="RACE")
    assert result["order"]["id"] == "winner-id"
    assert result.get("idempotent_replay") is True
