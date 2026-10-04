from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers.reports_pkg import standard_reports


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.limits = []

    async def to_list(self, limit):
        self.limits.append(limit)
        return self.rows


@pytest.mark.asyncio
async def test_daily_summary_never_silently_caps_bookings_or_payments(monkeypatch):
    booking_cursor = _Cursor([])
    payment_cursor = _Cursor([])
    monkeypatch.setattr(
        standard_reports,
        "db",
        SimpleNamespace(
            bookings=SimpleNamespace(find=lambda *_args, **_kwargs: booking_cursor),
            payments=SimpleNamespace(find=lambda *_args, **_kwargs: payment_cursor),
        ),
    )
    monkeypatch.setattr(
        standard_reports,
        "load_stay_night_metrics",
        AsyncMock(return_value=[{"occupied_rooms": 0, "total_rooms": 10}]),
    )
    monkeypatch.setattr(standard_reports, "_posted_revenue_rows", AsyncMock(return_value=[]))

    result = await standard_reports.get_daily_summary(
        date_str="2026-10-02",
        current_user=SimpleNamespace(tenant_id="tenant-a"),
        _=None,
        _perm=None,
        _nocache=True,
    )

    assert result["date"] == "2026-10-02"
    assert booking_cursor.limits == [None]
    assert payment_cursor.limits == [None]


@pytest.mark.asyncio
async def test_daily_summary_shows_gross_correction_and_net_revenue_separately(monkeypatch):
    booking_cursor = _Cursor([])
    payment_cursor = _Cursor([
        {
            "amount": 125.5,
            "currency": "TRY",
            "method": "discount",
            "payment_type": "rate_correction",
            "status": "paid",
        },
    ])
    monkeypatch.setattr(
        standard_reports,
        "db",
        SimpleNamespace(
            bookings=SimpleNamespace(find=lambda *_args, **_kwargs: booking_cursor),
            payments=SimpleNamespace(find=lambda *_args, **_kwargs: payment_cursor),
        ),
    )
    monkeypatch.setattr(
        standard_reports,
        "load_stay_night_metrics",
        AsyncMock(return_value=[{"occupied_rooms": 0, "total_rooms": 10}]),
    )
    monkeypatch.setattr(
        standard_reports,
        "_posted_revenue_rows",
        AsyncMock(return_value=[{"total": 1000, "currency": "TRY"}]),
    )

    result = await standard_reports.get_daily_summary(
        date_str="2026-10-02",
        current_user=SimpleNamespace(tenant_id="tenant-a"),
        _=None,
        _perm=None,
        _nocache=True,
    )

    assert result["gross_posted_revenue_by_currency"] == {"TRY": 1000.0}
    assert result["revenue_adjustments_by_currency"] == {"TRY": 125.5}
    assert result["daily_revenue_by_currency"] == {"TRY": 874.5}
