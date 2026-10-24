"""Real-Mongo checks for the active workspace's financial/operational breakdowns."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core import tenant_currency
from routers.reports_pkg import dashboard_lists

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(tenant_id="A", role="admin", id="operator")
DAY = "2026-10-07"


@pytest.fixture(autouse=True)
def context(ledger_db, monkeypatch):
    monkeypatch.setattr(dashboard_lists, "db", ledger_db)
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", AsyncMock(return_value=("EUR", "€")))
    monkeypatch.setattr("security.encrypted_lookup.decrypt_guest_doc", lambda row: row)


async def dashboard(period="daily"):
    return await dashboard_lists._basic_dashboard_impl.__wrapped__(USER, True, DAY, period)


async def seed_room(db):
    await db.rooms.insert_one({"tenant_id": "A", "id": "room", "room_number": "101", "room_type": "Suite"})


async def seed_booking(db, **extra):
    await db.bookings.insert_one({"tenant_id": "A", "id": "booking", "room_id": "room", "booking_source": "corporate",
        "status": "checked_in", "check_in": DAY, "check_out": "2026-10-08", "currency": "EUR", **extra})


def breakdown_totals(report, section):
    result = {}
    rows = report["room_type_occupancy"].values() if section == "rooms" else [
        {"revenue_by_currency": values} for values in report["booking_sources"]["revenue_by_currency"].values()
    ]
    for row in rows:
        for code, amount in row["revenue_by_currency"].items():
            result[code] = round(result.get(code, 0) + amount, 2)
    return {code: value for code, value in result.items() if value}


async def test_room_type_is_resolved_from_assigned_room_not_defaulted_to_standard(ledger_db):
    await seed_room(ledger_db)
    await seed_booking(ledger_db)
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "booking_id": "booking", "business_date": DAY, "total": 100, "currency": "EUR"})
    report = await dashboard()
    assert report["room_type_occupancy"]["Suite"]["revenue_by_currency"] == {"EUR": 100}
    assert breakdown_totals(report, "rooms") == report["period_comparison"]["month_revenue_by_currency"]


async def test_people_profiles_and_physical_rooms_have_distinct_reconciled_counts(ledger_db):
    await seed_room(ledger_db)
    await seed_booking(ledger_db, adults=2, children=2, guest_id="parent")
    await ledger_db.guests.insert_many([
        {"tenant_id": "A", "id": "parent", "name": "Parent"},
        {"tenant_id": "A", "id": "child", "name": "Child"},
    ])
    await ledger_db.booking_guests.insert_many([
        {"tenant_id": "A", "booking_id": "booking", "guest_id": "parent"},
        {"tenant_id": "A", "booking_id": "booking", "guest_id": "child"},
    ])
    await ledger_db.rooms.insert_one({"tenant_id": "A", "id": "virtual", "is_virtual": True})
    report = await dashboard()
    assert report["summary"]["physical_rooms"] == report["daily_analysis"]["occupied_rooms"] == 1
    assert report["daily_analysis"]["in_house_guests"] == 4
    assert report["daily_analysis"]["registered_guest_profiles"] == 2
    assert len(report["daily_lists"]["in_house"]) == 2


@pytest.mark.parametrize("folio_only", [False, True])
async def test_posting_period_does_not_drop_revenue_for_stays_outside_arrival_cohort(ledger_db, folio_only):
    await seed_room(ledger_db)
    await seed_booking(ledger_db, check_in="2026-08-01", check_out="2026-08-02", status="checked_out", room_type="Retired suite")
    await ledger_db.folios.insert_one({"tenant_id": "A", "id": "folio", "booking_id": "booking", "currency": "EUR"})
    await ledger_db.folio_charges.insert_many([
        {"tenant_id": "A", **({"folio_id": "folio"} if folio_only else {"booking_id": "booking"}), "business_date": DAY, "total": value, "currency": "EUR"}
        for value in (100, -20)
    ])
    report = await dashboard()
    assert report["booking_sources"]["revenue_by_currency"] == {"corporate": {"EUR": 80}}
    assert report["booking_sources"]["distribution"] == {"corporate": 1}
    assert report["room_type_occupancy"]["Retired suite"]["revenue_by_currency"] == {"EUR": 80}
    assert report["room_type_occupancy"]["Retired suite"]["total"] == 0
    assert report["summary"]["arrivals"] == 0
    assert report["guest_list"] == []


async def test_unassigned_and_pos_revenue_remain_visible_without_inventing_bookings(ledger_db):
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "booking_id": "missing", "business_date": DAY, "total": -5, "currency": "USD"})
    await ledger_db.pos_orders.insert_one({"tenant_id": "A", "id": "pos", "business_date": DAY, "status": "closed", "grand_total": 30, "currency": "EUR"})
    report = await dashboard()
    assert breakdown_totals(report, "rooms") == breakdown_totals(report, "channels") == {"USD": -5, "EUR": 30}
    assert report["booking_sources"]["distribution"] == {"unassigned": 0}


async def test_attribution_never_uses_another_tenants_folio_booking_or_room(ledger_db):
    await ledger_db.rooms.insert_one({"tenant_id": "B", "id": "room", "room_type": "Private suite"})
    await ledger_db.bookings.insert_one({"tenant_id": "B", "id": "secret", "room_id": "room", "booking_source": "Secret channel"})
    await ledger_db.folios.insert_one({"tenant_id": "B", "id": "foreign", "booking_id": "secret"})
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "folio_id": "foreign", "business_date": DAY, "total": 20, "currency": "EUR"})
    report = await dashboard()
    assert report["booking_sources"]["revenue_by_currency"] == {"unassigned": {"EUR": 20}}
    assert "Private suite" not in report["room_type_occupancy"]


@pytest.mark.parametrize("field", ["created_at", "started_at", "completed_at", "scheduled_date"])
@pytest.mark.parametrize("as_bson", [False, True])
async def test_housekeeping_task_day_supports_iso_and_bson_storage(ledger_db, field, as_bson):
    await seed_room(ledger_db)
    await ledger_db.housekeeping_tasks.insert_one({"tenant_id": "A", "id": "task", "room_id": "room", "status": "completed",
        field: datetime(2026, 10, 7, 23, 59, 59, 999000, tzinfo=UTC) if as_bson else DAY + "T23:59:59.999Z"})
    report = await dashboard()
    assert report["housekeeping"]["completed"] == 1
    assert report["housekeeping"]["rows"][0]["id"] == "task"


async def test_old_open_bson_housekeeping_task_is_not_hidden_by_room_ready_default(ledger_db):
    await seed_room(ledger_db)
    await ledger_db.housekeeping_tasks.insert_one({"tenant_id": "A", "id": "old", "room_id": "room", "status": "assigned", "created_at": datetime(2026, 9, 1, tzinfo=UTC)})
    assert (await dashboard())["housekeeping"]["pending"] == 1


@pytest.mark.parametrize("as_bson", [False, True])
async def test_maintenance_includes_entire_last_day_not_just_first_second_of_235959(ledger_db, as_bson):
    value = datetime(2026, 10, 7, 23, 59, 59, 999000, tzinfo=UTC) if as_bson else DAY + "T23:59:59.999Z"
    await ledger_db.maintenance_tasks.insert_many([
        {"tenant_id": "A", "status": "completed", "completed_at": value},
        {"tenant_id": "A", "status": "completed", "completed_at": "2026-10-08"},
        {"tenant_id": "B", "status": "completed", "completed_at": value},
    ])
    assert (await dashboard())["maintenance"]["completed_month"] == 1


@pytest.mark.parametrize("invalid", ["draft", "void", "voided", "cancelled", "canceled", "deleted"])
async def test_invalid_invoice_is_not_a_pending_or_paid_document(ledger_db, invalid):
    await ledger_db.invoices.insert_many([
        {"tenant_id": "A", "status": invalid, "payment_status": status, "created_at": DAY}
        for status in ("pending", "partial", "paid")
    ])
    report = await dashboard()
    assert report["finance"] == {"pending_invoices": 0, "paid_invoices_month": 0}
    assert report["payments"]["total_pending"] == 0


@pytest.mark.parametrize("as_bson", [False, True])
async def test_paid_invoice_counter_uses_issue_day_before_creation_day(ledger_db, as_bson):
    day = datetime(2026, 10, 7, 23, tzinfo=UTC) if as_bson else DAY
    await ledger_db.invoices.insert_many([
        {"tenant_id": "A", "issue_date": day, "created_at": "2026-11-01", "payment_status": "paid"},
        {"tenant_id": "A", "issue_date": "2026-10-08", "created_at": DAY, "payment_status": "paid"},
        {"tenant_id": "B", "issue_date": day, "payment_status": "paid"},
    ])
    assert (await dashboard())["finance"]["paid_invoices_month"] == 1


@pytest.mark.parametrize("flag", ["voided", "deleted"])
async def test_voided_or_deleted_flags_do_not_inflate_invoice_counts(ledger_db, flag):
    await ledger_db.invoices.insert_many([
        {"tenant_id": "A", flag: True, "payment_status": "pending"},
        {"tenant_id": "A", flag: True, "payment_status": "paid", "created_at": DAY},
    ])
    assert (await dashboard())["finance"] == {"pending_invoices": 0, "paid_invoices_month": 0}


async def test_legacy_invoice_without_issue_date_uses_created_day_and_live_pending_is_current(ledger_db):
    await ledger_db.invoices.insert_many([
        {"tenant_id": "A", "issue_date": "", "created_at": DAY, "payment_status": "paid"},
        {"tenant_id": "A", "created_at": datetime(2026, 10, 7, 23, 59, 59, 999000, tzinfo=UTC), "payment_status": "paid"},
        {"tenant_id": "A", "created_at": "2026-01-01", "payment_status": "partial"},
    ])
    assert (await dashboard())["finance"] == {"pending_invoices": 1, "paid_invoices_month": 2}


@pytest.mark.parametrize("status", ["sent", "overdue", "partial", "pending"])
async def test_legacy_invoice_status_is_used_only_when_payment_status_is_absent(ledger_db, status):
    await ledger_db.invoices.insert_many([
        {"tenant_id": "A", "status": status, "issue_date": DAY},
        {"tenant_id": "A", "status": status, "payment_status": "paid", "issue_date": DAY},
        {"tenant_id": "A", "status": "paid", "payment_status": "partial", "issue_date": DAY},
        {"tenant_id": "A", "status": "paid", "issue_date": DAY},
    ])
    assert (await dashboard())["finance"] == {"pending_invoices": 2, "paid_invoices_month": 2}


async def test_task_on_next_day_is_not_in_selected_days_completed_summary(ledger_db):
    await seed_room(ledger_db)
    await ledger_db.housekeeping_tasks.insert_one({"tenant_id": "A", "id": "future", "room_id": "room", "status": "completed", "completed_at": datetime(2026, 10, 8, tzinfo=UTC)})
    report = await dashboard()
    assert report["housekeeping"]["completed"] == 0


async def test_room_and_channel_breakdowns_reconcile_multiple_native_currencies(ledger_db):
    await seed_room(ledger_db)
    await seed_booking(ledger_db, room_type="Suite")
    await ledger_db.folio_charges.insert_many([
        {"tenant_id": "A", "booking_id": "booking", "business_date": DAY, "total": amount, "currency": code}
        for code, amount in [("EUR", 100), ("EUR", -20), ("USD", 25)]
    ])
    report = await dashboard()
    assert breakdown_totals(report, "rooms") == breakdown_totals(report, "channels") == {"EUR": 80, "USD": 25}
    assert report["room_type_occupancy"]["Suite"]["revenue"] == 0
    assert report["booking_sources"]["revenue"]["corporate"] == 0


async def test_explicit_workspace_refresh_bypasses_cached_report_and_replaces_it(ledger_db, monkeypatch):
    import cache_manager
    from core import report_cache

    memory = object.__new__(cache_manager.CacheManager)
    memory.enabled = True
    memory.backend = "memory"
    memory.client = cache_manager._InMemoryTTLStore()
    monkeypatch.setattr(cache_manager, "cache", memory)
    monkeypatch.setattr(report_cache, "cache", memory)
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "business_date": DAY, "total": 50, "currency": "EUR"})
    first = await dashboard_lists.get_basic_reports_dashboard(date=DAY, period="daily", current_user=USER)
    assert first["summary"]["today_revenue_by_currency"] == {"EUR": 50}
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "business_date": DAY, "total": 20, "currency": "EUR"})
    cached = await dashboard_lists.get_basic_reports_dashboard(date=DAY, period="daily", current_user=USER)
    assert cached["summary"]["today_revenue_by_currency"] == {"EUR": 50}
    fresh = await dashboard_lists.get_basic_reports_dashboard(date=DAY, period="daily", current_user=USER, nocache=True)
    assert fresh["summary"]["today_revenue_by_currency"] == {"EUR": 70}
    replaced = await dashboard_lists.get_basic_reports_dashboard(date=DAY, period="daily", current_user=USER)
    assert replaced["summary"]["today_revenue_by_currency"] == {"EUR": 70}
