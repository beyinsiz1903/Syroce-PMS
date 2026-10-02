from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from routers.departments import reports


class _Cursor:
    def __init__(self, limits: list[int | None]):
        self.limits = limits

    async def to_list(self, length=None):
        self.limits.append(length)
        return []


class _Collection:
    def __init__(self):
        self.limits: list[int | None] = []

    def find(self, *_args, **_kwargs):
        return _Cursor(self.limits)


@pytest.mark.asyncio
async def test_mtd_cost_summary_reads_all_cost_and_revenue_rows(monkeypatch):
    purchase_orders = _Collection()
    folio_charges = _Collection()
    monkeypatch.setattr(
        reports,
        "db",
        SimpleNamespace(purchase_orders=purchase_orders, folio_charges=folio_charges),
    )

    async def business_day(*_args, **_kwargs):
        return {"business_date": "2026-10-02"}

    async def stay_metrics(*_args, **_kwargs):
        return [{"occupied_rooms": 0, "total_rooms": 0}]

    monkeypatch.setattr(reports, "ensure_business_date_initialized", business_day)
    monkeypatch.setattr(reports, "load_stay_night_metrics", stay_metrics)

    result = await reports._compute_mtd_cost_summary("tenant-1")

    assert result["total_mtd_costs"] == 0
    assert result["financial_metrics"]["mtd_revenue"] == 0
    assert purchase_orders.limits == [None]
    assert folio_charges.limits == [None]
