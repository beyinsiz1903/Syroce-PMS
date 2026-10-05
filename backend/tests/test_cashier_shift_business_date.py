from types import SimpleNamespace

import pytest

from routers.finance import mobile


class _EmptyCursor:
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
async def test_cashier_shift_defaults_to_open_accounting_day(monkeypatch):
    payments = _Payments()
    monkeypatch.setattr(mobile, "db", SimpleNamespace(payments=payments))

    async def current_user(_credentials):
        return SimpleNamespace(tenant_id="tenant-1")

    async def business_day(_db, _tenant_id):
        return {"business_date": "2026-10-02"}

    monkeypatch.setattr(mobile, "get_current_user", current_user)
    monkeypatch.setattr(mobile, "ensure_business_date_initialized", business_day)

    result = await mobile.get_cashier_shift_report(credentials=None)

    assert result["shift_date"] == "2026-10-02"
    assert payments.query["$or"][0] == {"business_date": "2026-10-02"}
