"""Task #187 — Closing a POS order decrements recipe-linked ingredient stock.

close_order must consume ingredient stock (bom_qty * ordered_qty) atomically,
tenant-scoped and overdraft-safe (never negative). Voiding/reversing an order
restores the consumed stock idempotently.
"""
from types import SimpleNamespace

from domains.pms.pos_fnb.pos_fnb_service_v2 import PosFnbServiceV2


# ── Minimal in-memory Mongo-ish collection (supports the operators used) ──
class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_a, **_kw):
        return self

    async def to_list(self, _n=None):
        return self._docs


class InMemoryCollection:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    @staticmethod
    def _match(doc, flt):
        for k, v in flt.items():
            dv = doc.get(k)
            if isinstance(v, dict):
                for op, ov in v.items():
                    if op == "$gte":
                        if dv is None or dv < ov:
                            return False
                    elif op == "$gt":
                        if dv is None or dv <= ov:
                            return False
                    elif op == "$ne":
                        if dv == ov:
                            return False
                    else:  # pragma: no cover - unexpected operator
                        raise NotImplementedError(op)
            elif dv != v:
                return False
        return True

    async def find_one(self, flt, _proj=None):
        for d in self.docs:
            if self._match(d, flt):
                return dict(d)
        return None

    def find(self, flt, _proj=None):
        return _Cursor([dict(d) for d in self.docs if self._match(d, flt)])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id="x")

    async def update_one(self, flt, update):
        for d in self.docs:
            if self._match(d, flt):
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                for k, v in update.get("$inc", {}).items():
                    d[k] = (d.get(k) or 0) + v
                return SimpleNamespace(modified_count=1, matched_count=1)
        return SimpleNamespace(modified_count=0, matched_count=0)

    async def update_many(self, flt, update):
        n = 0
        for d in self.docs:
            if self._match(d, flt):
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                n += 1
        return SimpleNamespace(modified_count=n)


def _ctx(tenant_id="t1"):
    return SimpleNamespace(
        tenant_id=tenant_id,
        actor_id="u1",
        actor_email="u1@hotel.test",
        actor_role="admin",
        actor_is_super_admin=False,
    )


def _build_db(**overrides):
    db = SimpleNamespace(
        pos_transactions=InMemoryCollection(),
        pos_orders=InMemoryCollection(),
        kitchen_orders=InMemoryCollection(),
        folios=InMemoryCollection(),
        folio_charges=InMemoryCollection(),
        table_layouts=InMemoryCollection(),
        audit_logs=InMemoryCollection(),
        recipes=InMemoryCollection(),
        ingredients=InMemoryCollection(),
        stock_consumptions=InMemoryCollection(),
    )
    for k, v in overrides.items():
        setattr(db, k, v)
    return db


def _svc(db):
    svc = PosFnbServiceV2()
    svc._db = db
    return svc


def _pending_order(items, order_id="ord1", tenant_id="t1"):
    return {
        "id": order_id,
        "tenant_id": tenant_id,
        "status": "pending",
        "payment_status": "unpaid",
        "grand_total": 100.0,
        "tax_amount": 9.0,
        "order_number": "ORD-TEST-0001",
        "outlet_id": "out1",
        "order_items": items,
    }


async def test_close_order_decrements_recipe_ingredients_by_name():
    db = _build_db(
        ingredients=InMemoryCollection([
            {"id": "ing1", "tenant_id": "t1", "name": "Tomato", "current_stock": 100.0},
        ]),
        recipes=InMemoryCollection([
            {
                "id": "rec1",
                "tenant_id": "t1",
                "dish_name": "Tomato Soup",
                "ingredients": [
                    {"ingredient_id": "ing1", "ingredient_name": "Tomato", "quantity": 2},
                ],
            },
        ]),
    )
    order = _pending_order([
        {"item_id": "m1", "item_name": "Tomato Soup", "quantity": 3},
    ])
    db.pos_orders.docs.append(dict(order))
    svc = _svc(db)

    result = await svc.close_order(_ctx(), order_id="ord1", payment_method="cash")
    assert result.ok is True

    ing = await db.ingredients.find_one({"id": "ing1", "tenant_id": "t1"})
    assert ing["current_stock"] == 94.0  # 100 - (2 * 3)

    recs = db.stock_consumptions.docs
    assert len(recs) == 1
    assert recs[0]["ingredient_id"] == "ing1"
    assert recs[0]["consumed_quantity"] == 6.0
    assert recs[0]["overdraft_quantity"] == 0.0
    assert recs[0]["reversed"] is False


async def test_close_order_matches_recipe_by_item_id():
    db = _build_db(
        ingredients=InMemoryCollection([
            {"id": "ing1", "tenant_id": "t1", "name": "Flour", "current_stock": 50.0},
        ]),
        recipes=InMemoryCollection([
            {
                "id": "rec1",
                "tenant_id": "t1",
                "menu_item_id": "m1",
                "dish_name": "Bread",
                "ingredients": [{"ingredient_id": "ing1", "quantity": 5}],
            },
        ]),
    )
    order = _pending_order([
        {"item_id": "m1", "item_name": "Different Name", "quantity": 2},
    ])
    db.pos_orders.docs.append(dict(order))
    svc = _svc(db)

    await svc.close_order(_ctx(), order_id="ord1", payment_method="cash")
    ing = await db.ingredients.find_one({"id": "ing1", "tenant_id": "t1"})
    assert ing["current_stock"] == 40.0  # 50 - (5 * 2)


async def test_close_order_overdraft_never_goes_negative():
    db = _build_db(
        ingredients=InMemoryCollection([
            {"id": "ing1", "tenant_id": "t1", "name": "Saffron", "current_stock": 5.0},
        ]),
        recipes=InMemoryCollection([
            {
                "id": "rec1",
                "tenant_id": "t1",
                "dish_name": "Paella",
                "ingredients": [{"ingredient_id": "ing1", "quantity": 6}],
            },
        ]),
    )
    order = _pending_order([
        {"item_id": "m1", "item_name": "Paella", "quantity": 1},
    ])
    db.pos_orders.docs.append(dict(order))
    svc = _svc(db)

    await svc.close_order(_ctx(), order_id="ord1", payment_method="cash")
    ing = await db.ingredients.find_one({"id": "ing1", "tenant_id": "t1"})
    assert ing["current_stock"] == 5.0  # untouched — never negative

    rec = db.stock_consumptions.docs[0]
    assert rec["consumed_quantity"] == 0.0
    assert rec["overdraft_quantity"] == 6.0


async def test_close_order_is_tenant_scoped():
    # Ingredient/recipe belong to another tenant → no decrement.
    db = _build_db(
        ingredients=InMemoryCollection([
            {"id": "ing1", "tenant_id": "other", "name": "Tomato", "current_stock": 100.0},
        ]),
        recipes=InMemoryCollection([
            {
                "id": "rec1",
                "tenant_id": "other",
                "dish_name": "Tomato Soup",
                "ingredients": [{"ingredient_id": "ing1", "quantity": 2}],
            },
        ]),
    )
    order = _pending_order([
        {"item_id": "m1", "item_name": "Tomato Soup", "quantity": 3},
    ])
    db.pos_orders.docs.append(dict(order))
    svc = _svc(db)

    await svc.close_order(_ctx(tenant_id="t1"), order_id="ord1", payment_method="cash")
    ing = await db.ingredients.find_one({"id": "ing1", "tenant_id": "other"})
    assert ing["current_stock"] == 100.0  # untouched
    assert db.stock_consumptions.docs == []


async def test_close_aggregates_shared_ingredient_across_lines():
    db = _build_db(
        ingredients=InMemoryCollection([
            {"id": "ing1", "tenant_id": "t1", "name": "Butter", "current_stock": 100.0},
        ]),
        recipes=InMemoryCollection([
            {"id": "r1", "tenant_id": "t1", "dish_name": "Croissant",
             "ingredients": [{"ingredient_id": "ing1", "quantity": 1}]},
            {"id": "r2", "tenant_id": "t1", "dish_name": "Brioche",
             "ingredients": [{"ingredient_id": "ing1", "quantity": 3}]},
        ]),
    )
    order = _pending_order([
        {"item_id": "a", "item_name": "Croissant", "quantity": 2},  # 2
        {"item_id": "b", "item_name": "Brioche", "quantity": 4},    # 12
    ])
    db.pos_orders.docs.append(dict(order))
    svc = _svc(db)

    await svc.close_order(_ctx(), order_id="ord1", payment_method="cash")
    ing = await db.ingredients.find_one({"id": "ing1", "tenant_id": "t1"})
    assert ing["current_stock"] == 86.0  # 100 - (2 + 12)
    # Aggregated into a single consumption record.
    assert len(db.stock_consumptions.docs) == 1
    assert db.stock_consumptions.docs[0]["consumed_quantity"] == 14.0


async def test_restore_recipe_stock_reverses_consumption_idempotently():
    db = _build_db(
        ingredients=InMemoryCollection([
            {"id": "ing1", "tenant_id": "t1", "name": "Tomato", "current_stock": 100.0},
        ]),
        recipes=InMemoryCollection([
            {"id": "rec1", "tenant_id": "t1", "dish_name": "Tomato Soup",
             "ingredients": [{"ingredient_id": "ing1", "quantity": 2}]},
        ]),
    )
    order = _pending_order([
        {"item_id": "m1", "item_name": "Tomato Soup", "quantity": 3},
    ])
    svc = _svc(db)

    await svc._consume_recipe_stock(_ctx(), order)
    ing = await db.ingredients.find_one({"id": "ing1", "tenant_id": "t1"})
    assert ing["current_stock"] == 94.0

    # Reverse → stock restored.
    await svc._restore_recipe_stock(_ctx(), "ord1")
    ing = await db.ingredients.find_one({"id": "ing1", "tenant_id": "t1"})
    assert ing["current_stock"] == 100.0

    # Idempotent: a second restore must not double-credit.
    await svc._restore_recipe_stock(_ctx(), "ord1")
    ing = await db.ingredients.find_one({"id": "ing1", "tenant_id": "t1"})
    assert ing["current_stock"] == 100.0
    assert db.stock_consumptions.docs[0]["reversed"] is True


async def test_void_order_restores_consumed_stock_for_pending_order():
    # A pending order that already has consumption records (e.g. from a prior
    # reversal flow) gets its stock restored on void.
    db = _build_db(
        ingredients=InMemoryCollection([
            {"id": "ing1", "tenant_id": "t1", "name": "Tomato", "current_stock": 94.0},
        ]),
        pos_orders=InMemoryCollection([
            {"id": "ord1", "tenant_id": "t1", "status": "pending",
             "payment_status": "unpaid", "outlet_id": "out1"},
        ]),
        stock_consumptions=InMemoryCollection([
            {"id": "sc1", "tenant_id": "t1", "order_id": "ord1",
             "ingredient_id": "ing1", "consumed_quantity": 6.0, "reversed": False},
        ]),
    )
    svc = _svc(db)

    result = await svc.void_order(_ctx(), order_id="ord1", reason="staff error")
    assert result.ok is True
    ing = await db.ingredients.find_one({"id": "ing1", "tenant_id": "t1"})
    assert ing["current_stock"] == 100.0  # 94 + 6 restored


async def test_close_order_no_recipe_match_is_noop():
    db = _build_db(
        ingredients=InMemoryCollection([
            {"id": "ing1", "tenant_id": "t1", "name": "Tomato", "current_stock": 100.0},
        ]),
        recipes=InMemoryCollection([
            {"id": "rec1", "tenant_id": "t1", "dish_name": "Tomato Soup",
             "ingredients": [{"ingredient_id": "ing1", "quantity": 2}]},
        ]),
    )
    order = _pending_order([
        {"item_id": "m1", "item_name": "Unlinked Coffee", "quantity": 3},
    ])
    db.pos_orders.docs.append(dict(order))
    svc = _svc(db)

    result = await svc.close_order(_ctx(), order_id="ord1", payment_method="cash")
    assert result.ok is True
    ing = await db.ingredients.find_one({"id": "ing1", "tenant_id": "t1"})
    assert ing["current_stock"] == 100.0  # nothing matched
    assert db.stock_consumptions.docs == []
