"""Regression coverage for POS refund write-time protection."""

from types import SimpleNamespace

import pytest

from domains.pms.pos_extensions import pos_print_spool
from domains.pms.pos_fnb import pos_fnb_service_v2 as pos_service_module
from domains.pms.pos_fnb.pos_fnb_service_v2 import PosFnbServiceV2


class _Collection:
    def __init__(self, docs=()):
        self.docs = [dict(doc) for doc in docs]

    async def find_one_and_update(self, query, pipeline, **_kwargs):
        for doc in self.docs:
            if any(doc.get(key) != value for key, value in query.items() if not key.startswith("$")):
                continue
            amount = query["$expr"]["$lte"][0]["$add"][1]
            ceiling = query["$expr"]["$lte"][1]
            if float(doc.get("refunded_amount") or 0) + amount > ceiling:
                return None
            doc["refunded_amount"] = float(doc.get("refunded_amount") or 0) + amount
            doc["refund_status"] = "full" if doc["refunded_amount"] >= ceiling else "partial"
            return dict(doc)
        return None

    async def insert_one(self, doc, **_kwargs):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, **_kwargs):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


async def _within_transaction(**kwargs):
    return await kwargs["callback"](None)


@pytest.mark.asyncio
async def test_refund_write_rejects_amount_that_exceeds_current_remaining_balance(monkeypatch):
    """A stale caller cannot insert a refund after another refund used the balance."""
    service = PosFnbServiceV2()
    transactions = _Collection(
        [{"id": "sale-1", "tenant_id": "tenant-1", "status": "completed", "refunded_amount": 50.0}]
    )
    orders = _Collection([{"id": "order-1", "tenant_id": "tenant-1", "payment_status": "paid"}])
    service._db = SimpleNamespace(client=object(), pos_transactions=transactions, pos_orders=orders)
    monkeypatch.setattr(pos_service_module, "with_resource_locks", _within_transaction)

    result = await service._persist_refund_and_state(
        tenant_id="tenant-1",
        order_id="order-1",
        sale_id="sale-1",
        paid=100.0,
        refund_amount=60.0,
        refund_doc={"id": "refund-1", "tenant_id": "tenant-1"},
    )

    assert result is None
    assert len(transactions.docs) == 1
    assert transactions.docs[0]["refunded_amount"] == 50.0
    assert orders.docs[0]["payment_status"] == "paid"


@pytest.mark.asyncio
async def test_refund_write_updates_sale_order_and_refund_together(monkeypatch):
    service = PosFnbServiceV2()
    transactions = _Collection(
        [{"id": "sale-1", "tenant_id": "tenant-1", "status": "completed", "refunded_amount": 40.0}]
    )
    orders = _Collection([{"id": "order-1", "tenant_id": "tenant-1", "payment_status": "paid"}])
    service._db = SimpleNamespace(client=object(), pos_transactions=transactions, pos_orders=orders)
    monkeypatch.setattr(pos_service_module, "with_resource_locks", _within_transaction)

    result = await service._persist_refund_and_state(
        tenant_id="tenant-1",
        order_id="order-1",
        sale_id="sale-1",
        paid=100.0,
        refund_amount=60.0,
        refund_doc={"id": "refund-1", "tenant_id": "tenant-1", "payment_type": "refund"},
    )

    assert result["refund_status"] == "full"
    assert transactions.docs[0]["refunded_amount"] == 100.0
    assert transactions.docs[1]["id"] == "refund-1"
    assert orders.docs[0]["payment_status"] == "refunded"


@pytest.mark.asyncio
async def test_kot_deduplication_is_per_append_batch_not_only_order_and_station(monkeypatch):
    keys = []

    async def routing(*_args):
        return {"printer_id": "kitchen-1", "matched": True}

    async def enqueue(**kwargs):
        keys.append(kwargs["idempotency_key"])

    monkeypatch.setattr(pos_print_spool, "resolve_kot_printer", routing)
    monkeypatch.setattr(pos_print_spool, "enqueue_print_job", enqueue)
    service = PosFnbServiceV2()
    order = {"id": "order-1", "outlet_id": "outlet-1", "order_number": "A1"}

    await service._enqueue_kot("tenant-1", order, [{"line_id": "line-1", "station": "hot"}], "waiter-1")
    await service._enqueue_kot("tenant-1", order, [{"line_id": "line-2", "station": "hot"}], "waiter-1")

    assert len(keys) == 2
    assert keys[0] != keys[1]
    assert keys[0].startswith("kot-v2-order-1-hot-")
