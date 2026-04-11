"""
HotelRunner Provider — Validators
===================================

Pre-flight validation for credentials, payloads, and mappings.
Fail fast before making API calls.
"""
from typing import Any

from .errors import HotelRunnerMappingError, HotelRunnerValidationError


def validate_connection_credentials(token: str, hr_id: str) -> None:
    """Validate credentials are present and well-formed."""
    if not token or not token.strip():
        raise HotelRunnerValidationError("API token is required", field="token")
    if not hr_id or not hr_id.strip():
        raise HotelRunnerValidationError("HR ID (hotel ID) is required", field="hr_id")
    if len(token) < 8:
        raise HotelRunnerValidationError(
            "API token seems too short (min 8 chars)", field="token"
        )


def validate_inventory_payload(payload: dict[str, Any]) -> None:
    """Validate an ARI inventory payload before sending."""
    inv_code = payload.get("inv_code", "")
    if not inv_code:
        raise HotelRunnerValidationError("inv_code is required", field="inv_code")

    start = payload.get("start_date") or payload.get("date", "")
    if not start:
        raise HotelRunnerValidationError("date/start_date is required", field="start_date")

    # At least one update field must be present
    update_fields = ["availability", "price", "stop_sale", "min_stay", "cta", "ctd"]
    has_update = any(payload.get(f) is not None for f in update_fields)
    if not has_update:
        raise HotelRunnerValidationError(
            "At least one update field is required (availability, price, etc.)",
            field="payload",
        )


def validate_room_mapping(
    mapping: dict[str, Any] | None,
    pms_room_type_code: str = "",
) -> None:
    """Validate that a room mapping exists and is complete."""
    if not mapping:
        raise HotelRunnerMappingError(
            f"No room mapping found for PMS room type: {pms_room_type_code}",
            entity_type="room",
            entity_id=pms_room_type_code,
        )
    ext_code = mapping.get("external_code") or mapping.get("provider_room_code", "")
    if not ext_code:
        raise HotelRunnerMappingError(
            f"Room mapping has no external code for: {pms_room_type_code}",
            entity_type="room",
            entity_id=pms_room_type_code,
        )


def validate_reservation_pull_params(
    per_page: int = 50,
    page: int = 1,
) -> None:
    """Validate reservation pull parameters."""
    if per_page < 1 or per_page > 100:
        raise HotelRunnerValidationError(
            f"per_page must be between 1 and 100, got {per_page}",
            field="per_page",
        )
    if page < 1:
        raise HotelRunnerValidationError(
            f"page must be >= 1, got {page}",
            field="page",
        )
