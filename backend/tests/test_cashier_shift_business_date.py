from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from routers.finance import mobile


class _EmptyCursor:
    async def to_list(self, length):
        assert length is None  # Financial totals must not silently cap rows.
        return []

    def __aiter__(self):
        async def _iterate():
            if False:
                yield None

        return _iterate()


class _Payments:
    def __init__(self):
        self.query = None

    def find(self, query):
        self.query = query
        return _EmptyCursor()


@pytest.mark.asyncio
@pytest.mark.parametrize("shift_date, expected_day", [(None, "2026-10-02"), ("2026-10-03", "2026-10-03")])
async def test_cashier_shift_defaults_to_open_accounting_day(monkeypatch, shift_date, expected_day):
    payments = _Payments()
    monkeypatch.setattr(mobile, "db", SimpleNamespace(payments=payments))

    async def current_user(_credentials):
        return SimpleNamespace(tenant_id="tenant-1")

    async def business_day(_db, _tenant_id):
        return {"business_date": "2026-10-02"}

    monkeypatch.setattr(mobile, "get_current_user", current_user)
    monkeypatch.setattr(mobile, "ensure_business_date_initialized", business_day)

    result = await mobile.get_cashier_shift_report(shift_date=shift_date, credentials=None)

    assert result["shift_date"] == expected_day
    assert payments.query["tenant_id"] == "tenant-1"
    start = datetime.fromisoformat(expected_day).replace(tzinfo=UTC)
    after = start + timedelta(days=1)
    assert payments.query["$or"][0] == {"business_date": {"$gte": expected_day, "$lt": after.date().isoformat()}}
    assert {"business_date": {"$gte": start, "$lt": after}} in payments.query["$or"]
