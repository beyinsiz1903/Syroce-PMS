from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.channel_manager.auto_map_router import (
    AutoMapApplyItem,
    AutoMapApplyRequest,
    _require_explicit_rate_plans,
    _unambiguous_rate_plan,
    apply_auto_mappings,
)


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


@pytest.mark.asyncio
async def test_exely_discovery_aliases_cannot_be_auto_applied_as_ari_ids():
    payload = AutoMapApplyRequest(provider="exely", mappings=[AutoMapApplyItem(
        pms_room_type="Standard", provider_room_code="5001574",
        provider_room_name="Standart", provider_rate_plan_code="10003870",
    )])
    with pytest.raises(HTTPException) as exc_info:
        await apply_auto_mappings(payload, current_user=SimpleNamespace(tenant_id="tenant"), _perm=True)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "EXELY_ARI_IDS_REQUIRE_MANUAL_VERIFICATION"
