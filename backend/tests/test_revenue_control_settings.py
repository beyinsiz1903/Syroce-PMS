from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms import operations_router as ops
from modules.pms_core.revenue_control_settings import DEFAULTS, physical_types, snapshot, validate_patch, validate_walk

USER = SimpleNamespace(id="actor", tenant_id="tenant-qa", email="qa@example.invalid")
HURDLE = {"Junior Suite": {"min_rate": 0, "bar": 123.45, "active": False}}
DAY = {"Junior Suite": {"mon": {"rate": 123.45, "min_stay": 1}}}
WALK = {"guest_name": " Synthetic QA ", "room_type": "Junior Suite", "compensation_type": "cash", "compensation_amount": 12.34,
        "nearby_hotel": "", "notes": "Administrative test, not paid", "request_id": "synthetic-request"}


def patch(section="hurdle_rates", value=None, doc=None):
    value = HURDLE if value is None else value
    return {section: deepcopy(value), "expected_revisions": {section: snapshot(doc)["section_revisions"][section]}}


def test_physical_inventory_only_and_snapshot_does_not_claim_enforcement():
    assert physical_types([{"room_type": "Junior Suite"}, {"room_type": "Virtual", "is_virtual": True},
                           {"room_type": "Inactive", "is_active": False}]) == {"Junior Suite"}
    result = snapshot(None)
    assert result["automatic_enforcement"] is False and result["application_mode"] == "planning_only"
    assert set(result["section_revisions"]) == set(DEFAULTS)
    assert validate_patch(patch(), {"Junior Suite"})[0] == {"hurdle_rates": HURDLE}


@pytest.mark.parametrize("value", [-1, True, "12", None, float("nan"), float("inf"), 1e10, 10**500])
def test_invalid_money_is_not_coerced_to_zero(value):
    body = patch()
    body["hurdle_rates"]["Junior Suite"]["bar"] = value
    with pytest.raises(HTTPException) as exc:
        validate_patch(body, {"Junior Suite"})
    assert exc.value.status_code == 400


@pytest.mark.parametrize("section,value", [
    ("hurdle_rates", {}), ("hurdle_rates", {"Invented": HURDLE["Junior Suite"]}),
    ("hurdle_rates", {"Junior Suite": {"min_rate": 1, "bar": 2, "active": "false"}}),
    ("day_pricing", {"Junior Suite": {"funday": {"rate": 1, "min_stay": 1}}}),
    ("day_pricing", {"Junior Suite": {"mon": {"rate": 1, "min_stay": 1.5}}}),
    ("day_pricing", {"Junior Suite": {"mon": {"rate": 1, "min_stay": 0}}}),
    ("overbooking", {**DEFAULTS["overbooking"], "max_percentage": 21}),
    ("overbooking", {**DEFAULTS["overbooking"], "max_percentage": 2.5}),
    ("overbooking", {**DEFAULTS["overbooking"], "enabled": "false"}),
    ("overbooking", {**DEFAULTS["overbooking"], "walk_compensation": []}),
    ("overbooking", {**DEFAULTS["overbooking"], "current_overbooked": 99}),
])
def test_invalid_maps_and_bounds_rejected(section, value):
    with pytest.raises(HTTPException) as exc:
        validate_patch(patch(section, value), {"Junior Suite"})
    assert exc.value.status_code == 400


@pytest.mark.parametrize("body", [{}, {"tenant_id": "other"}, {"hurdle_rates": HURDLE}, {"hurdle_rates": HURDLE, "expected_revisions": {}}])
def test_missing_or_spoofed_patch_does_not_write(body):
    with pytest.raises(HTTPException):
        validate_patch(body, {"Junior Suite"})


@pytest.mark.asyncio
async def test_save_changes_only_selected_section_and_uses_atomic_compare(monkeypatch):
    before = {"_id": "existing", "tenant_id": USER.tenant_id, "day_pricing": DAY, "overbooking": DEFAULTS["overbooking"]}
    collection = SimpleNamespace(find_one=AsyncMock(return_value=before), update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)))
    rooms = SimpleNamespace(find=lambda *args: SimpleNamespace(to_list=AsyncMock(return_value=[{"room_type": "Junior Suite"}])))
    monkeypatch.setattr(ops, "db", SimpleNamespace(revenue_settings=collection, rooms=rooms))
    result = await ops.save_revenue_settings(patch(doc=before), current_user=USER)
    query, change = collection.update_one.await_args.args
    assert query == {"_id": "existing", "tenant_id": USER.tenant_id, "hurdle_rates": {"$exists": False}}
    assert set(change["$set"]) == {"hurdle_rates", "updated_at", "updated_by", "updated_by_id"}
    assert change["$set"]["updated_by_id"] == USER.id and not result["automatic_enforcement"]
    collection.update_one.return_value = SimpleNamespace(matched_count=0)
    with pytest.raises(HTTPException) as exc:
        await ops.save_revenue_settings(patch(doc=before), current_user=USER)
    assert exc.value.status_code == 409


@pytest.mark.parametrize("change", [{"guest_name": " "}, {"room_type": "Virtual"}, {"compensation_amount": -1},
    {"compensation_amount": "0"}, {"compensation_type": []}, {"request_id": ""}, {"tenant_id": "other"}])
def test_walk_note_rejects_invalid_or_spoofed_fields(change):
    with pytest.raises(HTTPException):
        validate_walk({**WALK, **change}, {"Junior Suite"})


def test_walk_note_preserves_decimal_amount_and_trims_identity():
    result = validate_walk(WALK, {"Junior Suite"})
    assert result["compensation_amount"] == 12.34 and result["guest_name"] == "Synthetic QA"
