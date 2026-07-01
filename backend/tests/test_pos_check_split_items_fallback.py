"""Regression: `split_check` must read order line-items even for legacy
transactions that did not snapshot `order_items` into the txn doc.

CI 2026-05-25 (98-pos-deep-lifecycle "D)") failed because the v2 close
handler wrote a txn doc with no `order_items` field. `split_check` fell
back to `items=[]`, so every index in `split_details` was out-of-range
and the handler 400'd with "no valid item indices".

Two-part fix:
  1) v2 close now snapshots `order_items` into the txn doc.
  2) split_check has a legacy fallback that fetches `order_items` from
     pos_orders via `order_id` (tenant-scoped).

These tests pin behavior (2) and the happy path.
"""
from types import SimpleNamespace

import pytest

from domains.pms.pos_fnb_router import pos_core


class _FakeColl:
    def __init__(self, doc=None):
        self._doc = doc
        self.last_filter = None
        self.last_projection = None

    async def find_one(self, flt, projection=None):
        self.last_filter = flt
        self.last_projection = projection
        return self._doc

    async def update_one(self, *_a, **_kw):
        return SimpleNamespace(modified_count=1)


class _FakeDB:
    def __init__(self, txn=None, parent_order=None):
        self.pos_transactions = _FakeColl(txn)
        self.pos_orders = _FakeColl(parent_order)


@pytest.fixture
def user():
    return SimpleNamespace(id="u1", tenant_id="t1")


async def test_legacy_txn_without_items_falls_back_to_pos_orders(monkeypatch, user):
    """Legacy txn doc (no order_items) + parent order has items → split_check
    must reach into pos_orders and succeed."""
    txn = {
        "id": "tx1",
        "tenant_id": "t1",
        "order_id": "ord1",
        "total_amount": 100.0,
    }
    # Legacy item shape (`name`/`price`) — still supported via schema-agnostic
    # field resolution for transactions seeded before the v2 close fix.
    parent = {
        "order_items": [
            {"name": "Espresso", "price": 80.0},
            {"name": "Croissant", "price": 60.0},
        ],
    }
    fake_db = _FakeDB(txn=txn, parent_order=parent)
    monkeypatch.setattr(pos_core, "db", fake_db)

    result = await pos_core.split_check(
        transaction_id="tx1",
        split_type="by_item",
        split_count=2,
        split_details={"1": [0], "2": [1]},
        current_user=user,
        _perm=None,
    )

    assert result["success"] is True
    splits = {s["split_number"]: s for s in result["splits"]}
    assert splits[1]["amount"] == 80.0
    assert splits[2]["amount"] == 60.0
    assert fake_db.pos_orders.last_filter == {"id": "ord1", "tenant_id": "t1"}


async def test_legacy_fallback_is_tenant_scoped(monkeypatch, user):
    """Cross-tenant safety: pos_orders fallback fetch MUST include tenant_id."""
    txn = {"id": "tx1", "tenant_id": "t1", "order_id": "ord1", "total_amount": 50.0}
    fake_db = _FakeDB(txn=txn, parent_order=None)
    monkeypatch.setattr(pos_core, "db", fake_db)

    # No parent → items stays empty → handler 400s; what we're asserting is
    # the filter used in the fallback, not the final status.
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        await pos_core.split_check(
            transaction_id="tx1",
            split_type="by_item",
            split_count=2,
            split_details={"1": [0]},
            current_user=user,
            _perm=None,
        )
    assert fake_db.pos_orders.last_filter == {"id": "ord1", "tenant_id": "t1"}


async def test_new_txn_with_embedded_items_skips_fallback(monkeypatch, user):
    """v2 close snapshots `order_items` into txn → split_check must NOT
    issue an unnecessary pos_orders fetch."""
    txn = {
        "id": "tx1",
        "tenant_id": "t1",
        "order_id": "ord1",
        "total_amount": 140.0,
        "order_items": [
            {"name": "A", "price": 80.0},
            {"name": "B", "price": 60.0},
        ],
    }
    fake_db = _FakeDB(txn=txn, parent_order=None)
    monkeypatch.setattr(pos_core, "db", fake_db)

    result = await pos_core.split_check(
        transaction_id="tx1",
        split_type="by_item",
        split_count=2,
        split_details={"1": [0], "2": [1]},
        current_user=user,
        _perm=None,
    )
    assert result["success"] is True
    # No fallback fetch needed
    assert fake_db.pos_orders.last_filter is None


async def test_v2_schema_item_name_unit_price_total_resolved(monkeypatch, user):
    """CRITICAL: v2 close writes items as `{item_name, unit_price, total}`,
    NOT `{name, price}`. split_check must resolve amounts via this real
    shape (CI 2026-05-25 D — without this, by_item splits silently
    returned 0.0 even for valid indices)."""
    txn = {
        "id": "tx1",
        "tenant_id": "t1",
        "order_id": "ord1",
        "total_amount": 220.0,
        "order_items": [
            {"item_id": "i1", "item_name": "Espresso",  "quantity": 2,
             "unit_price": 80.0, "total": 160.0},
            {"item_id": "i2", "item_name": "Croissant", "quantity": 1,
             "unit_price": 60.0, "total": 60.0},
        ],
    }
    fake_db = _FakeDB(txn=txn, parent_order=None)
    monkeypatch.setattr(pos_core, "db", fake_db)

    result = await pos_core.split_check(
        transaction_id="tx1",
        split_type="by_item",
        split_count=2,
        split_details={"1": [0], "2": [1]},
        current_user=user,
        _perm=None,
    )
    assert result["success"] is True
    splits = {s["split_number"]: s for s in result["splits"]}
    assert splits[1]["amount"] == 160.0
    assert splits[1]["items"] == ["Espresso"]
    assert splits[2]["amount"] == 60.0
    assert splits[2]["items"] == ["Croissant"]


async def test_v2_schema_unit_price_quantity_fallback(monkeypatch, user):
    """If `total` is missing, fall back to unit_price * quantity."""
    txn = {
        "id": "tx1",
        "tenant_id": "t1",
        "order_id": "ord1",
        "total_amount": 200.0,
        "order_items": [
            {"item_name": "Burger", "quantity": 2, "unit_price": 50.0},
        ],
    }
    fake_db = _FakeDB(txn=txn, parent_order=None)
    monkeypatch.setattr(pos_core, "db", fake_db)

    result = await pos_core.split_check(
        transaction_id="tx1",
        split_type="by_item",
        split_count=1,
        split_details={"1": [0]},
        current_user=user,
        _perm=None,
    )
    splits = {s["split_number"]: s for s in result["splits"]}
    assert splits[1]["amount"] == 100.0


async def test_update_one_filter_is_tenant_scoped(monkeypatch, user):
    """split_check's terminal `update_one` MUST include tenant_id (same
    bug class as the KDS IDOR fixed earlier in this batch)."""
    txn = {
        "id": "tx1",
        "tenant_id": "t1",
        "total_amount": 100.0,
        "order_items": [{"item_name": "X", "unit_price": 100.0, "quantity": 1, "total": 100.0}],
    }

    class _CapturingTxnColl:
        def __init__(self):
            self.update_filter = None

        async def find_one(self, *_a, **_kw):
            return txn

        async def update_one(self, flt, _upd):
            self.update_filter = flt
            return SimpleNamespace(modified_count=1)

    fake_db = SimpleNamespace(
        pos_transactions=_CapturingTxnColl(),
        pos_orders=_FakeColl(None),
    )
    monkeypatch.setattr(pos_core, "db", fake_db)

    await pos_core.split_check(
        transaction_id="tx1",
        split_type="equal",
        split_count=2,
        split_details=None,
        current_user=user,
        _perm=None,
    )
    assert fake_db.pos_transactions.update_filter == {
        "id": "tx1", "tenant_id": "t1",
    }
