"""Targeted tests for the F&B Cost Controller (recipe costing + variance).

Pinned contract (Kademe 2):
  * Recipe cost is computed server-side from inventory_items.unit_cost; per-portion
    = batch_cost / yield_portions; missing inventory costs are flagged.
  * food_cost_pct = cost_per_portion / menu_price * 100.
  * Variance = actual (inventory_movements outflow) - theoretical (sold qty x
    recipe ingredient qty), reported per ingredient and in totals.
  * Recipe mutations are admin-tier RBAC; reads tenant-scoped.

In-memory fake-DB approach (mirrors tests/test_laundry_orders.py).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms import fnb_cost_router as fc


def _match(doc: dict, flt: dict) -> bool:
    for k, v in flt.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif isinstance(v, dict) and ("$gte" in v or "$lte" in v):
            val = doc.get(k)
            if "$gte" in v and (val is None or val < v["$gte"]):
                return False
            if "$lte" in v and (val is None or val > v["$lte"]):
                return False
        elif doc.get(k) != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        out = [{kk: vv for kk, vv in d.items() if kk != "_id"} for d in self._docs]
        return out[:n] if n else out


class _Coll:
    def __init__(self):
        self.docs: list[dict] = []

    def find(self, flt=None, proj=None):
        flt = flt or {}
        return _Cursor([d for d in self.docs if _match(d, flt)])

    async def find_one(self, flt, proj=None, sort=None):
        matches = [d for d in self.docs if _match(d, flt)]
        if not matches:
            return None
        return {kk: vv for kk, vv in matches[0].items() if kk != "_id"}

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id", "x"))

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if _match(d, flt):
                if "$set" in update:
                    d.update(update["$set"])
                return SimpleNamespace(matched_count=1, modified_count=1)
        if upsert:
            newdoc = {k: v for k, v in flt.items() if not isinstance(v, dict)}
            newdoc.update(update.get("$set", {}))
            newdoc.update(update.get("$setOnInsert", {}))
            self.docs.append(newdoc)
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id="x")
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if _match(d, flt):
                self.docs.pop(i)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class _FakeDB:
    def __init__(self):
        self.fnb_recipes = _Coll()
        self.pos_menu_items = _Coll()
        self.inventory_items = _Coll()
        self.pos_orders = _Coll()
        self.inventory_movements = _Coll()

    def __getitem__(self, name):
        return getattr(self, name)


TENANT = "tenant-A"


def _user(role="admin", *, super_admin=False, tenant=TENANT):
    return SimpleNamespace(
        id="u1", user_id="u1", tenant_id=tenant, role=role,
        is_super_admin=super_admin, name="Staff", email="s@example.com",
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(fc, "db", fake)
    return fake


def _seed_inv(fake, iid, name, unit_cost, unit="g"):
    fake.inventory_items.docs.append({
        "id": iid, "tenant_id": TENANT, "name": name,
        "unit_cost": unit_cost, "unit": unit,
    })


def _seed_menu(fake, mid, name, price):
    fake.pos_menu_items.docs.append({
        "id": mid, "tenant_id": TENANT, "name": name, "price": price,
    })


async def _upsert(fake, mid, ingredients, user, portions=1, name=None):
    payload = fc.RecipeIn(
        menu_item_name=name,
        yield_portions=portions,
        ingredients=[fc.Ingredient(**i) for i in ingredients],
    )
    return (await fc.upsert_recipe(menu_item_id=mid, payload=payload, current_user=user))["recipe"]


# ---------------------------------------------------------------------------
# Recipe CRUD + cost
# ---------------------------------------------------------------------------
async def test_upsert_recipe_rbac_denies_front_desk(_patch):
    with pytest.raises(HTTPException) as exc:
        await _upsert(_patch, "m1", [{"inventory_item_id": "i1", "quantity": 1}], _user("front_desk"))
    assert exc.value.status_code == 403


async def test_upsert_is_idempotent_single_doc(_patch):
    await _upsert(_patch, "m1", [{"inventory_item_id": "i1", "quantity": 1}], _user("admin"))
    await _upsert(_patch, "m1", [{"inventory_item_id": "i1", "quantity": 2}], _user("admin"))
    assert len(_patch.fnb_recipes.docs) == 1
    assert _patch.fnb_recipes.docs[0]["ingredients"][0]["quantity"] == 2


async def test_recipe_cost_per_portion_and_food_cost_pct(_patch):
    _seed_inv(_patch, "beef", "Dana", unit_cost=0.5)   # per g
    _seed_inv(_patch, "bun", "Ekmek", unit_cost=2.0)   # per piece
    _seed_menu(_patch, "burger", "Burger", price=120.0)
    # 150g beef + 1 bun = 75 + 2 = 77 batch; 1 portion
    await _upsert(
        _patch, "burger",
        [{"inventory_item_id": "beef", "quantity": 150},
         {"inventory_item_id": "bun", "quantity": 1}],
        _user("admin"), portions=1, name="Burger",
    )
    out = await fc.recipe_cost(menu_item_id="burger", current_user=_user("admin"))
    assert out["batch_cost"] == 77.0
    assert out["cost_per_portion"] == 77.0
    assert out["menu_price"] == 120.0
    assert out["food_cost_pct"] == round(77.0 / 120.0 * 100, 2)
    assert out["missing_costs"] is False


async def test_recipe_cost_flags_missing_inventory_cost(_patch):
    _seed_menu(_patch, "m1", "X", price=10.0)
    await _upsert(_patch, "m1", [{"inventory_item_id": "ghost", "quantity": 5}], _user("admin"))
    out = await fc.recipe_cost(menu_item_id="m1", current_user=_user("admin"))
    assert out["missing_costs"] is True
    assert out["cost_per_portion"] == 0.0


async def test_yield_portions_divides_batch(_patch):
    _seed_inv(_patch, "flour", "Un", unit_cost=1.0)
    _seed_menu(_patch, "cake", "Kek", price=50.0)
    await _upsert(_patch, "cake", [{"inventory_item_id": "flour", "quantity": 80}], _user("admin"), portions=8)
    out = await fc.recipe_cost(menu_item_id="cake", current_user=_user("admin"))
    assert out["batch_cost"] == 80.0
    assert out["cost_per_portion"] == 10.0


async def test_get_missing_recipe_404(_patch):
    with pytest.raises(HTTPException) as exc:
        await fc.get_recipe(menu_item_id="nope", current_user=_user())
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Variance
# ---------------------------------------------------------------------------
async def test_variance_theoretical_vs_actual(_patch):
    _seed_inv(_patch, "beef", "Dana", unit_cost=0.5)
    _seed_menu(_patch, "burger", "Burger", price=120.0)
    await _upsert(
        _patch, "burger",
        [{"inventory_item_id": "beef", "quantity": 150}],
        _user("admin"), name="Burger",
    )
    # Sold 10 burgers -> theoretical 1500g beef.
    _patch.pos_orders.docs.append({
        "tenant_id": TENANT, "created_at": "2026-06-01T10:00:00",
        "items": [{"menu_item_id": "burger", "quantity": 10}],
    })
    # Actual outflow 1600g beef -> variance +100g (loss).
    _patch.inventory_movements.docs.append({
        "tenant_id": TENANT, "movement_type": "out", "timestamp": "2026-06-01T12:00:00",
        "product_id": "beef", "quantity": 1600,
    })
    out = await fc.yield_variance(
        start="2026-06-01T00:00:00", end="2026-06-01T23:59:59",
        outlet_id=None, current_user=_user("admin"),
    )
    row = next(r for r in out["rows"] if r["inventory_item_id"] == "beef")
    assert row["theoretical_qty"] == 1500.0
    assert row["actual_qty"] == 1600.0
    assert row["variance_qty"] == 100.0
    assert row["theoretical_cost"] == 750.0
    assert row["actual_cost"] == 800.0
    assert row["variance_cost"] == 50.0
    assert out["totals"]["variance_cost"] == 50.0
    assert out["totals"]["matched_order_lines"] == 1


async def test_variance_matches_by_name_when_no_menu_id(_patch):
    _seed_inv(_patch, "beef", "Dana", unit_cost=0.5)
    await _upsert(
        _patch, "burger",
        [{"inventory_item_id": "beef", "quantity": 100}],
        _user("admin"), name="Burger",
    )
    _patch.pos_orders.docs.append({
        "tenant_id": TENANT, "created_at": "2026-06-01T10:00:00",
        "items": [{"item_name": "burger", "quantity": 5}],  # no menu_item_id
    })
    out = await fc.yield_variance(
        start="2026-06-01T00:00:00", end="2026-06-01T23:59:59",
        outlet_id=None, current_user=_user("admin"),
    )
    row = next(r for r in out["rows"] if r["inventory_item_id"] == "beef")
    assert row["theoretical_qty"] == 500.0
    assert out["totals"]["matched_order_lines"] == 1


async def test_variance_out_of_window_excluded(_patch):
    _seed_inv(_patch, "beef", "Dana", unit_cost=0.5)
    await _upsert(_patch, "burger", [{"inventory_item_id": "beef", "quantity": 100}], _user("admin"), name="Burger")
    _patch.pos_orders.docs.append({
        "tenant_id": TENANT, "created_at": "2026-07-15T10:00:00",
        "items": [{"menu_item_id": "burger", "quantity": 5}],
    })
    out = await fc.yield_variance(
        start="2026-06-01T00:00:00", end="2026-06-30T23:59:59",
        outlet_id=None, current_user=_user("admin"),
    )
    assert out["totals"]["matched_order_lines"] == 0
    assert out["rows"] == []


async def test_variance_rbac_denies_guest(_patch):
    with pytest.raises(HTTPException) as exc:
        await fc.yield_variance(
            start="2026-06-01T00:00:00", end="2026-06-30T23:59:59",
            outlet_id=None, current_user=_user("guest"),
        )
    assert exc.value.status_code == 403
