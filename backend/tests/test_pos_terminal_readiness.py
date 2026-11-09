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


@pytest.mark.asyncio
async def test_legacy_kitchen_ticket_resolves_own_tenant_room_without_rewriting_source(monkeypatch):
    booking_id = "34105c3e-026c-40bd-bfa3-3320f95733af"
    missing_id = "44c3f09d-34c9-4d59-a8d3-b82263ad4a0d"
    room_ticket = {"table_number": f"Oda {booking_id}", "source_pos_order_id": "pos-1"}
    missing_ticket = {"table_number": f"Oda {missing_id}", "source_pos_order_id": "pos-2"}
    table_ticket = {"table_number": "12", "source_pos_order_id": "pos-3"}
    orders = _FakeKitchenOrders()
    orders.cursor.rows = [room_ticket, missing_ticket, table_ticket]

    class Collection:
        def __init__(self, rows, expected_ids, expected_status=None):
            self.rows = rows
            self.expected_ids = expected_ids
            self.expected_status = expected_status

        def find(self, query, _projection):
            assert query["tenant_id"] == "tenant-A"
            assert set(query["id"]["$in"]) == self.expected_ids
            assert query.get("status") == self.expected_status
            return _FakeCursor(self.rows)

    monkeypatch.setattr(kitchen, "db", SimpleNamespace(
        kitchen_orders=orders,
        bookings=Collection(
            [{"id": booking_id, "room_id": "physical-131"}],
            {booking_id, missing_id},
            {"$in": ["checked_in", "in_house"]},
        ),
        rooms=Collection([{"id": "physical-131", "room_number": "131"}], {"physical-131"}),
    ))

    response = await kitchen.get_kitchen_orders(current_user=SimpleNamespace(tenant_id="tenant-A"))
    room, missing, table = response["orders"]
    assert (room["table_number"], room["room_number"]) == (None, "131")
    assert (missing["table_number"], missing["table_name"]) == (None, "Oda servisi")
    assert table == table_ticket
    assert room_ticket["table_number"] == f"Oda {booking_id}"
