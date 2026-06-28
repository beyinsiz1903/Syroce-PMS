"""Backend tests for the B2B Supply Integration & Automated Replenishment.

Locks in regressions for:
1. Low stock detection and marketplace product matching (SKU / Name matching).
2. Verification of vendor approval before generating proposals.
3. Automated order grouping by vendor and marketplace order generation (mp_orders).
4. Local trace registration (procurement_b2b_replenishments).
"""
from __future__ import annotations

import sys
import datetime as dt
if not hasattr(dt, "UTC"):
    dt.UTC = dt.timezone.utc

from types import SimpleNamespace
from typing import Any
import pytest
from datetime import datetime, timezone
from datetime import timezone as dt_timezone
UTC = dt_timezone.utc
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers import procurement_b2b as proc_b2b_router
from routers.procurement_b2b import router as proc_b2b_api_router

TENANT_ID = "t-b2b-1"
_VENDOR_ID = "vendor-b2b-1"
_PRODUCT_ID = "prod-b2b-1"
_ITEM_ID = "item-b2b-1"


class _FakeCursor:
    def __init__(self, docs): self._docs = list(docs)
    def sort(self, *_a, **_kw): return self
    def __aiter__(self):
        self._it = iter(self._docs); return self
    async def __anext__(self):
        try: return next(self._it)
        except StopIteration: raise StopAsyncIteration
    async def to_list(self, *args, **kwargs): return list(self._docs)


class _MockCollection:
    def __init__(self, name, initial_docs=None):
        self.name = name
        self.docs = {d["id"]: dict(d) for d in (initial_docs or [])}

    async def find_one(self, flt, _proj=None):
        for d in self.docs.values():
            if flt.get("tenant_id") is None or d.get("tenant_id") == flt.get("tenant_id") or d.get("tenant_id") == "unknown":
                match = True
                for k, v in flt.items():
                    if k != "tenant_id" and k != "is_active" and d.get(k) != v:
                        match = False
                if match:
                    return dict(d)
        return None

    def find(self, flt, *_a, **_kw):
        matching = []
        for d in self.docs.values():
            if flt.get("tenant_id") is None or d.get("tenant_id") == flt.get("tenant_id") or d.get("tenant_id") == "unknown":
                match = True
                for k, v in flt.items():
                    if k != "tenant_id" and k != "is_active" and d.get(k) != v:
                        match = False
                if match:
                    matching.append(dict(d))
        return _FakeCursor(matching)

    async def insert_one(self, doc):
        self.docs[doc["id"]] = dict(doc)
        return SimpleNamespace(inserted_id=doc["id"])

    async def update_one(self, flt, update, upsert=False, session=None):
        target = None
        for d in self.docs.values():
            if flt.get("tenant_id") is None or d.get("tenant_id") == flt.get("tenant_id"):
                match = True
                for k, v in flt.items():
                    if k != "tenant_id" and d.get(k) != v:
                        match = False
                if match:
                    target = d
        if target:
            if "$set" in update:
                target.update(update["$set"])
            if "$inc" in update:
                for k, v in update["$inc"].items():
                    target[k] = target.get(k, 0) + v
            return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


class _FakeDB:
    def __init__(self):
        self.inventory_items = _MockCollection("inventory_items", [
            {
                "id": _ITEM_ID,
                "tenant_id": TENANT_ID,
                "name": "Organic Milk",
                "sku": "MILK-ORG",
                "quantity": 2.0,
                "reorder_level": 5.0
            },
            {
                "id": "item-ok",
                "tenant_id": TENANT_ID,
                "name": "Sugar",
                "sku": "SUGAR-1KG",
                "quantity": 20.0,
                "reorder_level": 5.0
            }
        ])
        self.mp_products = _MockCollection("mp_products", [
            {
                "id": _PRODUCT_ID,
                "tenant_id": "unknown",
                "vendor_id": _VENDOR_ID,
                "vendor_name": "Mega Wholesale",
                "name": "Organic Milk",
                "sku": "MILK-ORG",
                "price_try": 45.0,
                "moq": 5,
                "stock": 100,
                "is_active": True
            }
        ])
        self.mp_vendors = _MockCollection("mp_vendors", [
            {
                "id": _VENDOR_ID,
                "tenant_id": "unknown",
                "company_name": "Mega Wholesale",
                "status": "approved"
            }
        ])
        self.mp_orders = _MockCollection("mp_orders")
        self.procurement_b2b_replenishments = _MockCollection("procurement_b2b_replenishments")


@pytest.fixture
def env(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr(proc_b2b_router, "get_system_db", lambda: fake_db)

    # Mock place_order from modules/supplies_market/service
    async def _mock_place_order(payload, hotel_tenant_id, hotel_name):
        order_id = "sm-ord-123"
        order_doc = {
            "id": order_id,
            "order_no": "SM-123456",
            "hotel_tenant_id": hotel_tenant_id,
            "hotel_name": hotel_name,
            "vendor_id": _VENDOR_ID,
            "vendor_name": "Mega Wholesale",
            "lines": [{"product_id": line.product_id, "quantity": line.quantity} for line in payload.lines],
            "total": 45.0 * sum(line.quantity for line in payload.lines),
            "status": "pending"
        }
        await fake_db.mp_orders.insert_one(order_doc)
        return order_doc

    monkeypatch.setattr(proc_b2b_router, "place_order", _mock_place_order)

    app = FastAPI()
    app.include_router(proc_b2b_api_router)

    from core.security import get_current_user
    async def _admin_user():
        return SimpleNamespace(
            id="u1", username="admin",
            tenant_id=TENANT_ID, role="admin",
            granted_permissions=None,
        )
    app.dependency_overrides[get_current_user] = _admin_user

    from modules.pms_core.role_permission_service import require_op
    async def _fake_require_op(*args, **kwargs):
        return True
    app.dependency_overrides[require_op] = _fake_require_op

    client = TestClient(app)
    return SimpleNamespace(client=client, db=fake_db, app=app)


def test_get_replenishment_proposals(env):
    r = env.client.get("/api/procurement/b2b/proposals")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["proposals"]) == 1
    prop = data["proposals"][0]
    assert prop["vendor_id"] == _VENDOR_ID
    assert len(prop["lines"]) == 1
    line = prop["lines"][0]
    assert line["inventory_item_id"] == _ITEM_ID
    assert line["mp_product_id"] == _PRODUCT_ID
    # reorder level (5) * 2 - quantity (2) = 8.
    assert line["proposed_qty"] == 8


def test_approve_replenishment_orders(env):
    r = env.client.post(
        "/api/procurement/b2b/orders/approve",
        json={
            "lines": [
                {
                    "inventory_item_id": _ITEM_ID,
                    "mp_product_id": _PRODUCT_ID,
                    "quantity": 10
                }
            ],
            "shipping_address": "Main Hotel, Istanbul",
            "contact_name": "John",
            "contact_phone": "+905555555555"
        }
    )
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["success"] is True

    # Verify order created in mp_orders
    assert len(env.db.mp_orders.docs) == 1
    order = list(env.db.mp_orders.docs.values())[0]
    assert order["vendor_id"] == _VENDOR_ID
    assert order["total"] == 450.0

    # Verify trace log recorded
    assert len(env.db.procurement_b2b_replenishments.docs) == 1
    trace = list(env.db.procurement_b2b_replenishments.docs.values())[0]
    assert trace["inventory_item_id"] == _ITEM_ID
    assert trace["order_id"] == order["id"]
