"""Exercise the registered daily-reconciliation route with real Mongo queries."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core import tenant_currency
from domains.pms import night_audit_router as audit
from routers.reports_pkg import standard_reports

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(tenant_id="A", role="admin", id="operator", granted_permissions=[])


@pytest.fixture(autouse=True)
async def context(ledger_db, monkeypatch):
    monkeypatch.setattr(audit, "get_system_db", lambda: ledger_db)
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", AsyncMock(return_value=("EUR", "€")))
    await ledger_db.tenant_settings.insert_one({"tenant_id": "A", "business_date": "2026-10-07"})


async def result(day="2026-10-07"):
    return await audit.trial_balance(date=day, current_user=USER)


async def test_daily_report_uses_canonical_posted_amounts_cash_classification_and_native_currencies(ledger_db):
    await ledger_db.folio_charges.insert_many(
        [
            {"tenant_id": "A", "business_date": datetime(2026, 10, 7, tzinfo=UTC), "category": "room", "total": 100, "amount": 999, "currency": "EUR"},
            {"tenant_id": "A", "date": "2026-10-07", "category": "spa", "total": 20, "currency": "TRY"},
            {"tenant_id": "B", "business_date": "2026-10-07", "total": 99999},
            {"tenant_id": "A", "business_date": "2026-10-07", "total": 99999, "voided": True},
        ]
    )
    await ledger_db.extra_charges.insert_one({"tenant_id": "A", "business_date": "2026-10-07", "category": "laundry", "total": 5, "currency": "EUR"})
    payment = {"tenant_id": "A", "idempotency_key": "same", "business_date": "2026-10-07", "amount": 50, "currency": "EUR", "method": "cash", "status": "paid"}
    await ledger_db.payments.insert_many(
        [
            payment,
            {**payment, "id": "retry"},
            {"tenant_id": "A", "business_date": "2026-10-07", "amount": 10, "currency": "EUR", "method": "cash", "payment_type": "refund"},
            {"tenant_id": "A", "business_date": "2026-10-07", "amount": 5, "currency": "EUR", "method": "discount"},
            {"tenant_id": "A", "business_date": "2026-10-07", "amount": 999, "method": "card", "status": "pending"},
            {"tenant_id": "A", "business_date": "2026-10-07", "amount": 999, "method": "city_ledger"},
            {"tenant_id": "B", "business_date": "2026-10-07", "amount": 99999},
        ]
    )
    data = await result()
    assert data["revenue"]["total_by_currency"] == {"EUR": 105, "TRY": 20}
    assert data["revenue"]["total"] is None
    assert data["revenue"]["net_total_by_currency"] == {"EUR": 100, "TRY": 20}
    assert data["payments"]["total_by_currency"] == {"EUR": 40}
    assert data["payments"]["by_method"]["cash"]["count"] == 2
    assert data["balance_check"]["by_currency"] == {"EUR": 60, "TRY": 20}


async def test_equal_nominal_totals_in_unlike_currencies_are_not_balanced(ledger_db):
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "business_date": "2026-10-07", "total": 100, "currency": "EUR"})
    await ledger_db.payments.insert_one({"tenant_id": "A", "business_date": "2026-10-07", "amount": 100, "currency": "TRY"})
    data = await result()
    assert data["balance_check"]["in_balance"] is False
    assert data["balance_check"]["revenue_minus_payments"] is None
    assert data["balance_check"]["by_currency"] == {"EUR": 100, "TRY": -100}


async def test_zero_net_room_posting_is_not_replaced_with_booking_accrual(ledger_db):
    await ledger_db.rooms.insert_one({"tenant_id": "A", "id": "r"})
    await ledger_db.bookings.insert_one({"tenant_id": "A", "room_id": "r", "status": "checked_in", "check_in": "2026-10-07", "check_out": "2026-10-08", "total_amount": 100, "currency": "EUR"})
    await ledger_db.folio_charges.insert_many([{"tenant_id": "A", "business_date": "2026-10-07", "category": "room", "total": amount, "currency": "EUR"} for amount in (100, -100)])
    data = await result()
    assert data["revenue"]["rooms"] == 0
    assert data["revenue"]["posting_pending"] is False


async def test_posted_and_unposted_room_currencies_keep_independent_sources(ledger_db):
    await ledger_db.rooms.insert_many([{"tenant_id": "A", "id": room} for room in ("r1", "r2")])
    await ledger_db.bookings.insert_many(
        [
            {"tenant_id": "A", "room_id": room, "status": "checked_in", "check_in": "2026-10-07", "check_out": "2026-10-08", "total_amount": amount, "currency": code}
            for room, amount, code in [("r1", 100, "EUR"), ("r2", 200, "TRY")]
        ]
    )
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "business_date": "2026-10-07", "category": "room", "total": 90, "currency": "EUR"})
    data = await result()
    assert data["revenue"]["rooms_by_currency"] == {"EUR": 90, "TRY": 200}
    assert data["revenue"]["room_revenue_source_by_currency"] == {"EUR": "posted", "TRY": "accrued"}
    assert data["revenue"]["rooms"] is None and data["revenue"]["posting_pending"] is True


async def test_historical_movements_include_date_only_and_bson_completed_arrivals(ledger_db):
    await ledger_db.bookings.insert_many(
        [
            {"tenant_id": tenant, "id": str(i), "status": status, "check_in": start, "check_out": end}
            for i, (tenant, status, start, end) in enumerate(
                [
                    ("A", "checked_out", "2026-10-07", "2026-10-08"),
                    ("A", "checked_out", datetime(2026, 10, 7, tzinfo=UTC), datetime(2026, 10, 8, tzinfo=UTC)),
                    ("A", "checked_out", "2026-10-06", datetime(2026, 10, 7, tzinfo=UTC)),
                    ("A", "no_show", "2026-10-07", "2026-10-08"),
                    ("A", "confirmed", "2026-10-07", "2026-10-08"),
                    ("B", "checked_out", "2026-10-07", "2026-10-08"),
                ]
            )
        ]
    )
    data = await result()
    assert data["movements"] == {"arrivals": 2, "departures": 1, "no_shows": 1, "in_house": 2}


async def test_blocked_room_capacity_is_not_subtracted_twice(ledger_db):
    await ledger_db.rooms.insert_many([{"tenant_id": "A", "id": room, "status": status} for room, status in [("r1", "available"), ("r2", "out_of_order")]])
    await ledger_db.room_blocks.insert_one({"tenant_id": "A", "room_id": "r2", "status": "active", "start_date": "2026-10-07", "end_date": "2026-10-08"})
    data = await result()
    assert data["occupancy"]["total_rooms"] == 1
    assert data["occupancy"]["available"] == 1
    assert data["occupancy"]["out_of_order"] == 1


async def test_ledger_uses_folio_positions_and_deposit_remaining_amounts_not_stale_booking_projections(ledger_db):
    await ledger_db.bookings.insert_one({"tenant_id": "A", "id": "b", "status": "checked_out", "ar_balance": 9999, "currency": "EUR"})
    await ledger_db.folios.insert_one({"tenant_id": "A", "id": "f", "booking_id": "b", "status": "open", "currency": "EUR"})
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "folio_id": "f", "total": 100, "currency": "EUR"})
    await ledger_db.payments.insert_one({"tenant_id": "A", "folio_id": "f", "amount": 30, "currency": "EUR"})
    await ledger_db.deposits.insert_many(
        [
            {"tenant_id": "A", "booking_id": "b", "amount": 100, "refunded_amount": 40, "status": "partially_refunded"},
            {"tenant_id": "A", "amount": 200, "status": "refunded"},
            {"tenant_id": "A", "amount": 200, "status": "applied"},
            {"tenant_id": "B", "amount": 9999, "status": "received"},
        ]
    )
    data = await result()
    assert data["ledger"]["ar_balance_by_currency"] == {"EUR": 70}
    assert data["ledger"]["deposit_balance_by_currency"] == {"EUR": 60}
    assert data["ledger"]["snapshot_scope"] == "current"


async def test_current_open_folio_credit_does_not_cancel_unlike_currency_debt(ledger_db):
    await ledger_db.folios.insert_one({"tenant_id": "A", "id": "f", "status": "open", "currency": "EUR"})
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "folio_id": "f", "total": 100, "currency": "EUR"})
    await ledger_db.payments.insert_one({"tenant_id": "A", "folio_id": "f", "amount": 200, "currency": "TRY"})
    assert (await result())["ledger"]["ar_balance_by_currency"] == {"EUR": 100}


async def test_daily_report_does_not_cap_categories_or_payment_methods_at_fifty(ledger_db):
    await ledger_db.folio_charges.insert_many([{"tenant_id": "A", "business_date": "2026-10-07", "category": str(i), "total": 1, "currency": "EUR"} for i in range(51)])
    await ledger_db.payments.insert_many([{"tenant_id": "A", "business_date": "2026-10-07", "method": str(i), "amount": 1, "currency": "EUR"} for i in range(51)])
    data = await result()
    assert data["revenue"]["total_by_currency"] == data["payments"]["total_by_currency"] == {"EUR": 51}
    assert len(data["revenue"]["by_category"]) == len(data["payments"]["by_method"]) == 51
    assert data["revenue"]["by_category"] == {str(i): 1 for i in range(51)}


async def test_daily_categories_share_known_aliases_and_keep_minibar_outside_fnb(ledger_db):
    await ledger_db.folio_charges.insert_many([
        {"tenant_id": "A", "business_date": "2026-10-07", "category": category, "total": amount, "currency": "EUR"}
        for category, amount in [("mini_bar", 10), ("alcoholic_beverage", 20), ("food_and_beverage", 30), ("custom-service", 40)]
    ])
    data = await result()
    assert data["revenue"]["fnb_by_currency"] == {"EUR": 50}
    assert data["revenue"]["other_by_currency"] == {"EUR": 50}
    assert data["revenue"]["by_category"] == {"minibar": 10, "alcohol": 20, "fnb": 30, "custom-service": 40}
    assert data["revenue"]["total_by_currency"] == {"EUR": 100}


async def test_default_day_is_the_pms_business_date_not_the_calendar():
    assert (await result(None))["date"] == "2026-10-07"


async def test_invalid_financial_source_fails_closed_instead_of_returning_a_fake_zero(ledger_db):
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "business_date": "2026-10-07", "total": "invalid"})
    with pytest.raises(HTTPException) as error:
        await result()
    assert error.value.status_code == 503


@pytest.mark.parametrize("day", ["", "invalid", "2026-02-30", "2026-10-07oops"])
async def test_invalid_day_does_not_silently_select_another_report(day):
    with pytest.raises(HTTPException) as error:
        await result(day)
    assert error.value.status_code == 422


async def test_daily_and_standard_revenue_share_signed_pos_ledger_and_transfer_deduplication(ledger_db, monkeypatch):
    monkeypatch.setattr(standard_reports, "db", ledger_db)
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "business_date": "2026-10-07", "category": "room", "total": 100, "currency": "EUR", "source_pos_order_id": "room"})
    await ledger_db.pos_orders.insert_many(
        [
            {"tenant_id": "A", "id": "direct", "status": "closed", "business_date": "2026-10-07", "grand_total": 24, "currency": "TRY"},
            {"tenant_id": "A", "id": "room", "status": "closed", "business_date": "2026-10-07", "grand_total": 100, "currency": "EUR"},
        ]
    )
    await ledger_db.pos_transactions.insert_many(
        [
            {"tenant_id": "A", "id": "sale", "order_id": "cash", "status": "completed", "business_date": "2026-10-07", "total_amount": 110, "tip_amount": 10, "currency": "EUR"},
            {"tenant_id": "A", "id": "refund", "order_id": "cash", "status": "refunded", "business_date": "2026-10-07", "total_amount": -55, "tip_amount": -5, "currency": "EUR"},
            {"tenant_id": "A", "id": "transfer", "order_id": "room", "status": "completed", "business_date": "2026-10-07", "total_amount": 100, "currency": "EUR", "payment_method": "room_charge"},
        ]
    )
    data = await result()
    canonical = await standard_reports.get_revenue_report.__wrapped__("2026-10-07", "2026-10-07", USER)
    assert data["revenue"]["total_by_currency"] == canonical["total_revenue_by_currency"] == {"EUR": 150, "TRY": 24}
