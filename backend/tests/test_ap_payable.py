"""Targeted tests for Accounts Payable (invoice ledger + payments + aging).

Pinned contract (Kademe 2):
  * paid_amount is always recomputed from ap_payments (ledger recalc), never $inc.
  * Payments are idempotent (idempotency_key); replay returns existing state.
  * Overpayment rejected; void invoice cannot receive payment; invoice with
    payments cannot be voided.
  * Status derives: open -> partial -> paid. Aging buckets by due_date vs as_of.
  * All tenant-scoped; mutations accounting-tier RBAC.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from domains.accounting import ap_router as ap


def _match(doc: dict, flt: dict) -> bool:
    for k, v in flt.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
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
    def __init__(self, name, unique_key=None):
        self.name = name
        self.docs: list[dict] = []
        self._unique_key = unique_key

    def find(self, flt=None, proj=None):
        return _Cursor([d for d in self.docs if _match(d, flt or {})])

    async def find_one(self, flt, proj=None, sort=None):
        for d in self.docs:
            if _match(d, flt):
                return {kk: vv for kk, vv in d.items() if kk != "_id"}
        return None

    async def insert_one(self, doc):
        if self._unique_key:
            a, b = self._unique_key
            if doc.get(a) is not None and doc.get(b) is not None:
                for d in self.docs:
                    if d.get(a) == doc.get(a) and d.get(b) == doc.get(b):
                        raise DuplicateKeyError("dup")
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id", "x"))

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if _match(d, flt):
                d.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


class _FakeDB:
    def __init__(self):
        self.ap_invoices = _Coll("ap_invoices")
        self.ap_payments = _Coll("ap_payments", unique_key=("tenant_id", "idempotency_key"))
        self.proc_suppliers = _Coll("proc_suppliers")
        self.proc_purchase_orders = _Coll("proc_purchase_orders")


TENANT = "tenant-A"


def _user(role="accountant", *, super_admin=False, tenant=TENANT):
    return SimpleNamespace(
        id="u1", user_id="u1", tenant_id=tenant, role=role, is_super_admin=super_admin,
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(ap, "db", fake)

    async def _noop(_tenant):
        return None

    monkeypatch.setattr(ap, "_ensure_payment_idem", _noop)
    fake.proc_suppliers.docs.append({"id": "sup1", "tenant_id": TENANT, "name": "ABC Gıda"})
    return fake


async def _mk_invoice(fake, total=1000.0, no="INV-1", user=None):
    return (await ap.create_invoice(
        ap.InvoiceIn(
            supplier_id="sup1", invoice_no=no, due_date="2026-06-01",
            subtotal=total, tax=0,
        ),
        current_user=user or _user("accountant"),
    ))["invoice"]


async def _pay(invoice_id, amount, user=None, **kw):
    return await ap.apply_payment(
        invoice_id=invoice_id,
        payload=ap.PaymentIn(amount=amount, **kw),
        current_user=user or _user("accountant"),
    )


# ---------------------------------------------------------------------------
# Invoice creation
# ---------------------------------------------------------------------------
async def test_create_invoice_rbac_denies(_patch):
    with pytest.raises(HTTPException) as exc:
        await _mk_invoice(_patch, user=_user("front_desk"))
    assert exc.value.status_code == 403


async def test_create_invoice_unknown_supplier_404(_patch):
    with pytest.raises(HTTPException) as exc:
        await ap.create_invoice(
            ap.InvoiceIn(supplier_id="ghost", invoice_no="X", due_date="2026-06-01", subtotal=10),
            current_user=_user("accountant"),
        )
    assert exc.value.status_code == 404


async def test_create_invoice_duplicate_no_rejected(_patch):
    await _mk_invoice(_patch, no="INV-1")
    with pytest.raises(HTTPException) as exc:
        await _mk_invoice(_patch, no="INV-1")
    assert exc.value.status_code == 400


async def test_create_invoice_total_includes_tax(_patch):
    inv = (await ap.create_invoice(
        ap.InvoiceIn(supplier_id="sup1", invoice_no="T1", due_date="2026-06-01",
                     subtotal=100, tax=18),
        current_user=_user("accountant"),
    ))["invoice"]
    assert inv["total_amount"] == 118.0
    assert inv["balance"] == 118.0
    assert inv["status"] == "open"


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
async def test_partial_then_full_payment_status(_patch):
    inv = await _mk_invoice(_patch, total=1000.0)
    r1 = await _pay(inv["id"], 400)
    assert r1["invoice"]["paid_amount"] == 400.0
    assert r1["invoice"]["balance"] == 600.0
    assert r1["invoice"]["status"] == "partial"
    r2 = await _pay(inv["id"], 600)
    assert r2["invoice"]["paid_amount"] == 1000.0
    assert r2["invoice"]["status"] == "paid"
    assert r2["invoice"]["balance"] == 0.0


async def test_overpayment_rejected(_patch):
    inv = await _mk_invoice(_patch, total=500.0)
    await _pay(inv["id"], 300)
    with pytest.raises(HTTPException) as exc:
        await _pay(inv["id"], 300)
    assert exc.value.status_code == 400
    # ledger unchanged beyond first payment
    inv2 = await ap.get_invoice(inv["id"], current_user=_user("accountant"))
    assert inv2["invoice"]["paid_amount"] == 300.0


async def test_payment_idempotent_replay(_patch):
    inv = await _mk_invoice(_patch, total=1000.0)
    await _pay(inv["id"], 400, idempotency_key="pmt-1")
    r2 = await _pay(inv["id"], 400, idempotency_key="pmt-1")
    assert r2.get("idempotent_replay") is True
    assert r2["invoice"]["paid_amount"] == 400.0
    assert len(_patch.ap_payments.docs) == 1


async def test_payment_recalc_not_increment(_patch):
    """paid_amount is the sum of payments, even if invoice doc said otherwise."""
    inv = await _mk_invoice(_patch, total=1000.0)
    await _pay(inv["id"], 200)
    await _pay(inv["id"], 300)
    final = await ap.get_invoice(inv["id"], current_user=_user("accountant"))
    assert final["invoice"]["paid_amount"] == 500.0
    assert len(final["payments"]) == 2


async def test_void_blocked_with_payments(_patch):
    inv = await _mk_invoice(_patch, total=1000.0)
    await _pay(inv["id"], 100)
    with pytest.raises(HTTPException) as exc:
        await ap.void_invoice(inv["id"], current_user=_user("accountant"))
    assert exc.value.status_code == 409


async def test_payment_on_void_blocked(_patch):
    inv = await _mk_invoice(_patch, total=1000.0)
    await ap.void_invoice(inv["id"], current_user=_user("accountant"))
    with pytest.raises(HTTPException) as exc:
        await _pay(inv["id"], 100)
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# Aging
# ---------------------------------------------------------------------------
async def test_aging_buckets(_patch):
    # due 2026-06-01; as_of 2026-06-20 -> 19 days overdue (d1_30)
    inv = await _mk_invoice(_patch, total=1000.0, no="A1")
    await _pay(inv["id"], 200)  # balance 800 -> partial
    # second invoice due far future -> current
    fut = (await ap.create_invoice(
        ap.InvoiceIn(supplier_id="sup1", invoice_no="A2", due_date="2026-12-31", subtotal=500),
        current_user=_user("accountant"),
    ))["invoice"]
    assert fut["status"] == "open"
    out = await ap.aging(as_of="2026-06-20", current_user=_user("accountant"))
    assert out["buckets"]["d1_30"] == 800.0
    assert out["buckets"]["current"] == 500.0
    assert out["total_outstanding"] == 1300.0
    assert out["by_supplier"][0]["supplier_id"] == "sup1"
