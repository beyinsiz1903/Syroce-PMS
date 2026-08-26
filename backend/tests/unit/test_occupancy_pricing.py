from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.occupancy_pricing import (
    OccupancyPricingError,
    calculate_occupancy_quote,
    find_occupancy_rule,
    normalize_occupancy_rule,
)
from domains.channel_manager import unified_rate_manager_router as unified

RULE = {
    "pricing_type": "per_person",
    "base_occupancy": 2,
    "extra_adult_rate": 1500,
    "extra_child_rate": 750,
    "child_free_age_max": 6,
    "max_occupancy": 4,
}

TIERED_RULE = {
    **RULE,
    "child_age_bands": [
        {"min_age": 0, "max_age": 6, "pricing_mode": "free", "value": 0},
        {"min_age": 7, "max_age": 11, "pricing_mode": "adult_percentage", "value": 50},
        {"min_age": 12, "max_age": 17, "pricing_mode": "adult_rate", "value": 0},
    ],
}


def test_two_adults_pay_only_base_rate():
    quote = calculate_occupancy_quote(
        base_nightly_rate=5000,
        nights=1,
        adults=2,
        children_ages=[],
        rule=RULE,
    )
    assert quote["nightly_total"] == 5000
    assert quote["total_amount"] == 5000
    assert quote["extra_adults"] == 0


def test_third_adult_adds_supplement_for_every_night():
    quote = calculate_occupancy_quote(
        base_nightly_rate=5000,
        nights=2,
        adults=3,
        children_ages=[],
        rule=RULE,
    )
    assert quote["adult_supplement_nightly"] == 1500
    assert quote["nightly_total"] == 6500
    assert quote["total_amount"] == 13000


def test_free_child_age_and_paid_child_are_distinguished():
    quote = calculate_occupancy_quote(
        base_nightly_rate=5000,
        nights=1,
        adults=2,
        children_ages=[6, 7],
        rule=RULE,
    )
    assert quote["chargeable_children"] == 1
    assert quote["total_amount"] == 5750


def test_tiered_child_pricing_supports_free_half_and_adult_rates():
    quote = calculate_occupancy_quote(
        base_nightly_rate=5000,
        nights=2,
        adults=2,
        children_ages=[6, 7, 12],
        rule={**TIERED_RULE, "max_occupancy": 5},
    )

    assert [child["rate"] for child in quote["child_breakdown"]] == [0, 750, 1500]
    assert quote["free_children"] == 1
    assert quote["chargeable_children"] == 2
    assert quote["child_supplement_nightly"] == 2250
    assert quote["nightly_total"] == 7250
    assert quote["total_amount"] == 14500


def test_adult_equivalent_child_uses_an_included_adult_slot_first():
    quote = calculate_occupancy_quote(
        base_nightly_rate=5000,
        nights=1,
        adults=1,
        children_ages=[12],
        rule=TIERED_RULE,
    )

    assert quote["child_breakdown"][0]["counts_as_adult"] is True
    assert quote["child_breakdown"][0]["rate"] == 0
    assert quote["nightly_total"] == 5000


def test_percentage_tier_rounds_to_currency_precision():
    rule = {
        **TIERED_RULE,
        "extra_adult_rate": 999.99,
        "child_age_bands": [
            band | {"value": 33.33} if band["pricing_mode"] == "adult_percentage" else band
            for band in TIERED_RULE["child_age_bands"]
        ],
    }
    quote = calculate_occupancy_quote(
        base_nightly_rate=5000,
        nights=1,
        adults=2,
        children_ages=[8],
        rule=rule,
    )
    assert quote["child_supplement_nightly"] == 333.30
    assert quote["nightly_total"] == 5333.30


@pytest.mark.parametrize(
    "bands",
    [
        [
            {"min_age": 0, "max_age": 6, "pricing_mode": "free", "value": 0},
            {"min_age": 8, "max_age": 17, "pricing_mode": "fixed", "value": 500},
        ],
        [
            {"min_age": 0, "max_age": 10, "pricing_mode": "free", "value": 0},
            {"min_age": 10, "max_age": 17, "pricing_mode": "fixed", "value": 500},
        ],
    ],
)
def test_child_age_bands_reject_gaps_and_overlaps(bands):
    with pytest.raises(OccupancyPricingError, match="bosluk ve cakisma"):
        normalize_occupancy_rule({**RULE, "child_age_bands": bands})


def test_child_percentage_cannot_exceed_one_hundred():
    bands = [
        {"min_age": 0, "max_age": 6, "pricing_mode": "free", "value": 0},
        {"min_age": 7, "max_age": 17, "pricing_mode": "adult_percentage", "value": 101},
    ]
    with pytest.raises(OccupancyPricingError, match="0-100"):
        normalize_occupancy_rule({**RULE, "child_age_bands": bands})


def test_legacy_child_rule_is_migrated_without_price_change():
    normalized = normalize_occupancy_rule(RULE)
    assert normalized["child_age_bands"] == [
        {"min_age": 0, "max_age": 6, "pricing_mode": "free", "value": 0.0},
        {"min_age": 7, "max_age": 17, "pricing_mode": "fixed", "value": 750.0},
    ]


def test_per_room_rule_never_adds_guest_supplements():
    quote = calculate_occupancy_quote(
        base_nightly_rate=5000,
        nights=1,
        adults=3,
        children_ages=[12],
        rule={**RULE, "pricing_type": "per_room"},
    )
    assert quote["total_amount"] == 5000


def test_capacity_and_invalid_money_fail_closed():
    with pytest.raises(OccupancyPricingError, match="maksimum 4"):
        calculate_occupancy_quote(
            base_nightly_rate=5000,
            nights=1,
            adults=4,
            children_ages=[2],
            rule=RULE,
        )
    with pytest.raises(OccupancyPricingError, match="negatif"):
        calculate_occupancy_quote(
            base_nightly_rate=-1,
            nights=1,
            adults=2,
            children_ages=[],
            rule=RULE,
        )


def test_maximum_occupancy_cannot_be_below_included_occupancy():
    with pytest.raises(OccupancyPricingError, match="Maksimum"):
        normalize_occupancy_rule({**RULE, "base_occupancy": 3, "max_occupancy": 2})


def test_hotelrunner_pricing_rule_exposes_manual_verification_state():
    _, rules = unified._pricing_payload([
        {"room_type_code": "STD", **RULE, "provider_pricing_verified": False}
    ])
    assert rules["STD"]["provider_sync_state"] == "MANUAL_CONFIGURATION_REQUIRED"
    assert rules["STD"]["provider_pricing_verified"] is False

    _, verified = unified._pricing_payload([
        {"room_type_code": "STD", **RULE, "provider_pricing_verified": True}
    ])
    assert verified["STD"]["provider_sync_state"] == "VERIFIED"


def test_hotelrunner_base_rate_write_fails_closed_until_rule_is_attested():
    mappings = [{"pms_room_type": "standard", "hr_inv_code": "HR-STD"}]
    assert unified._unsafe_hotelrunner_room_types(["standard"], mappings, []) == ["standard"]
    assert unified._unsafe_hotelrunner_room_types(
        ["standard"], mappings, [{"room_type_code": "HR-STD", "pricing_type": "per_person"}]
    ) == ["standard"]
    assert unified._unsafe_hotelrunner_room_types(
        ["standard"], mappings, [{
            "room_type_code": "HR-STD", "pricing_type": "per_person", "provider_pricing_verified": True
        }]
    ) == []
    assert unified._unsafe_hotelrunner_room_types(
        ["standard"], mappings, [{"room_type_code": "HR-STD", "pricing_type": "per_room"}]
    ) == []


@pytest.mark.asyncio
async def test_rule_resolution_bridges_pms_type_to_hotelrunner_inventory_code():
    empty_mapping = SimpleNamespace(find_one=AsyncMock(return_value=None))
    hr_mapping = SimpleNamespace(
        find_one=AsyncMock(return_value={"hr_inv_code": "HR-STD"})
    )
    async def find_hr_rule(query, _projection):
        if query.get("room_type_code") == "HR-STD":
            return {"room_type_code": "HR-STD", **RULE}
        return None

    hr_settings = SimpleNamespace(find_one=AsyncMock(side_effect=find_hr_rule))
    db = SimpleNamespace(
        hotelrunner_room_mappings=hr_mapping,
        exely_room_mappings=empty_mapping,
        hr_pricing_settings=hr_settings,
        pricing_settings=SimpleNamespace(find_one=AsyncMock(return_value=None)),
    )

    resolved = await find_occupancy_rule(
        db,
        "tenant-1",
        {"room_type": "standard"},
    )

    assert resolved["room_type_code"] == "HR-STD"
    assert resolved["extra_adult_rate"] == 1500
