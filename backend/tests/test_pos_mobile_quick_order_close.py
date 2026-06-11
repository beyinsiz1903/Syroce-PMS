"""Task #355 — Mobile quick-order → close_order MUST collect a non-zero amount.

Task #353 made the mobile quick-order endpoint write canonical POS fields
(`grand_total`, `total_amount`, `tax_amount`, `payment_status`) onto the
`pos_orders` doc. Without them the shared close-order flow — which reads
`grand_total` — wrote a ZERO-amount `pos_transactions` row, i.e. a silent
0 TL collection.

These regression tests lock the invariant end-to-end: an order OPENED through
the mobile quick-order endpoint, when CLOSED via `close_order` (cash and card),
must produce a `pos_transactions` row with `status='completed'` and
`amount`/`total_amount` equal to the order's NON-ZERO `grand_total`, with the
correct `payment_method` recorded, and an `idempotency_key` replay must NOT
create a second payment.

Backend is NOT relaxed — these follow the FakeColl pattern of
`test_pos_close_order_terminal_state.py` / `test_pos_close_order_recipe_stock.py`.
"""
from types import SimpleNamespace

import pytest

from domains.pms.mobile_router import pos as mobile_pos
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


def _build_db(**overrides):
    db = SimpleNamespace(
        pos_outlets=InMemoryCollection(),
        pos_menu_items=InMemoryCollection(),
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


def _ctx(tenant_id="t1"):
    return SimpleNamespace(
        tenant_id=tenant_id,
        actor_id="u1",
        actor_email="u1@hotel.test",
        actor_role="admin",
        actor_is_super_admin=False,
    )


def _svc(db):
    svc = PosFnbServiceV2()
    svc._db = db
    return svc


async def _open_quick_order(db, monkeypatch, *, items, outlet_id="out1", tenant_id="t1"):
    """Open an order through the REAL mobile quick-order endpoint.

    Exercising the actual endpoint (not a hand-built doc) is what protects the
    invariant: if quick-order ever stops writing `grand_total`, the close path
    below collects 0 and the assertions fail.
    """
    monkeypatch.setattr(mobile_pos, "db", db)

    async def _fake_user(_credentials):
        return SimpleNamespace(
            tenant_id=tenant_id, username="mobiler", user_id="u1"
        )

    monkeypatch.setattr(mobile_pos, "get_current_user", _fake_user)

    req = mobile_pos.QuickOrderRequest(
        outlet_id=outlet_id,
        table_number="5",
        items=[
            mobile_pos.QuickOrderItem(item_id=i["item_id"], quantity=i["quantity"])
            for i in items
        ],
    )
    # Dependencies (`credentials`, `_perm`) are injected by FastAPI at runtime;
    # calling the coroutine directly bypasses them, so pass placeholders.
    resp = await mobile_pos.create_quick_order_mobile(req, credentials=None, _perm=None)
    return resp["order_id"]


def _seeded_db():
    return _build_db(
        pos_outlets=InMemoryCollection([
            {"id": "out1", "tenant_id": "t1", "name": "Lobby Bar"},
        ]),
        pos_menu_items=InMemoryCollection([
            {"id": "m1", "tenant_id": "t1", "name": "Burger", "price": 100.0},
        ]),
    )


# subtotal 200 (100 * 2) → tax 36 (18%) → grand_total 236
_EXPECTED_GRAND_TOTAL = 236.0


async def test_quick_order_then_close_cash_collects_grand_total(monkeypatch):
    db = _seeded_db()
    order_id = await _open_quick_order(
        db, monkeypatch, items=[{"item_id": "m1", "quantity": 2}]
    )

    # Guard the Task #353 invariant directly on the stored doc.
    order_doc = await db.pos_orders.find_one({"id": order_id, "tenant_id": "t1"})
    assert order_doc["grand_total"] == _EXPECTED_GRAND_TOTAL
    assert order_doc["grand_total"] > 0
    assert order_doc["payment_status"] == "unpaid"

    svc = _svc(db)
    result = await svc.close_order(_ctx(), order_id=order_id, payment_method="cash")
    assert result.ok is True

    txns = db.pos_transactions.docs
    assert len(txns) == 1
    txn = txns[0]
    assert txn["status"] == "completed"
    assert txn["payment_method"] == "cash"
    # The collected amount must equal the order grand_total — NOT zero.
    assert txn["amount"] == _EXPECTED_GRAND_TOTAL
    assert txn["total_amount"] == _EXPECTED_GRAND_TOTAL
    assert txn["amount"] > 0

    closed = await db.pos_orders.find_one({"id": order_id, "tenant_id": "t1"})
    assert closed["status"] == "closed"
    assert closed["payment_status"] == "paid"
    assert closed["payment_method"] == "cash"


async def test_quick_order_then_close_card_collects_grand_total(monkeypatch):
    db = _seeded_db()
    order_id = await _open_quick_order(
        db, monkeypatch, items=[{"item_id": "m1", "quantity": 2}]
    )

    svc = _svc(db)
    result = await svc.close_order(_ctx(), order_id=order_id, payment_method="card")
    assert result.ok is True

    txns = db.pos_transactions.docs
    assert len(txns) == 1
    txn = txns[0]
    assert txn["status"] == "completed"
    assert txn["payment_method"] == "card"
    assert txn["amount"] == _EXPECTED_GRAND_TOTAL
    assert txn["total_amount"] == _EXPECTED_GRAND_TOTAL
    assert txn["amount"] > 0


async def test_quick_order_close_idempotent_no_double_charge(monkeypatch):
    db = _seeded_db()
    order_id = await _open_quick_order(
        db, monkeypatch, items=[{"item_id": "m1", "quantity": 2}]
    )

    svc = _svc(db)
    first = await svc.close_order(
        _ctx(),
        order_id=order_id,
        payment_method="cash",
        idempotency_key="idem-1",
    )
    assert first.ok is True
    assert len(db.pos_transactions.docs) == 1

    # Replay with the SAME idempotency_key → no second transaction.
    second = await svc.close_order(
        _ctx(),
        order_id=order_id,
        payment_method="cash",
        idempotency_key="idem-1",
    )
    assert second.ok is True
    assert second.data.get("idempotent") is True
    assert len(db.pos_transactions.docs) == 1  # still exactly one collection
