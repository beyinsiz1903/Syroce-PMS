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

RULE = {
    "pricing_type": "per_person",
    "base_occupancy": 2,
    "extra_adult_rate": 1500,
    "extra_child_rate": 750,
    "child_free_age_max": 6,
    "max_occupancy": 4,
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
