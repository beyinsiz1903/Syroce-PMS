"""Task #571 — process_pending_efaturas_task real-cut behaviour.

Direct-call tests for the async body ``_process_pending_efaturas_async`` with a
fake Mongo + monkeypatched provider. Verifies the doctrine:

* not configured -> fail-closed, NO writes (no fake success),
* success -> official ETTN stored + status 'generated' + record mirrored,
* transient failure -> kept 'pending', attempts incremented, no alert,
* persistent failure (>= cap) -> status 'error' + ops alert dispatched.
"""
from unittest.mock import AsyncMock

import pytest

import celery_tasks
from core import efatura_provider as ep

pytestmark = pytest.mark.asyncio


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def limit(self, _n):
        return self

    async def to_list(self, _n):
        return list(self._docs)


class _Collection:
    def __init__(self, docs=None):
        self.docs = docs or []
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
        from types import SimpleNamespace
        return SimpleNamespace(matched_count=1, modified_count=1)


class _DB:
    def __init__(self, invoices):
        self.accounting_invoices = _Collection(invoices)
        self.efatura_records = _Collection([])


class _Client:
    async def close(self):
        pass


def _patch_db(monkeypatch, invoices):
    db = _DB(invoices)
    monkeypatch.setattr(celery_tasks, "get_db", lambda: (db, _Client()))
    return db


def _configure(monkeypatch):
    monkeypatch.setenv("EFATURA_PROVIDER", "generic")
    monkeypatch.setenv("EFATURA_PROVIDER_URL", "https://p.example.com/cut")
    monkeypatch.setenv("EFATURA_PROVIDER_API_KEY", "k")
    monkeypatch.setenv("EFATURA_SUPPLIER_VKN", "1234567890")
    monkeypatch.setenv("EFATURA_SUPPLIER_NAME", "Otel")
    monkeypatch.setenv("EFATURA_MAX_ATTEMPTS", "3")


def _invoice(**over):
    base = {
        "id": "inv-1",
        "tenant_id": "t-1",
        "invoice_number": "INV-1",
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


async def test_fail_closed_when_not_configured(monkeypatch):
    for k in ("EFATURA_PROVIDER_URL", "EFATURA_PROVIDER_API_KEY", "EFATURA_SUPPLIER_VKN"):
        monkeypatch.delenv(k, raising=False)
    db = _patch_db(monkeypatch, [_invoice()])

    out = await celery_tasks._process_pending_efaturas_async()

    assert out["success"] is False
    assert out["reason"] == "not_configured"
    # No fake success written anywhere.
    assert db.accounting_invoices.updates == []
    assert db.efatura_records.upserts == []
    assert db.accounting_invoices.docs[0]["efatura_status"] == "pending"


async def test_success_stores_official_ettn(monkeypatch):
    _configure(monkeypatch)
    db = _patch_db(monkeypatch, [_invoice()])

    async def fake_submit(**kw):
        return {"official_id": "OFFICIAL-42", "status": "accepted", "provider": "generic", "raw": {}}

    monkeypatch.setattr(ep, "submit_document", fake_submit)

    out = await celery_tasks._process_pending_efaturas_async()

    assert out["success"] is True
    assert out["processed"] == 1
    doc = db.accounting_invoices.docs[0]
    assert doc["efatura_status"] == "generated"
    assert doc["efatura_uuid"] == "OFFICIAL-42"
    assert doc["efatura_official_number"] == "OFFICIAL-42"
    assert doc["efatura_last_error"] is None
    # Mirror written to efatura_records.
    assert len(db.efatura_records.upserts) == 1


async def test_transient_failure_keeps_pending_no_alert(monkeypatch):
    _configure(monkeypatch)
    db = _patch_db(monkeypatch, [_invoice(efatura_attempts=0)])

    async def fake_submit(**kw):
        raise ep.EFaturaSubmissionError("provider HTTP 503")

    monkeypatch.setattr(ep, "submit_document", fake_submit)
    alert = AsyncMock()
    monkeypatch.setattr(celery_tasks, "_dispatch_efatura_alert", alert)

    out = await celery_tasks._process_pending_efaturas_async()

    assert out["failed"] == 1
    assert out["errored"] == 0
    doc = db.accounting_invoices.docs[0]
    assert doc["efatura_status"] == "pending"  # still retryable
    assert doc["efatura_attempts"] == 1
    assert "503" in doc["efatura_last_error"]
    alert.assert_not_awaited()


async def test_persistent_failure_marks_error_and_alerts(monkeypatch):
    _configure(monkeypatch)  # cap = 3
    db = _patch_db(monkeypatch, [_invoice(efatura_attempts=2)])

    async def fake_submit(**kw):
        raise ep.EFaturaSubmissionError("provider HTTP 500")

    monkeypatch.setattr(ep, "submit_document", fake_submit)
    alert = AsyncMock()
    monkeypatch.setattr(celery_tasks, "_dispatch_efatura_alert", alert)

    out = await celery_tasks._process_pending_efaturas_async()

    assert out["errored"] == 1
    doc = db.accounting_invoices.docs[0]
    assert doc["efatura_status"] == "error"
    assert doc["efatura_attempts"] == 3
    alert.assert_awaited_once()
