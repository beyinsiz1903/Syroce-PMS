"""Task #75 — Unit-mismatch guard for /api/accounting/inventory/transfer.

Verifies that POST /api/accounting/inventory/transfer rejects (422) when the
source and destination inventory rows use different units of measure unless
an explicit conversion_factor is supplied. When a conversion factor is
provided, the destination increment uses `quantity * conversion_factor`.

This is a router-level unit test against a fake Mongo collection — it does
not require a running backend or live DB, matching the
`test_pos_check_split_body_contract.py` pattern.
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.finance import accounting as accounting_mod
from routers.finance.accounting import router as finance_router


class _FakeInventoryItems:
    def __init__(self, items):
        # items: {id: {"id":..., "tenant_id":..., "quantity":..., "unit":...}}
        self._items = items
        self.inc_calls = []  # (filter, inc_amount)

    async def find_one(self, filt, projection=None):
        for it in self._items.values():
            if all(it.get(k) == v for k, v in filt.items() if not isinstance(v, dict)):
                return dict(it)
        return None

    async def update_one(self, filt, update):
        inc = update.get("$inc", {}).get("quantity", 0)
        # Match by id+tenant_id; honour optional `quantity: {$gte: ...}` guard.
        for it in self._items.values():
            if it["id"] != filt.get("id") or it["tenant_id"] != filt.get("tenant_id"):
                continue
            q_guard = filt.get("quantity")
            if isinstance(q_guard, dict) and "$gte" in q_guard:
                if it["quantity"] < q_guard["$gte"]:
                    return SimpleNamespace(matched_count=0, modified_count=0)
            it["quantity"] += inc
            self.inc_calls.append((dict(filt), inc))
            return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


class _FakeStockMovements:
    def __init__(self):
        self.inserts = []

    async def insert_many(self, docs):
        self.inserts.extend(docs)
        return SimpleNamespace(inserted_ids=list(range(len(docs))))


class _FakeDB:
    def __init__(self, items):
        self.inventory_items = _FakeInventoryItems(items)
        self.stock_movements = _FakeStockMovements()


def _build_client(monkeypatch, items):
    fake_db = _FakeDB(items)
    monkeypatch.setattr(accounting_mod, "db", fake_db)

    from core.security import get_current_user
    app = FastAPI()
    app.include_router(finance_router, prefix="/api")

    async def _fake_user():
        return SimpleNamespace(id="u1", tenant_id="t1", name="Tester")

    async def _fake_perm():
        return None

    app.dependency_overrides[get_current_user] = _fake_user
    # Resolve `_perm=Depends(require_op(...))` and override it for this route.
    for route in app.routes:
        if getattr(route, "path", "") == "/api/accounting/inventory/transfer":
            for param in route.dependant.dependencies:
                if param.name == "_perm":
                    app.dependency_overrides[param.call] = _fake_perm
                    break
            break

    return TestClient(app), fake_db


@pytest.fixture
def kg_to_adet(monkeypatch):
    items = {
        "src": {"id": "src", "tenant_id": "t1", "quantity": 100.0, "unit": "kg",
                "location": "Ana Depo"},
        "dst": {"id": "dst", "tenant_id": "t1", "quantity": 0.0, "unit": "adet",
                "location": "Mutfak"},
    }
    return _build_client(monkeypatch, items)


@pytest.fixture
def same_unit(monkeypatch):
    items = {
        "src": {"id": "src", "tenant_id": "t1", "quantity": 100.0, "unit": "kg",
                "location": "Ana Depo"},
        "dst": {"id": "dst", "tenant_id": "t1", "quantity": 0.0, "unit": "kg",
                "location": "Mutfak"},
    }
    return _build_client(monkeypatch, items)


def _post(client, payload):
    return client.post("/api/accounting/inventory/transfer", json=payload)


class TestUnitMismatchGuard:
    def test_a_mismatched_units_without_factor_is_422(self, kg_to_adet):
        client, fake_db = kg_to_adet
        r = _post(client, {
            "source_item_id": "src",
            "destination_item_id": "dst",
            "quantity": 5,
        })
        assert r.status_code == 422, f"got {r.status_code} {r.text}"
        body = r.json()
        detail = body.get("detail", "").lower()
        assert "unit mismatch" in detail
        assert "kg" in detail and "adet" in detail
        # Stock must be untouched.
        assert fake_db.inventory_items._items["src"]["quantity"] == 100.0
        assert fake_db.inventory_items._items["dst"]["quantity"] == 0.0
        assert fake_db.stock_movements.inserts == []

    def test_b_mismatched_units_with_factor_applies_conversion(self, kg_to_adet):
        client, fake_db = kg_to_adet
        # 5 kg × 4 adet/kg = 20 adet at destination.
        r = _post(client, {
            "source_item_id": "src",
            "destination_item_id": "dst",
            "quantity": 5,
            "conversion_factor": 4,
        })
        assert r.status_code == 200, f"got {r.status_code} {r.text}"
        body = r.json()
        assert body["quantity"] == 5
        assert body["destination_quantity"] == 20
        assert body["conversion_factor"] == 4
        assert fake_db.inventory_items._items["src"]["quantity"] == 95.0
        assert fake_db.inventory_items._items["dst"]["quantity"] == 20.0
        # Audit legs: out=5 kg, in=20 adet, sharing one transfer_id.
        legs = fake_db.stock_movements.inserts
        assert len(legs) == 2
        out_leg = next(l for l in legs if l["movement_type"] == "transfer_out")
        in_leg = next(l for l in legs if l["movement_type"] == "transfer_in")
        assert out_leg["quantity"] == 5
        assert in_leg["quantity"] == 20
        assert out_leg["transfer_id"] == in_leg["transfer_id"]

    def test_c_zero_conversion_factor_rejected_by_pydantic(self, kg_to_adet):
        client, _ = kg_to_adet
        r = _post(client, {
            "source_item_id": "src",
            "destination_item_id": "dst",
            "quantity": 5,
            "conversion_factor": 0,
        })
        # Pydantic gt=0 → 422.
        assert r.status_code == 422

    def test_d_matching_units_unchanged_behaviour(self, same_unit):
        client, fake_db = same_unit
        r = _post(client, {
            "source_item_id": "src",
            "destination_item_id": "dst",
            "quantity": 7,
        })
        assert r.status_code == 200, f"got {r.status_code} {r.text}"
        body = r.json()
        assert body["quantity"] == 7
        assert body["destination_quantity"] == 7
        assert body["conversion_factor"] == 1.0
        assert fake_db.inventory_items._items["src"]["quantity"] == 93.0
        assert fake_db.inventory_items._items["dst"]["quantity"] == 7.0

    def test_e_matching_units_ignore_supplied_factor(self, same_unit):
        # When units match, an accidentally-supplied factor must NOT scale
        # the destination (would silently double-count). Server ignores it.
        client, fake_db = same_unit
        r = _post(client, {
            "source_item_id": "src",
            "destination_item_id": "dst",
            "quantity": 3,
            "conversion_factor": 10,
        })
        assert r.status_code == 200, f"got {r.status_code} {r.text}"
        body = r.json()
        assert body["destination_quantity"] == 3
        assert body["conversion_factor"] == 1.0
        assert fake_db.inventory_items._items["dst"]["quantity"] == 3.0
