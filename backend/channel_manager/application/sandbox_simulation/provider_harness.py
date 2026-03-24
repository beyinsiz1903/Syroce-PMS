"""
Provider Harness — Synthetic data generators for Exely and HotelRunner.

Generates canonical reservations with configurable chaos:
  - Duplicate payloads (same external_id, same fingerprint)
  - Modifications (same external_id, different fingerprint)
  - Cancellations (same external_id, status=cancelled)
  - Stale inventory snapshots
  - Delayed/failed ACK responses
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ...domain.models.canonical import (
    CanonicalGuest,
    CanonicalReservation,
    ReservationStatus,
)

PROVIDER_PROFILES = {
    "hotelrunner": {
        "display_name": "HotelRunner",
        "channel_name": "Booking.com",
        "channel_code": "BDC",
        "room_type_prefix": "HR_RT_",
        "rate_plan_prefix": "HR_RP_",
        "requires_ack": True,
        "currency": "TRY",
    },
    "exely": {
        "display_name": "Exely",
        "channel_name": "Expedia",
        "channel_code": "EXP",
        "room_type_prefix": "EX_RT_",
        "rate_plan_prefix": "EX_RP_",
        "requires_ack": False,
        "currency": "EUR",
    },
}


def _base_guest(seq: int) -> CanonicalGuest:
    return CanonicalGuest(
        first_name=f"TestGuest{seq}",
        last_name=f"Sandbox{seq}",
        email=f"sandbox{seq}@test.dev",
        phone=f"+9055000{seq:04d}",
        nationality="TR",
    )


def generate_reservation(
    provider: str,
    external_id: str,
    seq: int = 1,
    status: ReservationStatus = ReservationStatus.CONFIRMED,
    arrival_offset_days: int = 7,
    stay_nights: int = 3,
    total_amount: float = 1500.0,
    adult_count: int = 2,
    child_count: int = 0,
    special_requests: str = "",
    message_uid: Optional[str] = None,
) -> CanonicalReservation:
    """Generate a single canonical reservation for a given provider profile."""
    profile = PROVIDER_PROFILES[provider]
    now = datetime.now(timezone.utc)
    arrival = (now + timedelta(days=arrival_offset_days)).strftime("%Y-%m-%d")
    departure = (now + timedelta(days=arrival_offset_days + stay_nights)).strftime("%Y-%m-%d")

    return CanonicalReservation(
        id=str(uuid.uuid4()),
        external_id=external_id,
        hr_number=f"HR-{external_id[:8]}",
        confirmation_number=f"CONF-{external_id[:8]}",
        channel_name=profile["channel_name"],
        channel_code=profile["channel_code"],
        status=status,
        message_uid=message_uid or str(uuid.uuid4()),
        requires_ack=profile["requires_ack"],
        guest=_base_guest(seq),
        arrival_date=arrival,
        departure_date=departure,
        room_type_id=f"{profile['room_type_prefix']}STD",
        room_type_name="Standard Room",
        rate_plan_id=f"{profile['rate_plan_prefix']}BAR",
        rate_plan_name="Best Available Rate",
        adult_count=adult_count,
        child_count=child_count,
        total_amount=total_amount,
        currency=profile["currency"],
        payment_type="credit_card",
        special_requests=special_requests,
        raw_provider_data={"sandbox": True, "provider": provider, "seq": seq},
    )


def generate_duplicate_batch(
    provider: str, count: int = 3
) -> List[CanonicalReservation]:
    """Generate N identical reservations (same external_id, same data)."""
    ext_id = f"DUP-{uuid.uuid4().hex[:8]}"
    return [
        generate_reservation(provider, external_id=ext_id, seq=1)
        for _ in range(count)
    ]


def generate_modify_then_cancel(
    provider: str,
) -> List[CanonicalReservation]:
    """Generate a reservation, then a modification, then a cancellation."""
    ext_id = f"RACE-{uuid.uuid4().hex[:8]}"
    original = generate_reservation(provider, external_id=ext_id, seq=1, total_amount=1500.0)
    modified = generate_reservation(
        provider, external_id=ext_id, seq=1,
        total_amount=2000.0, special_requests="Modified: extra bed",
    )
    cancelled = generate_reservation(
        provider, external_id=ext_id, seq=1,
        status=ReservationStatus.CANCELLED,
    )
    return [original, modified, cancelled]


def generate_stale_inventory_snapshot(
    provider: str, room_type_id: str, dates: List[str],
    stale_available: int = 10, actual_available: int = 3,
) -> Dict[str, Any]:
    """Generate a stale inventory snapshot that doesn't match actual state."""
    profile = PROVIDER_PROFILES[provider]
    return {
        "provider": provider,
        "display_name": profile["display_name"],
        "room_type_id": room_type_id,
        "dates": dates,
        "provider_reported_available": stale_available,
        "pms_actual_available": actual_available,
        "drift_rooms": stale_available - actual_available,
        "drift_direction": "provider_overselling" if stale_available > actual_available else "provider_underselling",
    }
