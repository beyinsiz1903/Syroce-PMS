"""Tests for auto-KDS ticket + auto-KOT print on POS order create.

Task #601 T002. When a waiter creates a POS order, the kitchen must learn about
it without any extra step:

  * A kitchen_orders (KDS) ticket is auto-created, carrying the adisyon_number
    and business_date so the line cook sees the same check number.
  * A per-station KOT print job is enqueued (one ticket per kitchen station the
    items route to).
  * Both are idempotent on the order id — a replay (same order) never creates a
    second KDS row or a second print job.
  * An empty order (no items) is a no-op.
"""
from datetime import UTC, datetime

import pytest

from domains.pms.pos_fnb_router import pos_core


class _FakeKitchenColl:
    def __init__(self):
        self.docs: list[dict] = []

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                return {k: v for k, v in d.items() if k != "_id"}
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return None


class _OrderItem:
    def __init__(self, name, qty, category):
        self.item_name = name
        self.quantity = qty
        self.category = category


class _Order:
    def __init__(self, items, oid="order-1"):
        self.id = oid
        self.order_items = items
        self.adisyon_number = 7
        self.business_date = "2026-06-14"
        self.outlet_id = "outletA"
        self.table_number = "12"
        self.booking_id = None
        self.notes = None


@pytest.fixture
def _patch_db(monkeypatch):
    kitchen = _FakeKitchenColl()
    monkeypatch.setattr(pos_core.db, "kitchen_orders", kitchen, raising=False)
    # Stub the kitchen order number + broadcast so the helper is hermetic.
    monkeypatch.setattr(pos_core, "_next_kitchen_order_number", _async_const(101))
    monkeypatch.setattr(pos_core, "_broadcast_kitchen_queue", _async_noop)

    enqueued: list[dict] = []

    async def _fake_enqueue(**kwargs):
        enqueued.append(kwargs)
        return ({"id": "job"}, False)

    import domains.pms.pos_extensions.pos_print_spool as spool
    monkeypatch.setattr(spool, "enqueue_print_job", _fake_enqueue)
    return kitchen, enqueued


def _async_const(value):
    async def _inner(*a, **k):
        return value
    return _inner


async def _async_noop(*a, **k):
    return None


@pytest.mark.asyncio
async def test_auto_kds_and_kot_created(_patch_db):
    kitchen, enqueued = _patch_db
    order = _Order([
        _OrderItem("Kofte", 2, "food"),
        _OrderItem("Cola", 1, "beverage"),
    ])
    await pos_core._auto_kds_and_kot(order, "t1", "Waiter")

    # KDS ticket created, carries the adisyon number + business date.
    assert len(kitchen.docs) == 1
    kds = kitchen.docs[0]
    assert kds["adisyon_number"] == 7
    assert kds["business_date"] == "2026-06-14"
    assert kds["source_pos_order_id"] == "order-1"
    assert kds["idempotency_key"] == "pos-order-1"

    # Two stations (hot_kitchen for food, bar for beverage) -> two KOT jobs.
    stations = sorted(k["printer_id"] for k in enqueued)
    assert stations == ["bar", "hot_kitchen"]
    assert all(k["kind"] == "kitchen" for k in enqueued)


@pytest.mark.asyncio
async def test_replay_does_not_duplicate_kds(_patch_db):
    kitchen, enqueued = _patch_db
    order = _Order([_OrderItem("Kofte", 1, "food")])

    await pos_core._auto_kds_and_kot(order, "t1", "Waiter")
    await pos_core._auto_kds_and_kot(order, "t1", "Waiter")

    # Idempotent on the order id: still exactly one KDS row.
    assert len(kitchen.docs) == 1


@pytest.mark.asyncio
async def test_empty_order_is_noop(_patch_db):
    kitchen, enqueued = _patch_db
    order = _Order([])
    await pos_core._auto_kds_and_kot(order, "t1", "Waiter")
    assert kitchen.docs == []
    assert enqueued == []
