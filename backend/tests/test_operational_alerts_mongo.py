"""Real Mongo query acceptance; the reused fixture permits localhost only."""
# ruff: noqa: F811

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers import pms_dashboard
from tests.test_report_ledger_mongo_acceptance import ledger_db  # noqa: F401


@pytest.mark.asyncio
async def test_real_ledger_queries_include_paid_stay_extras_and_legacy_rows_without_cross_tenant_leak(ledger_db, monkeypatch):
    database = ledger_db
    await database.bookings.insert_many([
        {"tenant_id": "A", "id": "prepaid", "status": "checked_in", "check_out": "2026-10-26T12:00:00+03:00",
         "total_amount": 100, "paid_amount": 100, "currency": "TRY"},
        {"tenant_id": "A", "id": "foreign-currency", "status": "checked_in", "check_out": "2026-10-27",
         "total_amount": 560, "paid_amount": 0, "currency": "USD"},
        {"tenant_id": "B", "id": "prepaid", "status": "checked_in", "check_out": "2026-10-26",
         "total_amount": 999999, "currency": "TRY"},
    ])
    await database.folios.insert_one({"tenant_id": "A", "id": "f1", "booking_id": "prepaid"})
    await database.folio_charges.insert_many([
        {"tenant_id": "A", "folio_id": "f1", "total": 100, "charge_type": "room_charge"},
        {"tenant_id": "A", "folio_id": "f1", "total": 25},
        {"tenant_id": "A", "booking_id": "foreign-currency", "total": 78.8, "currency": "USD"},
        {"tenant_id": "A", "booking_id": "foreign-currency", "total": 3.75, "currency": "USD"},
        {"tenant_id": "B", "booking_id": "prepaid", "folio_id": "f1", "total": 999999},
    ])
    await database.payments.insert_one({"tenant_id": "A", "folio_id": "f1", "amount": 100})
    monkeypatch.setattr(pms_dashboard, "db", database)
    monkeypatch.setattr(pms_dashboard, "_open_business_date", AsyncMock(return_value="2026-10-26"))
    monkeypatch.setattr(pms_dashboard, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setitem(sys.modules, "redis_cache", SimpleNamespace(redis_cache=None))

    result = await pms_dashboard.get_operational_alerts(SimpleNamespace(tenant_id="A"))
    pending = next(alert for alert in result["alerts"] if alert["type"] == "pending_payments")
    departing = next(alert for alert in result["alerts"] if alert["type"] == "departures_with_balance")
    assert {item["booking_id"]: item["balance"] for item in pending["items"]} == {"prepaid": 25, "foreign-currency": 642.55}
    assert result["summary"]["outstanding_by_currency"] == {"TRY": 25, "USD": 642.55}
    assert result["summary"]["total_outstanding"] is None
    assert departing["count"] == 1 and departing["items"][0]["booking_id"] == "prepaid"
