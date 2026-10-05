from types import SimpleNamespace

import pytest

from domains.pms.dashboard_router import dashboard_core


class _Cursor:
    async def to_list(self, _limit):
        return []


class _AggregateCollection:
    def __init__(self):
        self.pipelines = []

    def aggregate(self, pipeline):
        self.pipelines.append(pipeline)
        return _Cursor()


class _Bookings:
    def __init__(self):
        self.query = None

    def find(self, query, _projection):
        self.query = query
        return _Cursor()


@pytest.mark.asyncio
async def test_budget_actual_covers_the_full_month_and_crossing_stays(monkeypatch):
    charges = _AggregateCollection()
    expenses = _AggregateCollection()
    bookings = _Bookings()
    monkeypatch.setattr(
        dashboard_core,
        "db",
        SimpleNamespace(
            budgets=SimpleNamespace(find_one=lambda _query: _none()),
            folio_charges=charges,
            expenses=expenses,
            rooms=SimpleNamespace(count_documents=lambda _query: _zero()),
            bookings=bookings,
        ),
    )

    await dashboard_core.get_budget_vs_actual(
        month="2026-02", current_user=SimpleNamespace(tenant_id="tenant-1")
    )

    charge_match = charges.pipelines[0][0]["$match"]
    assert charge_match["voided"] == {"$ne": True}
    assert charge_match["date"] == {"$gte": "2026-02-01T00:00:00+00:00", "$lt": "2026-03-01T00:00:00+00:00"}
    assert bookings.query["check_in"] == {"$lt": "2026-03-01T00:00:00+00:00"}
    assert bookings.query["check_out"] == {"$gt": "2026-02-01T00:00:00+00:00"}


async def _none():
    return None


async def _zero():
    return 0
