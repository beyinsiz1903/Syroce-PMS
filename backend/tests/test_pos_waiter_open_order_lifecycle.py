from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.pos_fnb.pos_fnb_service_v2 import PosFnbServiceV2
from domains.pms.pos_fnb_router import kitchen, pos_core


class MemoryCollection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    @staticmethod
    def _matches(doc, query):
        for key, expected in query.items():
            actual = doc.get(key)
            if isinstance(expected, dict):
                if "$ne" in expected and actual == expected["$ne"]:
                    return False
                if "$nin" in expected and actual in expected["$nin"]:
                    return False
                if "$in" in expected and actual not in expected["$in"]:
                    return False
            elif actual != expected:
                return False
        return True

    async def find_one(self, query, _projection=None):
        return next((dict(doc) for doc in self.docs if self._matches(doc, query)), None)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))

    async def update_one(self, query, update):
        for doc in self.docs:
            if not self._matches(doc, query):
                continue
            for key, value in update.get("$set", {}).items():
                doc[key] = value
            for key, value in update.get("$inc", {}).items():
                doc[key] = doc.get(key, 0) + value
            for key, value in update.get("$push", {}).items():
                values = value.get("$each", []) if isinstance(value, dict) else [value]
                doc.setdefault(key, []).extend(values)
            return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def update_many(self, query, update):
        changed = 0
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(update.get("$set", {}))
                changed += 1
        return SimpleNamespace(matched_count=changed, modified_count=changed)


def ctx():
    return SimpleNamespace(tenant_id="tenant-1", actor_id="waiter-1", actor_role="admin")


@pytest.mark.asyncio
async def test_waiter_can_append_items_to_open_order_idempotently(monkeypatch):
    orders = MemoryCollection([{
        "id": "order-1", "tenant_id": "tenant-1", "outlet_id": "outlet-1",
        "table_number": "4", "order_number": "ORD-1", "status": "pending",
        "payment_status": "unpaid", "order_items": [], "total_amount": 0,
        "tax_amount": 0, "grand_total": 0,
    }])
    batches = MemoryCollection()
    kitchen_orders = MemoryCollection()
    service = PosFnbServiceV2()
    service._db = SimpleNamespace(
        pos_orders=orders,
        pos_order_item_batches=batches,
        kitchen_orders=kitchen_orders,
    )
    monkeypatch.setattr(service, "_broadcast_kitchen_queue", lambda _tenant_id: _async_none())

    payload = [{"item_id": "burger", "name": "Burger", "quantity": 2, "price": 100}]
    method = PosFnbServiceV2.add_order_items.__wrapped__
    first = await method(service, ctx(), "order-1", payload, "append-key")
    second = await method(service, ctx(), "order-1", payload, "append-key")

    assert first.ok is True
    assert second.data["idempotent"] is True
    assert orders.docs[0]["grand_total"] == 220
    assert len(orders.docs[0]["order_items"]) == 1
    assert len(kitchen_orders.docs) == 1


@pytest.mark.asyncio
async def test_waiter_cannot_open_second_order_on_occupied_table():
    service = PosFnbServiceV2()
    service._db = SimpleNamespace(table_layouts=MemoryCollection([{
        "tenant_id": "tenant-1", "outlet_id": "outlet-1", "table_number": "4",
        "status": "occupied", "current_order_id": "existing-order",
    }]))

    method = PosFnbServiceV2.create_order.__wrapped__
    result = await method(
        service, ctx(), "outlet-1", table_number="4",
        items=[{"item_id": "burger", "name": "Burger", "price": 100}],
    )

    assert result.ok is False
    assert result.code == "TABLE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_waiter_transfers_open_order_and_releases_source_table(monkeypatch):
    orders = MemoryCollection([{
        "id": "order-1", "tenant_id": "tenant-1", "outlet_id": "outlet-1",
        "table_number": "4", "status": "pending", "payment_status": "unpaid",
    }])
    tables = MemoryCollection([
        {"id": "t4", "tenant_id": "tenant-1", "outlet_id": "outlet-1", "table_number": "4", "status": "occupied", "current_order_id": "order-1"},
        {"id": "t8", "tenant_id": "tenant-1", "outlet_id": "outlet-1", "table_number": "8", "status": "available", "current_order_id": None},
    ])
    service = PosFnbServiceV2()
    service._db = SimpleNamespace(
        pos_orders=orders,
        table_layouts=tables,
        kitchen_orders=MemoryCollection(),
    )
    monkeypatch.setattr(service, "_broadcast_kitchen_queue", lambda _tenant_id: _async_none())

    method = PosFnbServiceV2.transfer_order_table.__wrapped__
    result = await method(service, ctx(), "order-1", "8")

    assert result.ok is True
    assert orders.docs[0]["table_number"] == "8"
    assert tables.docs[0]["status"] == "available"
    assert tables.docs[0]["current_order_id"] is None
    assert tables.docs[1]["status"] == "occupied"
    assert tables.docs[1]["current_order_id"] == "order-1"


@pytest.mark.asyncio
async def test_waiter_does_not_transfer_onto_a_legacy_open_check(monkeypatch):
    orders = MemoryCollection([{
        "id": "order-1", "tenant_id": "tenant-1", "outlet_id": "outlet-1",
        "table_number": "4", "status": "pending", "payment_status": "unpaid",
    }])
    tables = MemoryCollection([
        {"id": "t4", "tenant_id": "tenant-1", "outlet_id": "outlet-1", "table_number": "4", "status": "occupied", "current_order_id": "order-1"},
        {"id": "t8", "tenant_id": "tenant-1", "outlet_id": "outlet-1", "table_number": "8", "status": "available", "current_transaction_id": "legacy-check-1"},
    ])
    service = PosFnbServiceV2()
    service._db = SimpleNamespace(
        pos_orders=orders,
        table_layouts=tables,
        kitchen_orders=MemoryCollection(),
    )
    monkeypatch.setattr(service, "_broadcast_kitchen_queue", lambda _tenant_id: _async_none())

    method = PosFnbServiceV2.transfer_order_table.__wrapped__
    result = await method(service, ctx(), "order-1", "8")

    assert result.ok is False
    assert result.code == "TABLE_UNAVAILABLE"
    assert orders.docs[0]["table_number"] == "4"


@pytest.mark.asyncio
async def test_kitchen_terminal_state_cannot_regress(monkeypatch):
    collection = MemoryCollection([{"id": "k1", "tenant_id": "tenant-1", "status": "served"}])
    monkeypatch.setattr(kitchen, "db", SimpleNamespace(kitchen_orders=collection))

    with pytest.raises(HTTPException) as exc:
        await kitchen.update_kitchen_order_status_v2(
            "k1", "preparing", current_user=ctx(), _perm=None,
        )

    assert exc.value.status_code == 409
    assert collection.docs[0]["status"] == "served"


@pytest.mark.asyncio
async def test_open_table_cannot_be_manually_marked_available(monkeypatch):
    collection = MemoryCollection([{
        "id": "table-1", "tenant_id": "tenant-1", "status": "occupied",
        "current_order_id": "order-1",
    }])
    monkeypatch.setattr(pos_core, "db", SimpleNamespace(table_layouts=collection))

    with pytest.raises(HTTPException) as exc:
        await pos_core.update_pos_table_status(
            "table-1", "available", current_user=ctx(), _perm=None,
        )

    assert exc.value.status_code == 409
    assert collection.docs[0]["status"] == "occupied"


@pytest.mark.asyncio
async def test_room_charge_fails_closed_when_open_folio_is_missing():
    service = PosFnbServiceV2()
    service._db = SimpleNamespace(
        pos_transactions=MemoryCollection(),
        pos_orders=MemoryCollection([{
            "id": "order-1", "tenant_id": "tenant-1", "status": "pending",
            "payment_status": "unpaid", "grand_total": 120, "order_items": [],
        }]),
        folios=MemoryCollection(),
    )

    method = PosFnbServiceV2.close_order.__wrapped__
    result = await method(
        service, ctx(), "order-1", payment_method="room_charge",
        post_to_folio=True, booking_id="booking-1",
    )

    assert result.ok is False
    assert result.code == "FOLIO_NOT_OPEN"
    assert service._db.pos_transactions.docs == []
    assert service._db.pos_orders.docs[0]["status"] == "pending"


async def _async_none():
    return None
