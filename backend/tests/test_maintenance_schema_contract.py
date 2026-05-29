"""F9C § 98 (Wave 2) — Maintenance asset/plan create contract lock.

The stress spec previously POSTed `asset_tag`/`category` (assets) and
`frequency:'monthly'` (plans). With `extra="ignore"` those fields are
dropped and the required canonical fields go missing → 422 (recorded as a
P2 REVIEW). The frontend (MaintenanceAssets.jsx / MaintenancePlans.jsx)
already sends the canonical fields, so the schema is the source of truth.

These tests lock that contract so the corrected spec payloads stay valid
and the legacy bogus payloads stay rejected.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from models.schemas.rooms import MaintenanceAsset, PreventiveMaintenancePlan


# --- assets ---------------------------------------------------------------

def test_asset_valid_canonical_payload():
    asset = MaintenanceAsset(
        name="F9C_MAINT_F_asset",
        asset_type="hvac",
        location="Stress Test Lab",
    )
    assert asset.name == "F9C_MAINT_F_asset"
    assert asset.asset_type == "hvac"
    assert asset.id  # default uuid populated


def test_asset_legacy_bogus_payload_rejected():
    # asset_tag/category are not schema fields; name+asset_type missing.
    with pytest.raises(ValidationError):
        MaintenanceAsset(
            asset_tag="X-ASSET-1",
            category="HVAC",
            location="Stress Test Lab",
        )


# --- plans ----------------------------------------------------------------

def test_plan_valid_canonical_payload():
    due = datetime.now(UTC) + timedelta(days=30)
    plan = PreventiveMaintenancePlan(
        frequency_type="months",
        frequency_value=1,
        next_due_date=due,
        description="F9C_MAINT_G_plan",
    )
    assert plan.frequency_type == "months"
    assert plan.frequency_value == 1
    assert plan.next_due_date == due
    assert plan.is_active is True


def test_plan_legacy_bogus_payload_rejected():
    # frequency:'monthly' is not a schema field; required fields missing.
    with pytest.raises(ValidationError):
        PreventiveMaintenancePlan(
            name="X-PLAN-1",
            frequency="monthly",
            description="bogus",
        )
