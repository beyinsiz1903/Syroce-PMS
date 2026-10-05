from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers.departments import reports


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.limits = []

    async def to_list(self, limit):
        self.limits.append(limit)
        return self.rows


@pytest.mark.asyncio
async def test_company_aging_does_not_cap_open_company_folios(monkeypatch):
    folio_cursor = _Cursor([])
    monkeypatch.setattr(
        reports,
        "db",
        SimpleNamespace(
            folios=SimpleNamespace(find=lambda *_args, **_kwargs: folio_cursor),
            companies=SimpleNamespace(find_one=AsyncMock()),
        ),
    )
    monkeypatch.setattr(reports, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-02"}))

    await reports._compute_company_aging("tenant-a")

    assert folio_cursor.limits == [None]


@pytest.mark.asyncio
async def test_finance_snapshot_does_not_cap_financial_source_rows(monkeypatch):
    folio_cursor = _Cursor([])
    today_payment_cursor = _Cursor([])
    mtd_payment_cursor = _Cursor([])
    charge_cursor = _Cursor([])
    invoice_cursor = _Cursor([])
    monkeypatch.setattr(
        reports,
        "db",
        SimpleNamespace(
            folios=SimpleNamespace(find=lambda *_args, **_kwargs: folio_cursor),
            payments=SimpleNamespace(
                find=lambda *_args, **_kwargs: (
                    today_payment_cursor if not today_payment_cursor.limits else mtd_payment_cursor
                )
            ),
            folio_charges=SimpleNamespace(find=lambda *_args, **_kwargs: charge_cursor),
            accounting_invoices=SimpleNamespace(find=lambda *_args, **_kwargs: invoice_cursor),
        ),
    )
    monkeypatch.setattr(reports, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": date(2026, 10, 2)}))

    await reports.get_finance_snapshot(
        current_user=SimpleNamespace(tenant_id="tenant-a", role="admin"), _perm=None
    )

    assert folio_cursor.limits == [None]
    assert today_payment_cursor.limits == [None]
    assert mtd_payment_cursor.limits == [None]
    assert charge_cursor.limits == [None]
    assert invoice_cursor.limits == [None]
