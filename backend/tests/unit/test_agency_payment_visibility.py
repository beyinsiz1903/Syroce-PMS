"""The agency sees what was collected on its reservations and its credit use."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers import marketplace_b2b as m


def _cursor(rows):
    cur = SimpleNamespace(to_list=AsyncMock(return_value=rows))
    cur.sort = lambda *a, **k: cur
    return cur


@pytest.fixture
def world(monkeypatch):
    payments = [
        {"amount": 8000, "method": "cash", "payment_type": "final", "processed_at": "2026-10-15T20:00:00"},
        {"amount": 2000, "method": "city_ledger", "payment_type": "city_ledger_transfer", "processed_at": "2026-10-15T21:00:00"},
        {"amount": 500, "method": "card", "voided": True, "processed_at": "2026-10-15T22:00:00"},
        {"amount": -1000, "method": "cash", "payment_type": "refund", "status": "refunded", "processed_at": "2026-10-16T09:00:00"},
    ]
    sysdb = SimpleNamespace(
        marketplace_bookings=SimpleNamespace(find_one=AsyncMock(side_effect=lambda q, *a, **k:
            {"tenant_id": "t1", "currency": "TRY"} if q.get("agency_id") == "a1" else None)),
        agency_contracts=SimpleNamespace(find=lambda *a, **k: _cursor([
            {"tenant_id": "t1", "hotel_name": "Demo", "contract_code": "SOZ-1", "credit_limit": 10000, "credit_currency": "TRY"},
            {"tenant_id": "t2", "hotel_name": "Limitsiz", "contract_code": "SOZ-2"}])),
        agency_statements=SimpleNamespace(find=lambda *a, **k: _cursor([])),
    )
    tenant = SimpleNamespace(
        bookings=SimpleNamespace(find_one=AsyncMock(return_value={"total_amount": 10000, "balance": 0, "payment_status": "transferred", "currency": "TRY"}),
                                 find=lambda *a, **k: _cursor([{"id": "b1", "currency": "TRY", "credit_exposure_amount": 8500}])),
        payments=SimpleNamespace(find=lambda q, *a, **k: _cursor([dict(p, booking_id="b1") for p in payments])),
    )
    monkeypatch.setattr(m, "get_system_db", lambda: sysdb)
    monkeypatch.setattr(m, "db", tenant)
    monkeypatch.setattr(m, "tenant_context", lambda _t: nullcontext())
    return sysdb, tenant


@pytest.mark.asyncio
async def test_payment_history_separates_collection_transfer_refund(world):
    result = await m.agency_reservation_payments("b1", {"agency_id": "a1"})
    assert (result["collected_amount"], result["transferred_amount"], result["payment_status"]) == (7000.0, 2000.0, "transferred")
    assert [(p["label"], p["amount"], p["voided"]) for p in result["payments"]] == [
        ("Tahsilat", 8000.0, False), ("Cari hesaba aktarım", 2000.0, False), ("Tahsilat", 500.0, True), ("İade", 1000.0, False)]
    assert all("notes" not in p and "reference" not in p for p in result["payments"])


@pytest.mark.asyncio
async def test_payment_history_is_private_to_the_agency(world):
    with pytest.raises(HTTPException) as exc:
        await m.agency_reservation_payments("b1", {"agency_id": "other"})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_credit_overview_uses_money_actually_collected(world):
    hotels = (await m.agency_credit_overview({"agency_id": "a1"}))["hotels"]
    demo = next(h for h in hotels if h["tenant_id"] == "t1")["credit"]
    # 8500 net exposure - 7000 collected (transfer and voided not counted) = 1500 used
    assert demo == {"limit": 10000.0, "used": 1500.0, "available": 8500.0, "currency": "TRY"}
    assert next(h for h in hotels if h["tenant_id"] == "t2")["credit"] is None
