from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers.reports_pkg import standard_reports


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return self.rows


@pytest.mark.asyncio
async def test_revenue_report_includes_unabsorbed_manual_extra_categories(monkeypatch):
    folio_charges = SimpleNamespace(
        find=lambda *_args, **_kwargs: _Cursor([
            {"charge_category": "room", "total": 1000},
        ])
    )
    extra_charges = SimpleNamespace(
        find=lambda *_args, **_kwargs: _Cursor([
            {"category": "room", "total": 2000},
            {"category": "minibar", "charge_amount": 250},
            {"category": "spa", "amount": 500},
        ])
    )
    pos_orders = SimpleNamespace(find=lambda *_args, **_kwargs: _Cursor([]))
    bookings = SimpleNamespace(count_documents=AsyncMock(return_value=1))
    monkeypatch.setattr(
        standard_reports,
        "db",
        SimpleNamespace(folio_charges=folio_charges, extra_charges=extra_charges, pos_orders=pos_orders, bookings=bookings),
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
            {"charge_category": "room", "total": 5000, "currency": "TRY"},
            {"charge_category": "room", "total": 100, "currency": "EUR"},
        ])
    )
    empty = SimpleNamespace(find=lambda *_args, **_kwargs: _Cursor([]))
    bookings = SimpleNamespace(count_documents=AsyncMock(return_value=2))
    monkeypatch.setattr(
        standard_reports,
        "db",
        SimpleNamespace(folio_charges=folio_charges, extra_charges=empty, pos_orders=empty, bookings=bookings),
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
    assert result["total_revenue_by_currency"] == {"TRY": 5000.0, "EUR": 100.0}
    assert result["room_nights_sold"] == 2
    assert result["adr_by_currency"] == {"TRY": 2500.0, "EUR": 50.0}
    assert result["mixed_currency"] is True
