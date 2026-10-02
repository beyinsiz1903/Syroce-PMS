from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from routers.departments import reports


class _Cursor:
    def __init__(self, documents):
        self.documents = documents
        self.limits: list[int | None] = []

    async def to_list(self, length=None):
        self.limits.append(length)
        return list(self.documents)


class _Collection:
    def __init__(self, documents):
        self.cursor = _Cursor(documents)

    def find(self, *_args, **_kwargs):
        return self.cursor


@pytest.mark.asyncio
async def test_finance_snapshot_reads_complete_financial_collections(monkeypatch):
    """Dashboard totals must not silently stop at an arbitrary row count."""
    folios = _Collection([])
    payments = _Collection([])
    charges = _Collection([])
    invoices = _Collection([])
    fake_db = SimpleNamespace(
        folios=folios,
        payments=payments,
        folio_charges=charges,
        accounting_invoices=invoices,
    )
    monkeypatch.setattr(reports, "db", fake_db)
    monkeypatch.setattr(reports, "_enforce", lambda *_args, **_kwargs: None)

    async def business_date(*_args, **_kwargs):
        return {"business_date": "2026-10-02"}

    monkeypatch.setattr(reports, "ensure_business_date_initialized", business_date)

    result = await reports.get_finance_snapshot(
        current_user=SimpleNamespace(tenant_id="tenant-1", role="admin"),
    )

    assert result["accounting_invoices"] == {"pending_count": 0, "pending_total": 0}
    assert folios.cursor.limits == [None]
    assert payments.cursor.limits == [None, None]
    assert charges.cursor.limits == [None]
    assert invoices.cursor.limits == [None]
