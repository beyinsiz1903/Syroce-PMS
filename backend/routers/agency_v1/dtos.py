"""
Agency v1 — KATI (strict) DTO'lar (ADR Karar 1: tel formati).

Tasarim ilkeleri (donmus):
  - Kanonik modele (channel_manager.domain.models.canonical) 1:1 hizali. Enum'lar
    (ReservationStatus / MealPlan) kanonikten dogrudan ithal edilir; yeni enum
    icat edilmez (drift onleme).
  - `extra="forbid"`: bilinmeyen alan -> 422 (Karar 1, fail-closed; sessiz yutma YOK).
  - Versiyonlama: govdede `schema_version` zorunlu ve SCHEMA_VERSION'a esit olmali
    (uyumsuz -> 422). URL major version ayrica router prefix'inde.
  - Tarihler strict `YYYY-MM-DD`; departure > arrival (model dogrulamasi).
  - PII (misafir alanlari) burada yalnizca SEKIL olarak tanimli; log'lanmaz.

Bu modul yalnizca dogrulama/sekil sozlesmesidir; DB/secret/IO icermez.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from channel_manager.domain.models.canonical import MealPlan, ReservationStatus

# Govde + yanitlarda tasinan sozlesme surumu (ADR Karar 1). Kirici degisiklik =
# yeni major (URL: /api/agency/v2). Bu deger donmus kontratin parcasidir.
SCHEMA_VERSION = "2026-06"

# Tum istek DTO'lari icin ortak katiyet: bilinmeyen alan reddedilir, string'ler
# bosluk-kirpilir. (b2b_api/connect_requests.py deseniyle simetrik.)
_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AgencyPaymentType(str, Enum):
    """ADR Karar 1 alan eslemesi: payment_type icin izinli degerler."""

    PREPAID = "prepaid"
    PAY_AT_HOTEL = "pay_at_hotel"
    CREDIT_CARD_GUARANTEE = "credit_card_guarantee"


# ADR Karar 1 (donmus): acente create/modify yalniz su status degerlerini
# tasiyabilir. Kanonik ReservationStatus daha genistir (no_show/checked_in/
# checked_out) — bunlar PMS-ici durum gecisleridir, acente sozlesmesinde KABUL
# EDILMEZ (uzerinden gelirse 422). Drift onleme: enum kanonikten ithal, alt-kume
# burada kisitlanir.
_AGENCY_ALLOWED_STATUSES = frozenset(
    {
        ReservationStatus.CONFIRMED,
        ReservationStatus.PROVISIONAL,
        ReservationStatus.CANCELLED,
        ReservationStatus.MODIFIED,
    }
)


def _validate_agency_status(value: ReservationStatus | None) -> ReservationStatus | None:
    if value is None:
        return value
    if value not in _AGENCY_ALLOWED_STATUSES:
        allowed = ", ".join(sorted(s.value for s in _AGENCY_ALLOWED_STATUSES))
        raise ValueError(f"status '{value.value}' acente sozlesmesinde gecersiz; izinli: {allowed}")
    return value


def _validate_iso_date(value: str) -> str:
    """Strict YYYY-MM-DD. Aksi halde ValueError -> 422."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except (ValueError, TypeError) as exc:
        raise ValueError("tarih 'YYYY-MM-DD' formatinda olmali") from exc
    return value


# ── Alt yapilar ──────────────────────────────────────────────────


class AgencyOccupancy(BaseModel):
    model_config = _STRICT
    adults: int = Field(1, ge=1, le=30)
    children: int = Field(0, ge=0, le=30)
    child_ages: list[int] = Field(default_factory=list, max_length=30)

    @field_validator("child_ages")
    @classmethod
    def _ages_in_range(cls, v: list[int]) -> list[int]:
        for age in v:
            if age < 0 or age > 17:
                raise ValueError("child_ages 0..17 araliginda olmali")
        return v


class AgencyPriceBreakdown(BaseModel):
    """Gece-bazli fiyat (kanonik PriceBreakdown alt kumesi)."""

    model_config = _STRICT
    date: str
    base_rate: float = Field(0.0, ge=0)
    net_rate: float = Field(0.0, ge=0)
    sell_rate: float = Field(0.0, ge=0)
    currency: str = Field(..., min_length=3, max_length=3)  # ADR: zorunlu (ISO-4217), sessiz default YOK
    adult_count: int = Field(2, ge=0, le=30)
    child_count: int = Field(0, ge=0, le=30)

    _v_date = field_validator("date")(_validate_iso_date)


class AgencyPricing(BaseModel):
    model_config = _STRICT
    total: float = Field(..., ge=0)
    sub_total: float = Field(0.0, ge=0)
    tax_total: float = Field(0.0, ge=0)
    currency: str = Field(..., min_length=3, max_length=3)  # ADR: zorunlu (ISO-4217), sessiz default YOK
    breakdown: list[AgencyPriceBreakdown] = Field(default_factory=list, max_length=370)


class AgencyCommission(BaseModel):
    model_config = _STRICT
    amount: float = Field(0.0, ge=0)
    rate: float = Field(0.0, ge=0, le=100)


class AgencyGuest(BaseModel):
    """Misafir PII (kanonik CanonicalGuest alt kumesi). Asla log'lanmaz."""

    model_config = _STRICT
    first_name: str = Field("", max_length=120)
    last_name: str = Field("", max_length=120)
    email: str = Field("", max_length=160)
    phone: str = Field("", max_length=40)
    nationality: str = Field("", max_length=80)
    national_id: str = Field("", max_length=64)
    country_code: str = Field("", max_length=3)
    address: str = Field("", max_length=240)
    city: str = Field("", max_length=120)
    country: str = Field("", max_length=80)
    postal_code: str = Field("", max_length=20)
    company_name: str = Field("", max_length=160)


# ── Govde DTO'lari ───────────────────────────────────────────────


class AgencyReservationCreate(BaseModel):
    """POST /api/agency/v1/reservations govdesi (ADR Karar 1/3.2)."""

    model_config = _STRICT

    schema_version: str
    agency_reservation_id: str = Field(..., min_length=1, max_length=120)
    confirmation_number: str = Field("", max_length=120)
    status: ReservationStatus = ReservationStatus.CONFIRMED
    arrival_date: str
    departure_date: str
    room_type_id: str = Field(..., min_length=1, max_length=120)
    rate_plan_id: str = Field(..., min_length=1, max_length=120)
    occupancy: AgencyOccupancy = Field(default_factory=AgencyOccupancy)
    room_count: int = Field(1, ge=1, le=100)
    meal_plan: MealPlan = MealPlan.RO
    pricing: AgencyPricing
    commission: AgencyCommission | None = None
    payment_type: AgencyPaymentType | None = None
    guest: AgencyGuest = Field(default_factory=AgencyGuest)
    special_requests: str = Field("", max_length=2000)

    _v_arrival = field_validator("arrival_date")(_validate_iso_date)
    _v_departure = field_validator("departure_date")(_validate_iso_date)
    _v_status = field_validator("status")(_validate_agency_status)

    @field_validator("schema_version")
    @classmethod
    def _version_match(cls, v: str) -> str:
        if v != SCHEMA_VERSION:
            raise ValueError(f"schema_version '{v}' desteklenmiyor; beklenen '{SCHEMA_VERSION}'")
        return v

    @model_validator(mode="after")
    def _departure_after_arrival(self) -> "AgencyReservationCreate":
        if self.departure_date <= self.arrival_date:
            raise ValueError("departure_date, arrival_date'ten sonra olmali")
        return self


class AgencyReservationModify(BaseModel):
    """PATCH /api/agency/v1/reservations/{id} govdesi (ADR Karar 3.3).

    Tum alanlar opsiyonel (kismi guncelleme); en az bir degisebilir alan zorunlu.
    `agency_reservation_id` path'ten gelir, govdede tekrar edilmez.
    """

    model_config = _STRICT

    schema_version: str
    status: ReservationStatus | None = None
    arrival_date: str | None = None
    departure_date: str | None = None
    room_type_id: str | None = Field(None, min_length=1, max_length=120)
    rate_plan_id: str | None = Field(None, min_length=1, max_length=120)
    occupancy: AgencyOccupancy | None = None
    room_count: int | None = Field(None, ge=1, le=100)
    meal_plan: MealPlan | None = None
    pricing: AgencyPricing | None = None
    commission: AgencyCommission | None = None
    payment_type: AgencyPaymentType | None = None
    special_requests: str | None = Field(None, max_length=2000)

    @field_validator("schema_version")
    @classmethod
    def _version_match(cls, v: str) -> str:
        if v != SCHEMA_VERSION:
            raise ValueError(f"schema_version '{v}' desteklenmiyor; beklenen '{SCHEMA_VERSION}'")
        return v

    _v_status = field_validator("status")(_validate_agency_status)

    @field_validator("arrival_date", "departure_date")
    @classmethod
    def _opt_iso_date(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_iso_date(v)

    @model_validator(mode="after")
    def _at_least_one_and_date_order(self) -> "AgencyReservationModify":
        mutable = (
            self.status,
            self.arrival_date,
            self.departure_date,
            self.room_type_id,
            self.rate_plan_id,
            self.occupancy,
            self.room_count,
            self.meal_plan,
            self.pricing,
            self.commission,
            self.payment_type,
            self.special_requests,
        )
        if all(v is None for v in mutable):
            raise ValueError("en az bir degisebilir alan saglanmali")
        if self.arrival_date is not None and self.departure_date is not None and self.departure_date <= self.arrival_date:
            raise ValueError("departure_date, arrival_date'ten sonra olmali")
        return self


# ── Yanit DTO'lari (belge/sekil; strict zorunlu degil) ───────────


class AgencyReservationResponse(BaseModel):
    pms_reservation_id: str
    confirmation_number: str = ""
    status: ReservationStatus
    schema_version: str = SCHEMA_VERSION


class AgencyAvailabilityRestrictions(BaseModel):
    closed: bool = False
    closed_to_arrival: bool = False
    closed_to_departure: bool = False
    min_stay: int | None = None


class AgencyAvailabilityNight(BaseModel):
    date: str
    room_type_id: str
    rate_plan_id: str = ""
    available: int = 0
    sell_rate: float = 0.0
    restrictions: AgencyAvailabilityRestrictions = Field(default_factory=AgencyAvailabilityRestrictions)


class AgencyAvailabilityResponse(BaseModel):
    schema_version: str = SCHEMA_VERSION
    currency: str = "TRY"
    nights: list[AgencyAvailabilityNight] = Field(default_factory=list)


class AgencyErrorResponse(BaseModel):
    """ADR ortak hata modeli. error_code ust seviyededir."""

    error_code: str
    schema_version: str = SCHEMA_VERSION
    conflict_date: str | None = None
    room_type_id: str | None = None
    available: int | None = None
