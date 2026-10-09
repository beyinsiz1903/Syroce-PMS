"""Regression coverage for the POS dine-in table compare-and-set."""

from types import SimpleNamespace

import pytest

from domains.pms.pos_fnb import pos_fnb_service_v2 as pos_service_module
from domains.pms.pos_fnb.pos_fnb_service_v2 import PosFnbServiceV2, PosTableUnavailable


class _AlreadyClaimedTable:
    async def update_one(self, _query, _update, **_kwargs):
        return SimpleNamespace(matched_count=0)


class _AvailableTable:
    def __init__(self):
        self.query = None
        self.update = None

    async def update_one(self, query, update, **_kwargs):
        self.query = query
        self.update = update
        return SimpleNamespace(matched_count=1)


class _Recorder:
    def __init__(self):
        self.rows = []

    async def insert_one(self, document, **_kwargs):
        self.rows.append(dict(document))

    async def insert_many(self, documents, **_kwargs):
        self.rows.extend(dict(document) for document in documents)


async def _transaction_callback(**kwargs):
    return await kwargs["callback"](None)


@pytest.mark.asyncio
async def test_losing_table_claim_creates_no_order_or_kitchen_rows(monkeypatch):
    service = PosFnbServiceV2()
    orders = _Recorder()
    kitchen = _Recorder()
    service._db = SimpleNamespace(
        client=object(),
        table_layouts=_AlreadyClaimedTable(),
        pos_orders=orders,
        kitchen_orders=kitchen,
    )
    monkeypatch.setattr(pos_service_module, "with_resource_locks", _transaction_callback)

    with pytest.raises(PosTableUnavailable):
        await service._persist_order_and_claim_table(
            tenant_id="tenant-1",
            outlet_id="outlet-1",
            table_number="12",
            order_doc={"id": "order-1", "created_at": "2026-10-09T00:00:00+00:00"},
            kitchen_docs=[{"id": "kitchen-1"}],
        )

    assert orders.rows == []
    assert kitchen.rows == []


@pytest.mark.asyncio
async def test_successful_claim_persists_the_order_and_all_kitchen_rows(monkeypatch):
    service = PosFnbServiceV2()
    table = _AvailableTable()
    orders = _Recorder()
    kitchen = _Recorder()
    service._db = SimpleNamespace(
        client=object(),
        table_layouts=table,
        pos_orders=orders,
        kitchen_orders=kitchen,
    )
    monkeypatch.setattr(pos_service_module, "with_resource_locks", _transaction_callback)

    await service._persist_order_and_claim_table(
        tenant_id="tenant-1",
        outlet_id="outlet-1",
        table_number="12",
        order_doc={"id": "order-1", "created_at": "2026-10-09T00:00:00+00:00"},
        kitchen_docs=[{"id": "kitchen-1"}, {"id": "kitchen-2"}],
    )

    assert table.query["status"] == "available"
    assert table.query["current_order_id"] is None
    assert table.update["$set"]["current_order_id"] == "order-1"
    assert [row["id"] for row in orders.rows] == ["order-1"]
    assert [row["id"] for row in kitchen.rows] == ["kitchen-1", "kitchen-2"]
