"""The live report workspace and daily reconciliation must use identical room revenue."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core import tenant_currency
from domains.pms import night_audit_router
from routers.reports_pkg import dashboard_lists

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(tenant_id="A", role="admin", id="operator", name="Operator", email="operator@example.test", granted_permissions=[])


@pytest.fixture(autouse=True)
def context(ledger_db, monkeypatch):
    monkeypatch.setattr(dashboard_lists, "db", ledger_db)
    monkeypatch.setattr(dashboard_lists, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-07"}))
    monkeypatch.setattr(night_audit_router, "get_system_db", lambda: ledger_db)
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", AsyncMock(return_value=("EUR", "€")))
    monkeypatch.setattr("security.encrypted_lookup.decrypt_guest_doc", lambda row: row)


async def dashboard(period="daily", day="2026-10-07"):
    return await dashboard_lists._basic_dashboard_impl.__wrapped__(USER, True, day, period)


async def seed_stay(db, *, currency="EUR", **extra):
    await db.rooms.insert_one({"tenant_id": "A", "id": "r", "room_number": "101", "room_type": "standard"})
    await db.bookings.insert_one(
        {
            "tenant_id": "A",
            "id": "b",
            "room_id": "r",
            "room_type": "standard",
            "status": "checked_in",
            "check_in": "2026-10-07",
            "check_out": "2026-10-08",
            "total_amount": 100,
            **({"currency": currency} if currency else {}),
            **extra,
        }
    )


async def test_zero_room_posting_does_not_resurrect_accrual_in_any_workspace_card(ledger_db):
    await seed_stay(ledger_db)
    await ledger_db.folio_charges.insert_many([{"tenant_id": "A", "booking_id": "b", "business_date": "2026-10-07", "category": "room", "total": amount, "currency": "EUR"} for amount in (100, -100)])
    report = await dashboard()
    await ledger_db.tenant_settings.insert_one({"tenant_id": "A", "business_date": "2026-10-07"})
    daily = await night_audit_router.trial_balance(date="2026-10-07", current_user=USER)
    for data in (report["period_metrics"], report["daily_analysis"]):
        assert data["room_revenue"] == daily["revenue"]["rooms"] == 0
        assert data["revenue_source"] == "posted"
        assert data["adr"] == 0


async def test_period_preserves_actual_postings_and_accrues_only_missing_days(ledger_db):
    await seed_stay(ledger_db, check_out="2026-10-09", total_amount=200)
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "booking_id": "b", "business_date": "2026-10-07", "category": "room", "total": 80, "currency": "EUR"})
    report = await dashboard("monthly", "2026-10-08")
    assert report["period_metrics"]["room_revenue_by_currency"] == {"EUR": 180}
    assert report["period_metrics"]["adr_by_currency"] == {"EUR": 90}
    assert report["period_metrics"]["revenue_source"] == "mixed"


async def test_daily_posting_presence_is_decided_per_currency(ledger_db):
    await seed_stay(ledger_db)
    await ledger_db.rooms.insert_one({"tenant_id": "A", "id": "r2"})
    await ledger_db.bookings.insert_one(
        {"tenant_id": "A", "id": "try", "room_id": "r2", "status": "checked_in", "check_in": "2026-10-07", "check_out": "2026-10-08", "total_amount": 200, "currency": "TRY"}
    )
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "booking_id": "b", "business_date": "2026-10-07", "category": "room", "total": 80, "currency": "EUR"})
    report = await dashboard()
    assert report["daily_analysis"]["room_revenue_by_currency"] == {"EUR": 80, "TRY": 200}
    assert report["period_metrics"]["adr_by_currency"] == {"EUR": 40, "TRY": 100}


async def test_previous_period_room_performance_preserves_native_currency_and_zero_postings(ledger_db):
    await seed_stay(ledger_db, check_in="2026-10-06", check_out="2026-10-07")
    await ledger_db.folio_charges.insert_many([{"tenant_id": "A", "booking_id": "b", "business_date": "2026-10-06", "category": "room", "total": value, "currency": "EUR"} for value in (100, -100)])
    report = await dashboard()
    assert report["period_comparison"]["prev_month_adr"] == 0
    assert report["period_comparison"]["prev_period_revpar_by_currency"] == {"EUR": 0}


@pytest.mark.parametrize("in_bson,out_bson", [(False, True), (True, False)])
async def test_long_stay_with_mixed_date_storage_is_not_dropped_from_report_workspace(ledger_db, in_bson, out_bson):
    await seed_stay(
        ledger_db,
        check_in=datetime(2026, 8, 1, tzinfo=UTC) if in_bson else "2026-08-01",
        check_out=datetime(2026, 11, 1, tzinfo=UTC) if out_bson else "2026-11-01",
        total_amount=9200,
    )
    report = await dashboard("monthly")
    assert report["summary"]["occupied_rooms"] == 1
    assert len(report["daily_lists"]["in_house"]) == 1


async def test_missing_booking_currency_uses_property_native_currency(ledger_db):
    await seed_stay(ledger_db, currency=None)
    report = await dashboard()
    assert report["daily_analysis"]["room_revenue_by_currency"] == {"EUR": 100}
    assert report["daily_lists"]["in_house"][0]["currency"] == "EUR"


@pytest.mark.parametrize("start_bson,end_bson", [(False, False), (False, True), (True, False), (True, True)])
async def test_workspace_capacity_and_canonical_loader_share_mixed_date_blocks(ledger_db, start_bson, end_bson):
    from datetime import date

    from modules.pms_core.stay_night_metrics import load_stay_night_metrics

    await ledger_db.rooms.insert_one({"tenant_id": "A", "id": "r", "room_number": "101"})
    await ledger_db.room_blocks.insert_one(
        {
            "tenant_id": "A",
            "room_id": "r",
            "status": "active",
            "start_date": datetime(2026, 10, 1, tzinfo=UTC) if start_bson else "2026-10-01",
            "end_date": datetime(2026, 10, 8, tzinfo=UTC) if end_bson else "2026-10-08",
        }
    )
    report = await dashboard()
    canonical = await load_stay_night_metrics(ledger_db, "A", date(2026, 10, 7), date(2026, 10, 8), actual_only=True)
    assert report["summary"]["total_rooms"] == canonical[0]["total_rooms"] == 0
    assert report["summary"]["blocked_rooms"] == 1
    assert canonical[1]["total_rooms"] == 1


@pytest.mark.parametrize("endpoint", ["dashboard", "official"])
@pytest.mark.parametrize("day", ["", "2026-10-07oops", "2026-02-30"])
async def test_workspace_and_official_routes_reject_invalid_explicit_dates(endpoint, day):
    with pytest.raises(HTTPException) as caught:
        if endpoint == "dashboard":
            await dashboard_lists.get_basic_reports_dashboard(date=day, period="daily", current_user=USER)
        else:
            await dashboard_lists.get_official_guest_list(date=day, current_user=USER)
    assert caught.value.status_code == 422


@pytest.mark.parametrize("status,count_field", [("in_house", "arrivals"), ("noshow", "no_shows"), ("canceled", "cancellations")])
async def test_legacy_status_aliases_match_summary_and_guest_cohort(ledger_db, status, count_field):
    await seed_stay(ledger_db, status=status, cancelled_at="2026-10-07T10:00:00Z")
    report = await dashboard()
    assert report["summary"][count_field] == 1
    assert len(report["guest_list"]) == 1


async def test_comparison_reservation_count_uses_same_statuses_in_both_periods(ledger_db):
    for day, end in [("2026-10-06", "2026-10-07"), ("2026-10-07", "2026-10-08")]:
        await ledger_db.bookings.insert_one({"tenant_id": "A", "id": day, "status": "guaranteed", "check_in": day, "check_out": end})
    report = await dashboard()
    assert report["period_comparison"]["month_bookings"] == report["period_comparison"]["prev_month_bookings"] == 1
