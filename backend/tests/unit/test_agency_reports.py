"""Agency performance and receivables, per party and currency."""

from datetime import date
from types import SimpleNamespace

import pytest

from core.agency_reports import aging_bucket, build_report, due_date
from tests.unit.test_agency_statements_symmetric import _Coll

TODAY = date(2026, 12, 15)


def _booking(id_, agency="a1", currency="TRY", status="confirmed", check_in="2026-12-01", nights=2, total=8000, terms="prepaid",
             created_at="2026-11-01", cancelled_at=None):
    day = date.fromisoformat(check_in)
    return {"id": id_, "tenant_id": "t1", "agency_id": agency, "agency_name": {"a1": "Acente Bir", "a2": "Acente İki"}.get(agency),
            "hotel_name": "Demo Otel", "status": status, "check_in": check_in, "check_out": date.fromordinal(day.toordinal() + nights).isoformat(),
            "total_amount": total, "currency": currency, "commission_pct": 15, "payment_terms": terms, "created_at": created_at,
            "cancelled_at": cancelled_at, "cancellation_policy": {"free_until_days_before": 7, "penalty_pct": 50, "no_show_penalty_pct": 100}}


@pytest.fixture
def world():
    ledger = [
        _booking("b1"),                                                  # prepaid stay in period, unbilled: agency owes 6.800
        _booking("b2", terms="on_arrival", check_in="2026-12-05"),       # pay at hotel, billed below
        _booking("b3", status="cancelled", check_in="2026-12-10", cancelled_at="2026-12-09"),  # late cancel: 50% penalty
        _booking("b4", check_in="2027-01-10", created_at="2026-12-12"),  # forward 30 days, picked up this week
        _booking("b5", check_in="2027-02-20", nights=3),                  # forward 90 days only
        _booking("b6", agency="a2", currency="EUR", total=1000),          # other agency, other currency
    ]
    statements = [
        {"id": "s1", "tenant_id": "t1", "agency_id": "a1", "currency": "TRY", "status": "agreed", "agreed_at": "2026-10-01T10:00:00",
         "lines": [{"booking_id": "b2", "payment_terms": "net_30", "agency_owes_hotel": 0, "hotel_owes_agency": 1200}],
         "totals": {"net_balance": -1200}, "payments": [],
         "payment_notices": [{"status": "pending", "direction": "hotel_to_agency", "amount": 1200}]},
        {"id": "s2", "tenant_id": "t1", "agency_id": "a1", "currency": "TRY", "status": "issued",
         "lines": [{"booking_id": "old"}], "totals": {"net_balance": 500}, "payments": []},
        {"id": "s3", "tenant_id": "t1", "agency_id": "a1", "currency": "TRY", "status": "settled",
         "lines": [{"booking_id": "older"}], "totals": {"net_balance": 900}, "payments": [{"amount": 900, "direction": "agency_to_hotel"}]},
    ]
    return SimpleNamespace(
        marketplace_bookings=_Coll(ledger), bookings=_Coll(), agency_statements=_Coll(statements),
        agency_contracts=_Coll([{"tenant_id": "t1", "agency_id": "a1", "agency_name": "Acente Bir", "hotel_name": "Demo Otel", "contract_code": "SOZ-1"}]),
    )


def _row(report, party, currency="TRY"):
    return next(row for row in report["rows"] if row["party_id"] == party and row["currency"] == currency)


def test_due_date_and_aging():
    assert due_date({"agreed_at": "2026-10-01", "lines": [{"payment_terms": "prepaid"}, {"payment_terms": "net_30"}]}) == date(2026, 10, 31)
    assert due_date({"status": "issued", "lines": []}) is None
    assert aging_bucket(date(2026, 12, 20), TODAY) == "not_due"
    assert aging_bucket(date(2026, 11, 14), TODAY) == "overdue_31_60"
    assert aging_bucket(date(2026, 8, 1), TODAY) == "overdue_90_plus"


@pytest.mark.asyncio
async def test_hotel_view_per_agency_and_currency(world):
    report = await build_report(world, side="hotel", scope={"tenant_id": "t1"}, period_start="2026-12-01", period_end="2026-12-31", today=TODAY)
    a1 = _row(report, "a1")
    perf = a1["performance"]
    assert (perf["bookings"], perf["cancelled"], perf["room_nights"], perf["gross"]) == (2, 1, 4, 16000.0)
    assert perf["penalty"] == 4000.0  # b3 late cancellation, apart from sales
    assert (perf["commission"], perf["net_to_hotel"], perf["cancel_rate"]) == (2400.0, 13600.0, 0.3333)
    assert a1["party_name"] == "Acente Bir"
    # b1 prepaid 6.800 + b3 late-cancel penalty 4.000 not on any statement yet; b2 is billed
    assert a1["unbilled"] == {"bookings": 2, "agency_owes_hotel": 10800.0, "hotel_owes_agency": 0.0}
    rec = a1["receivables"]
    assert (rec["hotel_owes_agency"], rec["agency_owes_hotel"], rec["open_statements"]) == (1200.0, 500.0, 2)
    assert rec["aging"]["overdue_31_60"] == 1200.0  # agreed 1 Oct + net 30 = due 31 Oct
    assert rec["awaiting_agreement"] == 500.0       # issued, not agreed by both
    assert rec["pending_notices"] == {"agency_to_hotel": 0.0, "hotel_to_agency": 1200.0, "count": 1}
    assert a1["forward"]["30"] == {"bookings": 1, "room_nights": 2, "gross": 8000.0}
    assert a1["forward"]["90"]["bookings"] == 2
    assert a1["pickup_7d"] == {"bookings": 1, "gross": 8000.0, "cancelled": 1}  # b3 cancelled on the 9th
    eur = _row(report, "a2", "EUR")
    assert eur["performance"]["gross"] == 1000.0
    assert {total["currency"] for total in report["totals"]} == {"TRY", "EUR"}  # never mixed
    try_total = next(t for t in report["totals"] if t["currency"] == "TRY")
    assert try_total["performance"]["gross"] == 16000.0


@pytest.mark.asyncio
async def test_agency_view_lists_hotels(world):
    report = await build_report(world, side="agency", scope={"agency_id": "a1"}, period_start="2026-12-01", period_end="2026-12-31", today=TODAY)
    assert [(row["party_id"], row["party_name"], row["currency"]) for row in report["rows"]] == [("t1", "Demo Otel", "TRY")]
    assert report["rows"][0]["receivables"]["hotel_owes_agency"] == 1200.0


@pytest.mark.asyncio
async def test_no_show_is_not_a_sale(world):
    world.marketplace_bookings.rows.append(_booking("b7", status="no_show", check_in="2026-12-12", total=8000))
    world.marketplace_bookings.rows[-1]["cancellation_policy"] = {"free_until_days_before": 7, "penalty_pct": 50, "no_show_penalty_pct": 0}
    report = await build_report(world, side="hotel", scope={"tenant_id": "t1"}, period_start="2026-12-01", period_end="2026-12-31", today=TODAY)
    perf = _row(report, "a1")["performance"]
    assert (perf["bookings"], perf["room_nights"], perf["gross"], perf["no_show"]) == (2, 4, 16000.0, 1)
    assert perf["penalty"] == 4000.0  # the zero no-show penalty adds nothing
    assert perf["cancel_rate"] == 0.25
