"""
Mapping Completeness Validator
==============================

Enforces hard-fail policy for mapping issues.
Silent fallback is prohibited.

Every mapping failure produces:
  - error_code
  - reason
  - operator_action_hint
"""

import logging
from datetime import UTC, datetime
from typing import Any

from .data_model import MappingFailure

logger = logging.getLogger("channel_manager.mapping_validator")


class MappingValidationError:
    """Structured mapping failure with operator guidance."""

    def __init__(
        self,
        failure_type: MappingFailure,
        entity_type: str,  # "room" or "rate_plan"
        provider_code: str,
        reason: str,
        operator_action: str,
    ):
        self.failure_type = failure_type
        self.entity_type = entity_type
        self.provider_code = provider_code
        self.reason = reason
        self.operator_action = operator_action

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_type": self.failure_type.value,
            "entity_type": self.entity_type,
            "provider_code": self.provider_code,
            "reason": self.reason,
            "operator_action": self.operator_action,
        }


def validate_room_mapping(
    mapping: dict[str, Any] | None,
    provider_room_code: str,
) -> MappingValidationError | None:
    """
    Validate a room mapping. Returns error if invalid, None if OK.
    Hard fail policy: no silent fallback.
    """
    if mapping is None:
        return MappingValidationError(
            failure_type=MappingFailure.UNMAPPED,
            entity_type="room",
            provider_code=provider_room_code,
            reason=f"No room mapping found for provider room code: {provider_room_code}",
            operator_action="Create a room mapping for this provider room code in the Data Model dashboard",
        )

    if not mapping.get("is_active", True):
        return MappingValidationError(
            failure_type=MappingFailure.INACTIVE,
            entity_type="room",
            provider_code=provider_room_code,
            reason=f"Room mapping for {provider_room_code} exists but is inactive",
            operator_action="Reactivate the room mapping or create a new one",
        )

    if mapping.get("validation_status") == "invalid":
        return MappingValidationError(
            failure_type=MappingFailure.AMBIGUOUS,
            entity_type="room",
            provider_code=provider_room_code,
            reason=f"Room mapping for {provider_room_code} failed validation",
            operator_action="Review and fix the room mapping configuration",
        )

    if not mapping.get("pms_room_type_id"):
        return MappingValidationError(
            failure_type=MappingFailure.DELETED,
            entity_type="room",
            provider_code=provider_room_code,
            reason=f"Room mapping for {provider_room_code} has no PMS room type linked",
            operator_action="Link a valid PMS room type to this mapping",
        )

    return None


def validate_rate_plan_mapping(
    mapping: dict[str, Any] | None,
    provider_rate_code: str,
) -> MappingValidationError | None:
    """
    Validate a rate plan mapping. Returns error if invalid, None if OK.
    Hard fail policy: no silent fallback.
    """
    if mapping is None:
        return MappingValidationError(
            failure_type=MappingFailure.UNMAPPED,
            entity_type="rate_plan",
            provider_code=provider_rate_code,
            reason=f"No rate plan mapping found for provider rate code: {provider_rate_code}",
            operator_action="Create a rate plan mapping for this provider rate code in the Data Model dashboard",
        )

    if not mapping.get("is_active", True):
        return MappingValidationError(
            failure_type=MappingFailure.INACTIVE,
            entity_type="rate_plan",
            provider_code=provider_rate_code,
            reason=f"Rate plan mapping for {provider_rate_code} exists but is inactive",
            operator_action="Reactivate the rate plan mapping or create a new one",
        )

    if mapping.get("validation_status") == "invalid":
        return MappingValidationError(
            failure_type=MappingFailure.AMBIGUOUS,
            entity_type="rate_plan",
            provider_code=provider_rate_code,
            reason=f"Rate plan mapping for {provider_rate_code} failed validation",
            operator_action="Review and fix the rate plan mapping configuration",
        )

    if not mapping.get("pms_rate_plan_id"):
        return MappingValidationError(
            failure_type=MappingFailure.DELETED,
            entity_type="rate_plan",
            provider_code=provider_rate_code,
            reason=f"Rate plan mapping for {provider_rate_code} has no PMS rate plan linked",
            operator_action="Link a valid PMS rate plan to this mapping",
        )

    return None


async def compute_mapping_health(
    tenant_id: str,
    property_id: str,
    provider: str,
    room_mappings: list[dict],
    rate_plan_mappings: list[dict],
) -> dict[str, Any]:
    """
    Compute mapping health score for a tenant/property/provider.
    Returns completeness %, broken/ambiguous/inactive counts.
    """
    now = datetime.now(UTC).isoformat()

    room_total = len(room_mappings)
    room_active = sum(1 for m in room_mappings if m.get("is_active"))
    room_valid = sum(1 for m in room_mappings if m.get("validation_status") == "valid")
    room_broken = sum(1 for m in room_mappings if not m.get("pms_room_type_id"))
    room_inactive = room_total - room_active

    rate_total = len(rate_plan_mappings)
    rate_active = sum(1 for m in rate_plan_mappings if m.get("is_active"))
    rate_valid = sum(1 for m in rate_plan_mappings if m.get("validation_status") == "valid")
    rate_broken = sum(1 for m in rate_plan_mappings if not m.get("pms_rate_plan_id"))
    rate_inactive = rate_total - rate_active

    room_completeness = (room_active / room_total * 100) if room_total > 0 else 0
    rate_completeness = (rate_active / rate_total * 100) if rate_total > 0 else 0
    overall_completeness = ((room_active + rate_active) / (room_total + rate_total) * 100) if (room_total + rate_total) > 0 else 0

    return {
        "tenant_id": tenant_id,
        "property_id": property_id,
        "provider": provider,
        "overall_completeness_pct": round(overall_completeness, 1),
        "room_mapping": {
            "total": room_total,
            "active": room_active,
            "valid": room_valid,
            "broken": room_broken,
            "inactive": room_inactive,
            "completeness_pct": round(room_completeness, 1),
        },
        "rate_plan_mapping": {
            "total": rate_total,
            "active": rate_active,
            "valid": rate_valid,
            "broken": rate_broken,
            "inactive": rate_inactive,
            "completeness_pct": round(rate_completeness, 1),
        },
        "is_production_ready": (room_completeness == 100 and rate_completeness == 100 and room_broken == 0 and rate_broken == 0),
        "last_validation_at": now,
    }
