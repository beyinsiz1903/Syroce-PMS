"""No-show risk reports must reconcile without turning tariffs into cash loss."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers import pms_analytics as reports
from routers import pms_dashboard as legacy

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(tenant_id="A", id="u", role="admin")


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 2, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def context(ledger_db, monkeypatch):
    for module in (reports, legacy):
        monkeypatch.setattr(module, "datetime", Clock)
        monkeypatch.setattr(module, "db", ledger_db)
        monkeypatch.setattr(module, "get_tenant_currency", AsyncMock(return_value=("EUR", "€")), raising=False)


async def booking(database, **extra):
    await database.bookings.insert_one({"tenant_id": "A", "id": "b", "status": "no_show", "check_in": "2026-10-01",
        "check_out": "2026-10-03", "no_show_at": "2026-10-02", "created_at": "2026-09-01", "channel": "direct",
        "currency": "EUR", "total_amount": 100, "no_show_reason": "overbooking", **extra})


@pytest.mark.parametrize("status", ["no_show", "noshow"])
async def test_all_reports_include_both_canonical_and_legacy_no_show_status(ledger_db, status):
    await booking(ledger_db, status=status)
    assert (await reports.get_channel_loss_analytics(days=7, current_user=USER))["total_no_shows"] == 1
    assert (await reports.get_overbooking_heatmap(days=7, current_user=USER))["total_overbookings"] == 1
    assert (await legacy.get_no_show_analytics(days=7, current_user=USER))["total_no_shows"] == 1


@pytest.mark.parametrize("extra,expected", [
    ({"is_complimentary": True, "total_amount": 999}, 0),
    ({"total_amount": None, "total": 123.45}, 123.45),
    ({"total_amount": 0, "total": 999}, 0),
    ({"total_amount": "1.005"}, 1.01),
])
async def test_money_agrees_across_channel_heatmap_and_legacy_details(ledger_db, extra, expected):
    await booking(ledger_db, **extra)
    channel = await reports.get_channel_loss_analytics(days=7, current_user=USER)
    heatmap = await reports.get_overbooking_heatmap(days=7, current_user=USER)
    detail = await legacy.get_no_show_analytics(days=7, current_user=USER)
    assert channel["loss_by_currency"] == heatmap["loss_by_currency"] == detail["loss_by_currency"] == {"EUR": expected}
    assert detail["recent"][0]["amount"] == expected


@pytest.mark.parametrize("value", ["NaN", "Infinity", "bad", True])
async def test_bad_money_does_not_crash_or_disguise_itself_as_verified_zero(ledger_db, value):
    await booking(ledger_db, total_amount=value)
    for endpoint in (reports.get_channel_loss_analytics, reports.get_overbooking_heatmap, legacy.get_no_show_analytics):
        result = await endpoint(days=7, current_user=USER)
        assert result["data_quality"]["invalid_amounts"] == 1
        assert result["loss_by_currency"] == {}


@pytest.mark.parametrize("status", ["tentative", "unknown", "draft", "pending"])
async def test_no_show_rate_denominator_is_not_diluted_by_unconfirmed_statuses(ledger_db, status):
    await booking(ledger_db)
    await booking(ledger_db, id="paid", status="checked_out")
    await booking(ledger_db, id="non-sale", status=status)
    result = await reports.get_channel_loss_analytics(days=7, current_user=USER)
    assert result["channels"][0]["no_show_rate"] == 50
    assert result["channels"][0]["total_bookings"] == 2


async def test_channel_dimensions_use_ota_precedence_and_tolerate_legacy_objects(ledger_db):
    await booking(ledger_db, source_channel={"name": "agency"})
    await booking(ledger_db, id="paid", status="checked_out", source_channel={"name": "agency"})
    result = await reports.get_channel_loss_analytics(days=7, current_user=USER)
    assert result["channels"][0]["channel"] == "agency"
    assert result["channels"][0]["no_show_rate"] == 50
    await booking(ledger_db, id="ota", ota_channel="expedia", source_channel="channel_manager")
    result = await reports.get_channel_loss_analytics(days=7, current_user=USER)
    assert {row["channel"] for row in result["channels"]} == {"agency", "expedia"}


async def test_missing_currency_follows_property_not_try(ledger_db):
    await booking(ledger_db, currency=None)
    for endpoint in (reports.get_channel_loss_analytics, reports.get_overbooking_heatmap, legacy.get_no_show_analytics):
        result = await endpoint(days=7, current_user=USER)
        assert result["currency"] == "EUR"
        assert result["loss_by_currency"] == {"EUR": 100}


async def test_daily_overbooking_values_reconcile_with_summary_not_all_no_shows(ledger_db):
    await booking(ledger_db)
    await booking(ledger_db, id="other-reason", total_amount=900, no_show_reason="guest_not_arrived")
    result = await reports.get_overbooking_heatmap(days=7, current_user=USER)
    assert sum(row["loss_by_currency"].get("EUR", 0) for row in result["heatmap"]) == result["loss_by_currency"]["EUR"] == 100
    assert result["total_overbookings"] == 1
    assert result["total_no_shows"] == 2


async def test_empty_heatmap_never_invents_a_riskiest_day(ledger_db):
    result = await reports.get_overbooking_heatmap(days=7, current_user=USER)
    assert len(result["heatmap"]) == 7
    assert result["peak_days"] == []


@pytest.mark.parametrize("bson", [False, True])
async def test_legacy_event_report_uses_calendar_edges_bson_and_excludes_future_events(ledger_db, bson):
    await booking(ledger_db, no_show_at=Clock(2026, 9, 26, tzinfo=UTC) if bson else "2026-09-26")
    await booking(ledger_db, id="future", no_show_at="2026-10-03", total_amount=9999)
    await booking(ledger_db, id="foreign", tenant_id="B", total_amount=9999)
    result = await legacy.get_no_show_analytics(days=7, current_user=USER)
    assert result["total_no_shows"] == 1
    assert result["start_date"] == "2026-09-26" and result["end_date"] == "2026-10-02"
    assert result["daily"] == [{"date": "2026-09-26", "count": 1}]


async def test_legacy_keeps_native_currencies_in_all_buckets_and_details(ledger_db):
    await booking(ledger_db)
    await booking(ledger_db, id="usd", currency="USD", total_amount=22.33)
    result = await legacy.get_no_show_analytics(days=7, current_user=USER)
    assert result["total_revenue_loss"] is None
    assert result["loss_by_currency"] == {"EUR": 100, "USD": 22.33}
    assert result["by_room_type"][0]["loss_by_currency"] == result["by_channel"][0]["loss_by_currency"] == result["loss_by_currency"]
    assert {row["currency"] for row in result["recent"]} == {"EUR", "USD"}


async def test_rule_channel_filter_is_applied_to_overbooking_count_not_only_rate(ledger_db):
    await booking(ledger_db, channel="expedia")
    await ledger_db.alert_rules.insert_one({"tenant_id": "A", "id": "rule", "is_active": True, "condition_metric": "overbooking_count", "condition_operator": "gt", "condition_value": 0,
        "channel_filter": "direct", "rule_name": "Direct only"})
    result = await reports.evaluate_alert_rules(days=7, current_user=USER)
    assert result["alerts"] == []


async def test_rule_rate_matches_channel_report_for_same_cohort(ledger_db):
    await booking(ledger_db, status="noshow")
    await booking(ledger_db, id="paid", status="checked_out")
    await booking(ledger_db, id="tentative", status="tentative")
    await ledger_db.alert_rules.insert_one({"tenant_id": "A", "id": "rule", "is_active": True, "condition_metric": "noshow_rate", "condition_operator": "gte", "condition_value": 40,
        "rule_name": "Rate test", "rule_type": "noshow_rate_high", "action_suggestion": "prepaid_zorunlu"})
    result = await reports.evaluate_alert_rules(days=7, current_user=USER)
    channel = await reports.get_channel_loss_analytics(days=7, current_user=USER)
    assert result["metrics"]["noshow_rate"] == channel["channels"][0]["no_show_rate"] == 50
    assert len(result["alerts"]) == 1


async def test_legacy_report_reads_all_rows_not_only_first_5000(ledger_db):
    await ledger_db.bookings.insert_many([{"tenant_id": "A", "id": str(i), "status": "no_show", "no_show_at": "2026-10-01", "total_amount": 0.01, "currency": "EUR"} for i in range(5001)])
    result = await legacy.get_no_show_analytics(days=7, current_user=USER)
    assert result["total_no_shows"] == 5001
    assert result["loss_by_currency"] == {"EUR": 50.01}


async def test_risk_model_keeps_legacy_status_and_comp_reference_money_consistent(ledger_db):
    await booking(ledger_db, status="noshow")
    await booking(ledger_db, id="tentative", status="tentative")
    await booking(ledger_db, id="upcoming", status="confirmed", check_in="2026-10-02", is_complimentary=True, total_amount=999)
    result = await reports.get_noshow_prediction(days_ahead=2, current_user=USER)
    assert result["historical_rates"]["by_channel"]["direct"] == 100
    assert result["predictions"][0]["total_amount"] == 0
    assert result["summary"]["potential_loss_by_currency"] == {"EUR": 0}


async def test_cohort_includes_zero_event_channels_and_zero_calendar_days(ledger_db):
    await booking(ledger_db)
    await booking(ledger_db, id="healthy", status="checked_out", channel="healthy")
    result = await reports.get_channel_loss_analytics(days=7, current_user=USER)
    healthy = next(row for row in result["channels"] if row["channel"] == "healthy")
    assert healthy["no_show_rate"] == 0 and healthy["total_bookings"] == 1
    assert len(result["trend"]) == 7
    assert sum(row["counts_by_channel"].get("direct", 0) for row in result["trend"]) == 1
    assert all(row["no_show_count"] > 0 for row in result["top3_worst"])


async def test_channel_named_date_cannot_overwrite_the_trend_axis(ledger_db):
    await booking(ledger_db, channel="date")
    result = await reports.get_channel_loss_analytics(days=7, current_user=USER)
    day = next(row for row in result["trend"] if row["date"] == "2026-10-01")
    assert day["counts_by_channel"] == {"date": 1}


async def test_invalid_stored_dates_are_explicit_and_do_not_corrupt_bucket_counts(ledger_db):
    await booking(ledger_db, check_in="2026-09-31", no_show_at="2026-09-31")
    for endpoint in (reports.get_channel_loss_analytics, reports.get_overbooking_heatmap, legacy.get_no_show_analytics):
        result = await endpoint(days=7, current_user=USER)
        assert result["data_quality"]["invalid_dates"] == 1
        assert result.get("total_no_shows", 0) == 0


async def test_unpriced_risk_is_unknown_not_a_verified_zero_loss(ledger_db):
    await booking(ledger_db, check_in="2026-09-25", check_out="2026-09-27")
    await booking(ledger_db, id="upcoming", status="confirmed", check_in="2026-10-02", total_amount="bad")
    result = await reports.get_noshow_prediction(days_ahead=2, current_user=USER)
    assert result["predictions"][0]["risk_level"] == "high"
    assert result["summary"]["potential_loss"] is None
    assert result["data_quality"]["invalid_amounts"] == 1


async def test_different_arrival_and_event_cohorts_are_deliberate_and_labelled(ledger_db):
    await booking(ledger_db, check_in="2026-09-10", no_show_at="2026-10-01")
    channel = await reports.get_channel_loss_analytics(days=7, current_user=USER)
    event = await legacy.get_no_show_analytics(days=7, current_user=USER)
    assert channel["total_no_shows"] == 0 and event["total_no_shows"] == 1
    assert channel["basis"].startswith("arrival_cohort") and event["basis"].startswith("no_show_event_day")
