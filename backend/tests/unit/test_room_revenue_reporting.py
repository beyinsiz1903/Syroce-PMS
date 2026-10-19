"""Pure arithmetic guards shared by report workspace and daily reconciliation."""

import pytest

from modules.pms_core.reporting_ledger import charge_category
from modules.pms_core.room_revenue_reporting import room_period_performance


@pytest.mark.parametrize("category", ["room", "rooms", "accommodation", "lodging", "konaklama", "room_charge"])
def test_all_supported_room_categories_enter_the_same_canonical_ledger_bucket(category):
    assert charge_category({"category": category}) == "room"


def metric(day="2026-10-07", **extra):
    return {"date": day, "occupied_rooms": 2, "sold_rooms": 2, "total_rooms": 10, "revenue_by_currency": {"EUR": 100}, **extra}


def test_empty_room_totals_keep_the_property_currency_including_zero_postings():
    result = room_period_performance([], {}, fallback_currency="EUR")
    for key in ("room_revenue", "posted_room_revenue", "accrued_room_revenue", "adr", "revpar"):
        assert result[key] == 0
        assert result[key + "_by_currency"] == {"EUR": 0}


@pytest.mark.parametrize("posted", [0, -20])
def test_a_present_zero_or_negative_room_posting_is_never_replaced_by_accrual(posted):
    result = room_period_performance([metric()], {"2026-10-07": {"EUR": posted}})
    assert result["room_revenue"] == posted
    assert result["revenue_source"] == "posted"
    assert result["posting_gap_days"] == []


def test_adr_uses_decimal_half_up_and_paid_room_nights():
    result = room_period_performance([metric(revenue_by_currency={"EUR": .05})], {})
    assert result["adr_by_currency"] == {"EUR": .03}


def test_a_mixed_currency_performance_never_returns_a_sum_as_its_legacy_scalar():
    result = room_period_performance([metric(revenue_by_currency={"EUR": 100, "TRY": 200})], {"2026-10-07": {"EUR": 90}})
    assert result["room_revenue"] is None
    assert result["room_revenue_by_currency"] == {"EUR": 90, "TRY": 200}
    assert result["adr_by_currency"] == {"EUR": 45, "TRY": 100}
    assert result["revenue_source"] == "mixed"
