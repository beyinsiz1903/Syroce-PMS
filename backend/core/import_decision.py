"""
DATA-001: Import Decision Layer
================================
Classifies lineage records for PMS booking import eligibility.

After the ingest pipeline creates/updates a lineage record, this module
determines the correct import_status:

  - pending_auto_import : mapping OK, no duplicate → ready for auto-import
  - review_required     : mapping missing, anomaly, or business rule violation
  - duplicate           : booking already exists for this external reservation
"""
import logging
from typing import Any, Dict, Optional, Tuple

from core.database import db

logger = logging.getLogger("core.import_decision")

COLL_IMPORTED = "imported_reservations"

# Review reasons
REASON_UNMAPPED_ROOM = "unmapped_room_type"
REASON_UNMAPPED_RATE = "unmapped_rate_plan"
REASON_INVALID_DATES = "invalid_date_range"
REASON_MISSING_GUEST = "missing_guest_identity"
REASON_PROPERTY_MISMATCH = "property_scope_mismatch"
REASON_CANCELLED = "reservation_cancelled"


def classify_for_import(
    lineage: Dict[str, Any],
    room_mapping: Optional[Dict[str, Any]],
    rate_mapping: Optional[Dict[str, Any]],
) -> Tuple[str, Optional[str]]:
    """
    Determine import eligibility from a lineage record.

    Returns:
        (import_status, review_reason) tuple.
        import_status is one of: pending_auto_import, review_required, duplicate (skipped here)
        review_reason is None when eligible.
    """
    # Cancelled reservations don't need PMS booking import
    status = lineage.get("status", "")
    if status == "cancelled":
        return "review_required", REASON_CANCELLED

    # Date validation
    arrival = lineage.get("arrival_date", "")
    departure = lineage.get("departure_date", "")
    if not arrival or not departure:
        return "review_required", REASON_INVALID_DATES
    if arrival >= departure:
        return "review_required", REASON_INVALID_DATES

    # Guest identity
    guest_name = lineage.get("guest_name", "")
    if not guest_name or len(guest_name.strip()) < 2:
        return "review_required", REASON_MISSING_GUEST

    # Room mapping
    room_type_code = lineage.get("room_type_code", "")
    if room_type_code and not room_mapping:
        return "review_required", REASON_UNMAPPED_ROOM

    # Rate plan mapping
    rate_plan_code = lineage.get("rate_plan_code", "")
    if rate_plan_code and not rate_mapping:
        return "review_required", REASON_UNMAPPED_RATE

    return "pending_auto_import", None


async def check_already_imported(
    tenant_id: str,
    connector_id: str,
    external_reservation_id: str,
) -> bool:
    """Check if this external reservation was already imported."""
    existing = await db[COLL_IMPORTED].find_one(
        {
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "external_reservation_id": external_reservation_id,
            "import_status": {"$in": ["imported", "processing", "pending_auto_import"]},
        },
        {"_id": 0, "id": 1},
    )
    return existing is not None


async def check_booking_source_exists(
    tenant_id: str,
    provider: str,
    external_reservation_id: str,
) -> Optional[str]:
    """Check if a PMS booking already exists for this source."""
    booking = await db.bookings.find_one(
        {
            "tenant_id": tenant_id,
            "source.provider": provider,
            "source.external_reservation_id": external_reservation_id,
        },
        {"_id": 0, "id": 1},
    )
    return booking.get("id") if booking else None
