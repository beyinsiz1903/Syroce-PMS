from __future__ import annotations

from types import SimpleNamespace

import pytest

from routers import eod_report


class _Cursor:
    def __init__(self, limits: list[int | None]):
        self.limits = limits

    async def to_list(self, length=None):
        self.limits.append(length)
        return []


class _FinancialCollection:
    def __init__(self):
        self.limits: list[int | None] = []

    def find(self, *_args, **_kwargs):
        return _Cursor(self.limits)


@pytest.mark.asyncio
async def test_eod_collect_does_not_truncate_financial_totals(monkeypatch):
    payments = _FinancialCollection()
    extras = _FinancialCollection()
    charges = _FinancialCollection()
    counts = SimpleNamespace(count_documents=lambda *_args, **_kwargs: _zero())
    fake_db = SimpleNamespace(
        bookings=counts,
        payments=payments,
        extra_charges=extras,
        folio_charges=charges,
        folios=counts,
        shift_handovers=counts,
    )
    monkeypatch.setattr(eod_report, "db", fake_db)
    monkeypatch.setattr(eod_report, "load_stay_night_metrics", _empty_metrics)
    monkeypatch.setattr(eod_report, "get_tenant_currency", _tenant_currency)

    result = await eod_report._collect("tenant-1", "2026-10-02")

    assert result["payments_total"] == 0
    assert payments.limits == [None]
    assert extras.limits == [None]
    assert charges.limits == [None]


async def _zero():
    return 0


async def _empty_metrics(*_args, **_kwargs):
    return [{"total_rooms": 0, "occupied_rooms": 0, "occupancy_rate": 0}]


async def _tenant_currency(*_args, **_kwargs):
    return "TRY", None
