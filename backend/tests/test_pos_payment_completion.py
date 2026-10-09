from types import SimpleNamespace

import pytest

from domains.pms.pos_fnb.pos_fnb_service_v2 import PosFnbServiceV2


class Collection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items() if not isinstance(value, dict)):
                return dict(doc)
        return None

    async def insert_one(self, doc, **_kwargs):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, **_kwargs):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items() if not isinstance(value, dict)):
                doc.update(update.get("$set", {}))
                for key, value in update.get("$push", {}).items():
                    doc.setdefault(key, []).append(value)
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def update_many(self, _query, update):
        for doc in self.docs:
            doc.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=len(self.docs), modified_count=len(self.docs))


def context():
    return SimpleNamespace(tenant_id="tenant-1", actor_id="manager-1", actor_role="admin", actor_is_super_admin=False)


@pytest.mark.asyncio
async def test_mixed_payment_must_equal_order_total():
    service = PosFnbServiceV2()
    service._db = SimpleNamespace(
        pos_transactions=Collection(),
        pos_orders=Collection([{"id": "order-1", "tenant_id": "tenant-1", "status": "pending", "payment_status": "unpaid", "grand_total": 120}]),
    )
    method = PosFnbServiceV2.close_order.__wrapped__
    result = await method(service, context(), "order-1", payments=[{"method": "cash", "amount": 50}, {"method": "card", "amount": 60}])
    assert result.ok is False
    assert result.code == "PAYMENT_MISMATCH"


@pytest.mark.asyncio
async def test_void_line_recalculates_order_and_cancels_kitchen(monkeypatch):
    orders = Collection([{
        "id": "order-1", "tenant_id": "tenant-1", "status": "pending", "payment_status": "unpaid",
        "order_items": [
            {"line_id": "line-1", "item_name": "Çorba", "quantity": 1, "total": 100, "tax_rate": .1},
            {"line_id": "line-2", "item_name": "Su", "quantity": 1, "total": 20, "tax_rate": .1},
        ],
    }])
    kitchen = Collection([{"id": "k-1", "tenant_id": "tenant-1", "order_id": "order-1", "line_id": "line-1", "status": "pending"}])
    service = PosFnbServiceV2()
    service._db = SimpleNamespace(pos_orders=orders, kitchen_orders=kitchen, pos_order_item_voids=Collection())
    monkeypatch.setattr(service, "_broadcast_kitchen_queue", lambda _tenant: _none())
    method = PosFnbServiceV2.void_order_item.__wrapped__
    result = await method(service, context(), "order-1", 0, "Yanlış ürün")
    assert result.ok is True
    assert result.data["grand_total"] == 22
    assert orders.docs[0]["order_items"][0]["item_name"] == "Su"
    assert kitchen.docs[0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_refund_cannot_exceed_original_payment(monkeypatch):
    service = PosFnbServiceV2()
    service._db = SimpleNamespace(
        pos_orders=Collection([{"id": "order-1", "tenant_id": "tenant-1", "status": "closed", "payment_status": "paid"}]),
        pos_transactions=Collection([{"id": "sale-1", "tenant_id": "tenant-1", "order_id": "order-1", "status": "completed", "total_amount": 100, "payment_method": "cash"}]),
    )
    method = PosFnbServiceV2.refund_order.__wrapped__
    result = await method(service, context(), "order-1", 101, "Misafir talebi", "refund-1")
    assert result.ok is False
    assert result.code == "REFUND_LIMIT"


@pytest.mark.asyncio
async def test_manager_discount_recalculates_open_check_and_keeps_audit_event():
    orders = Collection([{
        "id": "order-1", "tenant_id": "tenant-1", "status": "pending", "payment_status": "unpaid",
        "total_amount": 100, "tax_amount": 10, "grand_total": 110,
    }])
    service = PosFnbServiceV2()
    service._db = SimpleNamespace(pos_orders=orders)
    method = PosFnbServiceV2.apply_order_adjustment.__wrapped__
    result = await method(service, context(), "order-1", "discount", "percentage", 10, "Yetkili misafir indirimi")
    assert result.ok is True
    assert result.data["discount_amount"] == 11
    assert result.data["grand_total"] == 99
    assert orders.docs[0]["adjustments"][0]["reason"] == "Yetkili misafir indirimi"


@pytest.mark.asyncio
async def test_waiter_cannot_apply_manager_adjustment():
    service = PosFnbServiceV2()
    service._db = SimpleNamespace(pos_orders=Collection())
    waiter = SimpleNamespace(tenant_id="tenant-1", actor_id="waiter-1", actor_role="waiter", actor_is_super_admin=False)
    method = PosFnbServiceV2.apply_order_adjustment.__wrapped__
    result = await method(service, waiter, "order-1", "discount", "fixed", 5, "İndirim")
    assert result.ok is False
    assert result.code == "FORBIDDEN"


async def _none():
    return None
