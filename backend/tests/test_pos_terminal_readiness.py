from types import SimpleNamespace

import pytest

from domains.pms.pos_fnb_router import kitchen, pos_core


class _FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sort_args = None

    def sort(self, *args):
        self.sort_args = args
        return self

    async def to_list(self, _length):
        return self.rows


class _FakeKitchenOrders:
    def __init__(self):
        self.query = None
        self.cursor = _FakeCursor([])

    def find(self, query, _projection):
        self.query = query
        return self.cursor


def test_default_table_layout_is_persistable_and_tenant_scoped():
    tables = pos_core.create_default_table_layout("tenant-A", "outlet-A")

    assert len(tables) == 8
    assert {table["table_number"] for table in tables} == {str(i) for i in range(1, 9)}
    assert all(table["tenant_id"] == "tenant-A" for table in tables)
    assert all(table["outlet_id"] == "outlet-A" for table in tables)
    assert all(table["status"] == "available" for table in tables)
    assert all(table["seats"] == 4 for table in tables)


@pytest.mark.asyncio
async def test_kitchen_default_queue_keeps_ready_orders_visible(monkeypatch):
    collection = _FakeKitchenOrders()
    monkeypatch.setattr(kitchen, "db", SimpleNamespace(kitchen_orders=collection))

    await kitchen._get_active_kitchen_orders("tenant-A")

    assert collection.query == {
        "tenant_id": "tenant-A",
        "status": {"$in": ["pending", "preparing", "ready"]},
    }


@pytest.mark.asyncio
async def test_kitchen_explicit_status_filter_is_preserved(monkeypatch):
    collection = _FakeKitchenOrders()
    monkeypatch.setattr(kitchen, "db", SimpleNamespace(kitchen_orders=collection))

    await kitchen._get_active_kitchen_orders("tenant-A", statuses=["ready"])

    assert collection.query == {
        "tenant_id": "tenant-A",
        "status": {"$in": ["ready"]},
    }
