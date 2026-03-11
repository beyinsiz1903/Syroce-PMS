"""
ReservationImportBatch / ImportedReservation - Tracks reservation pull from providers.

Indexes:
  ReservationImportBatch: (tenant_id, connector_id, status, created_at)
  ImportedReservation: (tenant_id, connector_id, external_reservation_id): unique
                       (tenant_id, import_status)
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field


class ImportStatus(str, Enum):
    PENDING = "pending"
    MATCHED = "matched"
    CREATED = "created"
    MODIFIED = "modified"
    CANCELLED = "cancelled"
    DUPLICATE = "duplicate"
    REVIEW = "review"  # Needs manual review
    FAILED = "failed"
    ACKNOWLEDGED = "acknowledged"


class ReservationImportBatch(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    connector_id: str

    status: str = "in_progress"  # in_progress, completed, partial, failed
    total_reservations: int = 0
    new_count: int = 0
    modified_count: int = 0
    cancelled_count: int = 0
    duplicate_count: int = 0
    review_count: int = 0
    failed_count: int = 0

    # Pull metadata
    pull_from: Optional[str] = None  # Start of pull window
    pull_to: Optional[str] = None
    triggered_by: str = "system"

    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None

    def to_doc(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "ReservationImportBatch":
        doc.pop("_id", None)
        return cls(**doc)


class ImportedReservation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    connector_id: str
    batch_id: str

    # External reference (idempotency key)
    external_reservation_id: str
    external_confirmation_number: str = ""
    channel_name: str = ""  # e.g., "Booking.com", "Expedia"

    import_status: ImportStatus = ImportStatus.PENDING

    # Linked PMS reservation (after successful import)
    pms_booking_id: Optional[str] = None

    # Reservation data (canonical form)
    guest_name: str = ""
    guest_email: str = ""
    guest_phone: str = ""
    arrival_date: str = ""
    departure_date: str = ""
    room_type_external_id: str = ""
    rate_plan_external_id: str = ""
    room_type_mapped_id: Optional[str] = None
    rate_plan_mapped_id: Optional[str] = None
    adult_count: int = 1
    child_count: int = 0
    total_amount: float = 0.0
    currency: str = "TRY"
    payment_type: str = ""  # prepaid, pay_at_hotel
    special_requests: str = ""
    cancellation_policy: str = ""

    # Raw provider data for debugging
    raw_payload: Dict[str, Any] = Field(default_factory=dict)

    # Modification tracking
    is_modification: bool = False
    is_cancellation: bool = False
    previous_version_id: Optional[str] = None

    # Review metadata
    review_reason: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None

    # Error
    error_message: Optional[str] = None

    # Acknowledgement to provider
    acknowledged: bool = False
    acknowledged_at: Optional[str] = None
    acknowledgement_id: Optional[str] = None

    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "ImportedReservation":
        doc.pop("_id", None)
        return cls(**doc)
