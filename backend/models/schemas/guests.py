"""Auto-split from schemas.py — domain: guests."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


# Guest & Booking Models
class GuestCreate(BaseModel):
    name: str
    email: str = ""
    phone: str = ""
    id_number: str = ""
    nationality: str | None = None
    address: str | None = None
    vip_status: bool = False


class Guest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    email: str | None = ""
    phone: str | None = ""
    id_number: str | None = ""
    nationality: str | None = None
    address: str | None = None
    vip_status: bool = False
    loyalty_points: int = 0
    total_stays: int = 0
    total_spend: float = 0.0
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # v95+ — VIP / tekrar misafir alarm bilgileri
    allergies: str | None = None  # "Ananas, fındık" gibi virgüllü liste
    dietary_restrictions: str | None = None  # "Vejeteryan", "Helal", "Glutensiz"
    pillow_preference: str | None = None  # "Kaz tüyü", "Sert", "İnce"
    room_preference: str | None = None  # "Yüksek kat, deniz manzarası"
    important_notes: str | None = None  # Resepsiyona özel uyarı (kavga, hassasiyet)
    anniversary_date: str | None = None  # "MM-DD" — yıldönümü
    birthday: str | None = None  # "MM-DD" — doğum günü
    last_visit_date: str | None = None  # "YYYY-MM-DD" — son ziyaret
    blacklisted: bool = False  # Kara liste (madde 7)
    blacklist_reason: str | None = None  # Sebep (ödeme, hasar, kavga)
