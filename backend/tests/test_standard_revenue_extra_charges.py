from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers.reports_pkg import standard_reports


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.limits = []

    async def to_list(self, _limit):
        self.limits.append(_limit)
        return self.rows


@pytest.fixture(autouse=True)
def configured_reporting_currency(monkeypatch):
    from modules.pms_core import property_reporting_currency
    from modules.pms_core.property_reporting_currency import HistoricalRates
    # These adapter fixtures intentionally omit a real rate store.
    monkeypatch.setattr(property_reporting_currency, "load_historical_rates", AsyncMock(return_value=HistoricalRates("TRY")))


@pytest.mark.asyncio
async def test_revenue_report_includes_unabsorbed_manual_extra_categories(monkeypatch):
    folio_charges = SimpleNamespace(
        find=lambda *_args, **_kwargs: _Cursor([
            {"charge_category": "room", "total": 1000, "business_date": "2026-09-26", "currency": "TRY"},
        ])
    )
    extra_charges = SimpleNamespace(
        find=lambda *_args, **_kwargs: _Cursor([
            {"category": "room", "total": 2000, "business_date": "2026-09-26", "currency": "TRY"},
            {"category": "minibar", "charge_amount": 250, "business_date": "2026-09-26", "currency": "TRY"},
            {"category": "spa", "amount": 500, "business_date": "2026-09-26", "currency": "TRY"},
        ])
    )
    pos_orders = SimpleNamespace(find=lambda *_args, **_kwargs: _Cursor([]))
    bookings = SimpleNamespace(count_documents=AsyncMock(return_value=1))
    monkeypatch.setattr(
        standard_reports,
        "db",
        SimpleNamespace(folio_charges=folio_charges, extra_charges=extra_charges, pos_orders=pos_orders, bookings=bookings,
            pos_transactions=pos_orders, pos_menu_transactions=pos_orders, transactions=pos_orders),
    )
    monkeypatch.setattr(
        standard_reports,
        "load_stay_night_metrics",
        AsyncMock(return_value=[{"occupied_rooms": 1, "sold_rooms": 1, "total_rooms": 10}]),
    )

    result = await standard_reports.get_revenue_report(
        start_date="2026-09-26",
        end_date="2026-09-26",
        current_user=SimpleNamespace(tenant_id="tenant-a"),
        _=None,
        _perm=None,
        _nocache=True,
    )

    assert result["revenue_by_type"] == {"room": 3000.0, "minibar": 250.0, "spa": 500.0}
    assert result["total_revenue"] == 3750.0
    assert result["revenue_basis"] == "posted_folio_and_reservation_charges"


@pytest.mark.asyncio
async def test_revenue_report_never_adds_unlike_currencies_and_excludes_comp_from_adr(monkeypatch):
    folio_charges = SimpleNamespace(
        find=lambda *_args, **_kwargs: _Cursor([
            {"charge_category": "room", "total": 5000, "currency": "TRY", "business_date": "2026-10-01"},
            {"charge_category": "room", "total": 100, "currency": "EUR", "business_date": "2026-10-01"},
        ])
    )
    empty = SimpleNamespace(find=lambda *_args, **_kwargs: _Cursor([]))
    bookings = SimpleNamespace(count_documents=AsyncMock(return_value=2))
    monkeypatch.setattr(
        standard_reports,
        "db",
        SimpleNamespace(folio_charges=folio_charges, extra_charges=empty, pos_orders=empty, bookings=bookings,
            pos_transactions=empty, pos_menu_transactions=empty, transactions=empty),
    )
    monkeypatch.setattr(
        standard_reports,
        "load_stay_night_metrics",
        AsyncMock(return_value=[{"occupied_rooms": 5, "sold_rooms": 2, "total_rooms": 17}]),
    )

    result = await standard_reports.get_revenue_report(
        start_date="2026-10-01",
        end_date="2026-10-01",
        current_user=SimpleNamespace(tenant_id="tenant-a"),
        _=None,
        _perm=None,
        _nocache=True,
    )

    assert result["total_revenue"] is None
    assert result["total_revenue_by_currency"] == {"TRY": None}
    assert result["original_currency_breakdown"]["EUR"]["total"] == 100
    assert result["room_nights_sold"] == 2
    assert result["adr_by_currency"] == {"TRY": None}
    assert result["mixed_currency"] is False


@pytest.mark.asyncio
async def test_posted_revenue_rows_never_silently_caps_financial_ledger_rows(monkeypatch):
    folio_cursor = _Cursor([])
    extra_cursor = _Cursor([])
    pos_cursor = _Cursor([])
    monkeypatch.setattr(
        standard_reports,
        "db",
        SimpleNamespace(
            folio_charges=SimpleNamespace(find=lambda *_args, **_kwargs: folio_cursor),
            extra_charges=SimpleNamespace(find=lambda *_args, **_kwargs: extra_cursor),
            pos_orders=SimpleNamespace(find=lambda *_args, **_kwargs: pos_cursor),
            pos_transactions=SimpleNamespace(find=lambda *_args, **_kwargs: _Cursor([])),
            pos_menu_transactions=SimpleNamespace(find=lambda *_args, **_kwargs: _Cursor([])),
            transactions=SimpleNamespace(find=lambda *_args, **_kwargs: _Cursor([])),
        ),
    )

    await standard_reports._posted_revenue_rows(
        "tenant-a",
        standard_reports.date(2026, 10, 1),
        standard_reports.date(2026, 10, 2),
    )

    assert folio_cursor.limits == [None]
    assert extra_cursor.limits == [None]
    assert pos_cursor.limits == [None]
