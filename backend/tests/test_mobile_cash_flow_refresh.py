"""A real HTTP refresh must see a payment/refund despite a warm mobile cache."""
from copy import deepcopy

import httpx
from fastapi import FastAPI

import cache_manager
from routers.finance import mobile
from tests.test_finance_report_reconciliation import USER
from tests.test_finance_report_reconciliation import context as finance_context

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
context = finance_context


async def test_cash_flow_http_refresh_reconciles_after_payment_and_void(ledger_db, monkeypatch):
    values = {}
    monkeypatch.setattr(cache_manager.cache, "enabled", True)
    monkeypatch.setattr(cache_manager.cache, "get", lambda key: deepcopy(values.get(key)))
    monkeypatch.setattr(cache_manager.cache, "set", lambda key, value, **kw: values.update({key: deepcopy(value)}))
    app = FastAPI()
    app.include_router(mobile.router)
    app.dependency_overrides[mobile.get_current_user] = lambda: USER
    route = next(r for r in app.routes if r.path == "/finance/mobile/cash-flow-summary")
    for dependency in route.dependant.dependencies:
        if dependency.name == "current_user":
            app.dependency_overrides[dependency.call] = lambda: USER
        if dependency.name == "_perm":
            app.dependency_overrides[dependency.call] = lambda: None
    await ledger_db.payments.insert_one({"id": "base", "tenant_id": "A", "business_date": "2026-10-02", "amount": 100, "currency": "TRY", "method": "cash"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get("/finance/mobile/cash-flow-summary")
        assert first.status_code == 200
        assert first.json()["today"]["cash_inflow"] == 100
        await ledger_db.payments.insert_one({"id": "new", "tenant_id": "A", "business_date": "2026-10-02", "amount": 20, "currency": "TRY", "method": "cash"})
        fresh = await client.get("/finance/mobile/cash-flow-summary?nocache=1")
        assert fresh.status_code == 200
        assert fresh.json()["today"]["cash_inflow"] == 120
        assert fresh.json()["today"]["inflow_count"] == 2
        await ledger_db.payments.update_one({"id": "new"}, {"$set": {"voided": True}})
        refunded = await client.get("/finance/mobile/cash-flow-summary?nocache=1")
        assert refunded.json()["today"]["cash_inflow"] == 100
        assert refunded.json()["today"]["inflow_count"] == 1
