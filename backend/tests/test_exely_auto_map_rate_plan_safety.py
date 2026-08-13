import pytest
from fastapi import HTTPException

from domains.channel_manager.auto_map_router import AutoMapApplyItem, _require_explicit_rate_plans, _unambiguous_rate_plan


def test_single_rate_plan_can_be_selected_without_ambiguity():
    plan = {"code": "only-plan", "name": "Only plan"}

    assert _unambiguous_rate_plan([plan]) == plan


def test_multiple_rate_plans_never_select_the_first_plan_implicitly():
    plans = [
        {"code": "first", "name": "First"},
        {"code": "approved", "name": "Approved"},
    ]

    assert _unambiguous_rate_plan(plans) is None


def test_exely_apply_rejects_a_missing_rate_plan_before_database_write():
    mapping = AutoMapApplyItem(
        pms_room_type="Standard",
        provider_room_code="provider-room",
        provider_room_name="Provider room",
    )

    with pytest.raises(HTTPException) as exc_info:
        _require_explicit_rate_plans("exely", [mapping])

    assert exc_info.value.status_code == 400


def test_hotelrunner_mapping_does_not_require_an_exely_rate_plan():
    mapping = AutoMapApplyItem(
        pms_room_type="Standard",
        provider_room_code="provider-room",
        provider_room_name="Provider room",
    )

    _require_explicit_rate_plans("hotelrunner", [mapping])
