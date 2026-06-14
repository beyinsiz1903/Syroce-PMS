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


def _match(doc: dict, flt: dict) -> bool:
    for k, v in flt.items():
        dv = doc.get(k)
        if isinstance(v, dict) and "$in" in v:
            if dv not in v["$in"]:
                return False
        elif dv != v:
            return False
    return True


class _FakeKitchenColl:
    def __init__(self):
        self.docs: list[dict] = []

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if _match(d, flt):
                return {k: v for k, v in d.items() if k != "_id"}
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return None


class _FakePrintersColl:
    """Minimal pos_printers stand-in supporting the resolver's find_one queries
    (plain equality plus the outlet_id ``$in`` membership test)."""

    def __init__(self, docs=None):
        self.docs: list[dict] = list(docs or [])

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if _match(d, flt):
                return {k: v for k, v in d.items() if k != "_id"}
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
def _patch_db(monkeypatch, request):
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
    # Hermetic printer registry so the real resolve_kot_printer runs without
    # touching a live DB. Tests can seed rows via the `printer_rows` marker.
    printers = _FakePrintersColl(getattr(request, "param", None))
    monkeypatch.setattr(spool.db, "pos_printers", printers, raising=False)
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


@pytest.mark.asyncio
async def test_unmapped_station_falls_back_with_warning(_patch_db):
    # Empty registry: the (outletA, hot_kitchen) pair maps nowhere, so the job
    # falls back to printer_id == station AND carries a visible routing warning.
    kitchen, enqueued = _patch_db
    order = _Order([_OrderItem("Kofte", 1, "food")])
    await pos_core._auto_kds_and_kot(order, "t1", "Waiter")

    assert len(enqueued) == 1
    job = enqueued[0]
    assert job["printer_id"] == "hot_kitchen"  # legacy station fallback
    assert job["routing_warning"]
    assert "hot_kitchen" in job["routing_warning"]


# Seed: outletA has its own hot_kitchen printer; a different outlet has another.
@pytest.mark.parametrize(
    "_patch_db",
    [[
        {"tenant_id": "t1", "printer_id": "rest1_hot", "station": "hot_kitchen",
         "outlet_id": "outletA", "enabled": True},
        {"tenant_id": "t1", "printer_id": "rest2_hot", "station": "hot_kitchen",
         "outlet_id": "outletB", "enabled": True},
    ]],
    indirect=True,
)
@pytest.mark.asyncio
async def test_per_outlet_printer_resolution(_patch_db):
    kitchen, enqueued = _patch_db
    order = _Order([_OrderItem("Kofte", 1, "food")])  # order.outlet_id == outletA
    await pos_core._auto_kds_and_kot(order, "t1", "Waiter")

    assert len(enqueued) == 1
    job = enqueued[0]
    # Routed to outletA's physical printer, not the generic station name.
    assert job["printer_id"] == "rest1_hot"
    assert job["routing_warning"] is None


@pytest.mark.asyncio
async def test_resolve_exact_outlet_match():
    import domains.pms.pos_extensions.pos_print_spool as spool
    rows = [
        {"tenant_id": "t1", "printer_id": "rest1_hot", "station": "hot_kitchen",
         "outlet_id": "outletA", "enabled": True},
        {"tenant_id": "t1", "printer_id": "shared_hot", "station": "hot_kitchen",
         "outlet_id": None, "enabled": True},
    ]
    orig = spool.db.pos_printers if hasattr(spool.db, "pos_printers") else None
    spool.db.pos_printers = _FakePrintersColl(rows)
    try:
        res = await spool.resolve_kot_printer("t1", "outletA", "hot_kitchen")
        assert res == {"printer_id": "rest1_hot", "matched": True, "reason": "outlet_station"}
        # An outlet with no per-outlet row falls back to the shared station printer.
        res2 = await spool.resolve_kot_printer("t1", "outletZ", "hot_kitchen")
        assert res2["printer_id"] == "shared_hot"
        assert res2["matched"] is True
        assert res2["reason"] == "station_shared"
    finally:
        if orig is not None:
            spool.db.pos_printers = orig


@pytest.mark.asyncio
async def test_resolve_legacy_printer_id_equals_station():
    import domains.pms.pos_extensions.pos_print_spool as spool
    rows = [
        {"tenant_id": "t1", "printer_id": "bar", "station": None,
         "outlet_id": None, "enabled": True},
    ]
    orig = spool.db.pos_printers if hasattr(spool.db, "pos_printers") else None
    spool.db.pos_printers = _FakePrintersColl(rows)
    try:
        res = await spool.resolve_kot_printer("t1", "outletA", "bar")
        assert res == {"printer_id": "bar", "matched": True, "reason": "legacy_id"}
    finally:
        if orig is not None:
            spool.db.pos_printers = orig


@pytest.mark.asyncio
async def test_resolve_unmapped_is_not_matched():
    import domains.pms.pos_extensions.pos_print_spool as spool
    orig = spool.db.pos_printers if hasattr(spool.db, "pos_printers") else None
    spool.db.pos_printers = _FakePrintersColl([])
    try:
        res = await spool.resolve_kot_printer("t1", "outletA", "cold_kitchen")
        assert res == {"printer_id": "cold_kitchen", "matched": False, "reason": "unmapped"}
    finally:
        if orig is not None:
            spool.db.pos_printers = orig


@pytest.mark.asyncio
async def test_resolve_disabled_printer_skipped():
    import domains.pms.pos_extensions.pos_print_spool as spool
    rows = [
        {"tenant_id": "t1", "printer_id": "rest1_hot", "station": "hot_kitchen",
         "outlet_id": "outletA", "enabled": False},
    ]
    orig = spool.db.pos_printers if hasattr(spool.db, "pos_printers") else None
    spool.db.pos_printers = _FakePrintersColl(rows)
    try:
        # The only mapped printer is disabled -> falls through to unmapped.
        res = await spool.resolve_kot_printer("t1", "outletA", "hot_kitchen")
        assert res["matched"] is False
        assert res["reason"] == "unmapped"
    finally:
        if orig is not None:
            spool.db.pos_printers = orig
