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
async def test_mtd_cost_summary_never_truncates_cost_or_revenue_ledger(monkeypatch):
    purchase_cursor = _Cursor([])
    revenue_cursor = _Cursor([])
    monkeypatch.setattr(
        reports,
        "db",
        SimpleNamespace(
            purchase_orders=SimpleNamespace(find=lambda *_args, **_kwargs: purchase_cursor),
            folio_charges=SimpleNamespace(find=lambda *_args, **_kwargs: revenue_cursor),
        ),
    )
    monkeypatch.setattr(
        reports,
        "ensure_business_date_initialized",
        AsyncMock(return_value={"business_date": "2026-10-02"}),
    )
    monkeypatch.setattr(reports, "load_stay_night_metrics", AsyncMock(return_value=[]))

    await reports._compute_mtd_cost_summary("tenant-a")

    assert purchase_cursor.limits == [None]
    assert revenue_cursor.limits == [None]
