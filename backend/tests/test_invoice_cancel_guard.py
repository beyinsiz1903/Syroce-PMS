"""Cancelled-reservation fiscal-document guard (shared_kernel.invoice_guards)
plus the Celery e-Fatura sweep's terminal-fail behaviour for cancelled bookings.

Doctrine verified here:

* ONLY a positively-cancelled reservation blocks an invoice / e-Fatura cut,
* no_show penalty / checked_out invoicing stays ALLOWED,
* a missing / cross-tenant / id-less booking is treated as invoiceable (manual
  and legacy invoices must keep working; we never read across tenants),
* the off-hot-path sweep terminal-fails a cancelled invoice ('error') WITHOUT
  building XML and WITHOUT a fake success, while an active booking is processed
  normally.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import celery_tasks
from core import efatura_provider as ep
from shared_kernel import invoice_guards as ig


# ── invoice_guards unit tests ────────────────────────────────────────────────
class _Bookings:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, filt, proj=None):
        for d in self.docs:
            if d.get("id") == filt.get("id") and d.get("tenant_id") == filt.get("tenant_id"):
                return dict(d)
        return None


class _GuardDB:
    def __init__(self, bookings):
        self.bookings = _Bookings(bookings)


def test_is_status_invoiceable_allows_non_cancelled():
    for status in ("checked_out", "no_show", "confirmed", "checked_in", None, ""):
        assert ig.is_status_invoiceable(status) is True


def test_is_status_invoiceable_blocks_cancelled_variants():
    for status in ("cancelled", "CANCELLED", "Cancelled", "canceled"):
        assert ig.is_status_invoiceable(status) is False


async def test_resolve_status_none_without_booking_id():
    db = _GuardDB([])
    assert await ig.resolve_booking_status(db, "t", None) is None
    assert await ig.resolve_booking_status(db, "t", "") is None


async def test_resolve_status_none_when_not_found():
    db = _GuardDB([])
    assert await ig.resolve_booking_status(db, "t", "b-x") is None


async def test_ensure_blocks_cancelled():
    db = _GuardDB([{"id": "b-1", "tenant_id": "t", "status": "cancelled"}])
    with pytest.raises(HTTPException) as exc:
        await ig.ensure_booking_invoiceable(db, "t", "b-1")
    assert exc.value.status_code == 409


async def test_ensure_allows_no_show_and_checked_out():
    db = _GuardDB([
        {"id": "b-1", "tenant_id": "t", "status": "no_show"},
        {"id": "b-2", "tenant_id": "t", "status": "checked_out"},
    ])
    await ig.ensure_booking_invoiceable(db, "t", "b-1")
    await ig.ensure_booking_invoiceable(db, "t", "b-2")


async def test_ensure_allows_missing_or_idless_booking():
    db = _GuardDB([])
    await ig.ensure_booking_invoiceable(db, "t", None)
    await ig.ensure_booking_invoiceable(db, "t", "b-missing")


async def test_ensure_is_tenant_scoped():
    # A cancelled booking owned by ANOTHER tenant must not be read across the
    # boundary -> resolves to None -> treated as invoiceable (no leak / no
    # cross-tenant 409 oracle).
    db = _GuardDB([{"id": "b-1", "tenant_id": "other", "status": "cancelled"}])
    await ig.ensure_booking_invoiceable(db, "t", "b-1")


# ── Celery sweep terminal-fail tests ─────────────────────────────────────────
class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def limit(self, _n):
        return self

    async def to_list(self, _n):
        return list(self._docs)


class _InvCollection:
    def __init__(self, docs):
        self.docs = docs
        self.updates = []
        self.upserts = []

    def find(self, _filt):
        return _Cursor(self.docs)

    async def update_one(self, filt, update, upsert=False):
        if upsert:
            self.upserts.append((filt, update))
        else:
            self.updates.append((filt, update))
            for d in self.docs:
                if d.get("id") == filt.get("id"):
                    d.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=1, modified_count=1)


class _SweepDB:
    def __init__(self, invoices, bookings):
        self.accounting_invoices = _InvCollection(invoices)
        self.efatura_records = _InvCollection([])
        self.bookings = _Bookings(bookings)


class _Client:
    async def close(self):
        pass


def _configure(monkeypatch):
    monkeypatch.setenv("EFATURA_PROVIDER", "generic")
    monkeypatch.setenv("EFATURA_SUPPLIER_VKN", "1234567890")
    monkeypatch.setenv("EFATURA_SUPPLIER_NAME", "Otel")
    monkeypatch.setenv("EFATURA_MAX_ATTEMPTS", "3")


def _invoice(**over):
    base = {
        "id": "inv-9",
        "tenant_id": "t-1",
        "invoice_number": "INV-9",
        "invoice_type": "sales",
        "efatura_status": "pending",
        "customer_name": "Ali",
        "customer_tax_number": "1234567890",
        "currency": "TRY",
        "subtotal": 100.0,
        "total_vat": 20.0,
        "total": 120.0,
        "items": [{"description": "Oda", "quantity": 1, "unit_price": 100.0,
                   "vat_rate": 20, "vat_amount": 20.0, "total": 120.0}],
    }
    base.update(over)
    return base


async def test_sweep_terminal_fails_cancelled_booking(monkeypatch):
    _configure(monkeypatch)
    db = _SweepDB(
        [_invoice(booking_id="b-1")],
        [{"id": "b-1", "tenant_id": "t-1", "status": "cancelled"}],
    )
    monkeypatch.setattr(celery_tasks, "get_db", lambda: (db, _Client()))

    built = {"called": False}

    def fake_build(*a, **kw):
        built["called"] = True
        return "<xml/>"

    monkeypatch.setattr(ep, "build_ubl_tr_document", fake_build)

    out = await celery_tasks._process_pending_efaturas_async()

    doc = db.accounting_invoices.docs[0]
    assert doc["efatura_status"] == "error"
    assert "iptal" in doc["efatura_last_error"]
    # No XML cut, no fake record written, counted as errored not processed.
    assert built["called"] is False
    assert db.efatura_records.upserts == []
    assert out["errored"] == 1
    assert out["processed"] == 0


async def test_sweep_processes_active_booking(monkeypatch):
    _configure(monkeypatch)
    db = _SweepDB(
        [_invoice(booking_id="b-2")],
        [{"id": "b-2", "tenant_id": "t-1", "status": "checked_out"}],
    )
    monkeypatch.setattr(celery_tasks, "get_db", lambda: (db, _Client()))

    out = await celery_tasks._process_pending_efaturas_async()

    doc = db.accounting_invoices.docs[0]
    assert doc["efatura_status"] == "xml_ready"
    assert out["processed"] == 1
    assert out["errored"] == 0


async def test_sweep_processes_invoice_without_booking(monkeypatch):
    _configure(monkeypatch)
    # No booking_id -> manual/legacy invoice -> guard skipped, normal cut.
    db = _SweepDB([_invoice()], [])
    monkeypatch.setattr(celery_tasks, "get_db", lambda: (db, _Client()))

    out = await celery_tasks._process_pending_efaturas_async()

    doc = db.accounting_invoices.docs[0]
    assert doc["efatura_status"] == "xml_ready"
    assert out["processed"] == 1
