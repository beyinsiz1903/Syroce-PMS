"""
ReservationImportBatch / ImportedReservation - Tracks reservation pull from providers.

Indexes:
  ReservationImportBatch: (tenant_id, connector_id, status, created_at)
  ImportedReservation: (tenant_id, connector_id, external_reservation_id): unique
                       (tenant_id, import_status)
                       (tenant_id, connector_id, payload_fingerprint)
                       (tenant_id, ack_status)
                       (batch_id)
"""
import uuid
import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field


class ImportStatus(str, Enum):
    PENDING = "pending"
    MATCHED = "matched"
    CREATED = "created"
    MODIFIED = "modified"
    CANCELLED = "cancelled"
    DUPLICATE = "duplicate"
    DUPLICATE_CANCEL = "duplicate_cancel"
    CONFLICT = "conflict"
    REVIEW = "review"
    FAILED = "failed"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"
    OUT_OF_ORDER = "out_of_order"


class ReviewReasonCode(str, Enum):
    MISSING_ROOM_MAPPING = "missing_room_mapping"
    MISSING_RATE_MAPPING = "missing_rate_mapping"
    CHECKED_IN_CANCELLATION = "checked_in_cancellation"
    MODIFICATION_AFTER_CANCEL = "modification_after_cancel"
    PAYLOAD_CONFLICT = "payload_conflict"
    UNKNOWN_ROOM_TYPE = "unknown_room_type"
    AMOUNT_MISMATCH = "amount_mismatch"
    DATE_OVERLAP = "date_overlap"
    MANUAL_ESCALATION = "manual_escalation"


class AckStatus(str, Enum):
    ACK_PENDING = "ack_pending"
    ACK_SENT = "ack_sent"
    ACK_FAILED = "ack_failed"
    NOT_REQUIRED = "not_required"


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
    duplicate_cancel_count: int = 0
    conflict_count: int = 0
    review_count: int = 0
    failed_count: int = 0
    out_of_order_count: int = 0
    ack_sent_count: int = 0
    ack_failed_count: int = 0

    # Pull metadata
    pull_from: Optional[str] = None
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

    # Idempotency key fields
    external_reservation_id: str
    external_confirmation_number: str = ""
    hr_number: str = ""
    message_uid: str = ""
    payload_fingerprint: str = ""
    channel_name: str = ""
    requires_ack: bool = False

    import_status: ImportStatus = ImportStatus.PENDING

    # Linked PMS reservation
    pms_booking_id: Optional[str] = None

    # Guest data
    guest_name: str = ""
    guest_email: str = ""
    guest_phone: str = ""

    # Stay data
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
    payment_type: str = ""
    special_requests: str = ""
    cancellation_policy: str = ""

    # Raw provider data
    raw_payload: Dict[str, Any] = Field(default_factory=dict)

    # Modification tracking
    is_modification: bool = False
    is_cancellation: bool = False
    previous_version_id: Optional[str] = None

    # Review metadata (enhanced)
    review_reason: Optional[str] = None
    review_reason_code: Optional[str] = None
    suggested_action: Optional[str] = None
    conflict_reason: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None

    # Manual review resolution
    dismissed_by: Optional[str] = None
    dismissed_at: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None
    reprocessed_at: Optional[str] = None

    # Error
    error_message: Optional[str] = None

    # Acknowledgement tracking
    ack_status: AckStatus = AckStatus.NOT_REQUIRED
    ack_sent_at: Optional[str] = None
    ack_failed_reason: Optional[str] = None

    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "ImportedReservation":
        doc.pop("_id", None)
        return cls(**doc)

    @staticmethod
    def compute_fingerprint(canonical_data: Dict[str, Any]) -> str:
        """Compute payload fingerprint for idempotency detection."""
        key_fields = {
            "arrival_date": canonical_data.get("arrival_date", ""),
            "departure_date": canonical_data.get("departure_date", ""),
            "room_type_id": canonical_data.get("room_type_id", ""),
            "rate_plan_id": canonical_data.get("rate_plan_id", ""),
            "adult_count": canonical_data.get("adult_count", 1),
            "child_count": canonical_data.get("child_count", 0),
            "total_amount": canonical_data.get("total_amount", 0.0),
            "status": canonical_data.get("status", ""),
            "guest_email": canonical_data.get("guest", {}).get("email", "") if isinstance(canonical_data.get("guest"), dict) else "",
            "special_requests": canonical_data.get("special_requests", ""),
        }
        raw = json.dumps(key_fields, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
