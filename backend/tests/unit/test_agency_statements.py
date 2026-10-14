"""Period statement rules: who owes whom, penalties, payments, status guards."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.agency_statements import outstanding, penalty_amount, statement_line, statement_totals
from routers import agency_statements

BASE = {"id": "b1", "confirmation_code": "MKT-1", "check_in": "2026-11-20", "check_out": "2026-11-22",
        "total_amount": 1000, "commission_pct": 15, "syroce_b2b_fee_pct": 2,
        "cancellation_policy": {"free_until_days_before": 7, "penalty_pct": 50, "no_show_penalty_pct": 100}}


def test_on_arrival_stay_hotel_owes_commission():
    line = statement_line({**BASE, "status": "checked_out", "payment_terms": "on_arrival"}, None)
    assert (line["gross"], line["commission"], line["platform_fee"], line["net_to_hotel"]) == (1000, 150, 20, 850)
    assert (line["hotel_owes_agency"], line["agency_owes_hotel"]) == (150, 0)


def test_prepaid_stay_agency_owes_net():
    line = statement_line({**BASE, "status": "confirmed", "payment_terms": "prepaid"}, None)
    assert (line["hotel_owes_agency"], line["agency_owes_hotel"]) == (0, 850)


@pytest.mark.parametrize("cancelled_at,expected", [("2026-11-01", 0.0), ("2026-11-15", 500.0), (None, 0.0)])
def test_cancellation_penalty_follows_policy(cancelled_at, expected):
    row = {**BASE, "status": "cancelled"}
    assert penalty_amount(row, {"cancelled_at": cancelled_at} if cancelled_at else None) == expected
    line = statement_line(row, {"cancelled_at": cancelled_at} if cancelled_at else None)
    assert line["commission"] == 0 and line["agency_owes_hotel"] == expected


def test_no_show_penalty_and_totals():
    lines = [
        statement_line({**BASE, "status": "no_show", "payment_terms": "on_arrival"}, None),
        statement_line({**BASE, "id": "b2", "status": "checked_out", "payment_terms": "on_arrival"}, None),
    ]
    totals = statement_totals(lines)
    assert totals["penalty"] == 1000 and totals["hotel_owes_agency"] == 150
    assert totals["net_balance"] == 850  # agency pays the hotel
    assert (totals["bookings"], totals["no_show"]) == (1, 1)


def test_outstanding_nets_payments_by_direction():
    statement = {"totals": {"net_balance": -150.0}, "payments": [{"amount": 100, "direction": "hotel_to_agency"}]}
    assert outstanding(statement) == -50.0
    statement["payments"].append({"amount": 50, "direction": "hotel_to_agency"})
    assert outstanding(statement) == 0.0


USER = SimpleNamespace(id="u", email="ops@hotel.test", tenant_id="t1", role="admin", roles=[])


@pytest.mark.asyncio
async def test_payment_refused_before_agency_agrees(monkeypatch):
    sysdb = SimpleNamespace(agency_statements=SimpleNamespace(find_one=AsyncMock(return_value={"id": "s1", "status": "issued"})))
    monkeypatch.setattr(agency_statements, "get_system_db", lambda: sysdb)
    with pytest.raises(HTTPException) as exc:
        await agency_statements.record_payment(
            "s1", agency_statements.PaymentCreate(amount=10, direction="hotel_to_agency", paid_at="2026-12-01"), USER
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_dispute_must_reference_statement_lines(monkeypatch):
    sysdb = SimpleNamespace(agency_statements=SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "s1", "lines": [{"booking_id": "b1"}]}), find_one_and_update=AsyncMock()))
    monkeypatch.setattr(agency_statements, "get_system_db", lambda: sysdb)
    with pytest.raises(HTTPException) as exc:
        await agency_statements.dispute_statement(
            "s1", agency_statements.DisputeCreate(reason="Tutar hatalı", booking_ids=["other"]), {"agency_id": "a1"}
        )
    assert exc.value.status_code == 400
    sysdb.agency_statements.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_agree_only_from_issued_or_resolved(monkeypatch):
    sysdb = SimpleNamespace(agency_statements=SimpleNamespace(find_one_and_update=AsyncMock(return_value=None)))
    monkeypatch.setattr(agency_statements, "get_system_db", lambda: sysdb)
    with pytest.raises(HTTPException) as exc:
        await agency_statements.agree_statement("s1", {"agency_id": "a1"})
    assert exc.value.status_code == 409
    query = sysdb.agency_statements.find_one_and_update.await_args.args[0]
    assert query["status"] == {"$in": ["issued", "resolved"]}
