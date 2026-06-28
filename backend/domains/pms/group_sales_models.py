"""
Group Sales Management Models
Group bookings, blocks, rooming lists, master folios
"""

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class GroupBlockStatus(str, Enum):
    """Grup bloğu durumu"""

    TENTATIVE = "tentative"  # Opsiyonel
    DEFINITE = "definite"  # Kesinleşmiş
    RELEASED = "released"  # Serbest bırakılmış
    COMPLETED = "completed"  # Tamamlanmış
    CANCELLED = "cancelled"  # İptal


class BillingType(str, Enum):
    """Fatura tipi"""

    MASTER_ACCOUNT = "master_account"  # Tümü master hesaba
    INDIVIDUAL = "individual"  # Her misafir kendi
    SPLIT = "split"  # Karma (oda master, ekstralar bireysel)


class GroupBlock(BaseModel):
    """Grup rezervasyon bloğu"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str

    # Group details
    group_name: str
    organization: str
    contact_name: str
    contact_email: str
    contact_phone: str

    # Booking details
    check_in: datetime
    check_out: datetime
    total_rooms: int
    rooms_picked_up: int = 0

    # Room breakdown
    room_breakdown: dict | None = None  # {"Standard": 10, "Deluxe": 5}

    # Rates
    group_rate: float
    room_type: str
    rate_code: str | None = None

    # Important dates
    cutoff_date: datetime
    release_date: datetime | None = None

    # Billing
    billing_type: BillingType
    master_folio_id: str | None = None
    payment_terms: str | None = None

    # Status
    status: GroupBlockStatus

    # Notes
    special_requirements: str | None = None
    catering_notes: str | None = None
    meeting_room_needs: str | None = None

    # Tracking
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GroupBlockCreate(BaseModel):
    """Grup bloğu oluşturma"""

    group_name: str
    organization: str
    contact_name: str
    contact_email: str
    contact_phone: str
    check_in: str
    check_out: str
    total_rooms: int
    room_breakdown: dict | None = None
    group_rate: float
    room_type: str
    cutoff_date: str
    billing_type: BillingType
    special_requirements: str | None = None


class RoomingListEntry(BaseModel):
    """Rooming list girdisi"""

    guest_name: str
    room_type: str
    check_in: str
    check_out: str
    special_requests: str | None = None
    email: str | None = None
    phone: str | None = None
    passport_number: str | None = None


class GroupMasterFolio(BaseModel):
    """Grup master folio"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    group_block_id: str

    # Financial
    total_charges: float = 0.0
    total_payments: float = 0.0
    balance: float = 0.0

    # Billing rules
    master_charges: list[str] = []  # Charge categories on master (e.g., ["room", "breakfast"])
    individual_charges: list[str] = []  # Individual charges (e.g., ["minibar", "spa"])

    # Status
    status: str = "open"  # open, closed
    closed_at: datetime | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
