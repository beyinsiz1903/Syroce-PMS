"""Pydantic models for the supplies marketplace."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

# ── Enums / literals ─────────────────────────────────────────────────────────
VendorStatus = Literal["pending", "approved", "suspended"]
ProductCategory = Literal[
    "banyo",          # havlu, terlik, şampuan, sabun, dental kit
    "yatak_tekstil",  # çarşaf, nevresim, yastık
    "temizlik",       # deterjan, kimyasal
    "mutfak_fb",      # F&B, mutfak ekipmanı
    "kirtasiye",      # kalem, defter, ofis
    "diger",
]
PaymentMethod = Literal["cash_on_delivery", "bank_transfer", "credit_card"]
OrderStatus = Literal[
    "pending",        # otel oluşturdu, toptancı onayı bekliyor
    "confirmed",      # toptancı onayladı
    "shipped",        # kargoya verildi
    "delivered",      # otel teslim aldı
    "cancelled",
]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── Vendor ───────────────────────────────────────────────────────────────────
class VendorRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    company_name: str = Field(min_length=2, max_length=200)
    contact_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=30)
    tax_no: str = Field(min_length=5, max_length=20)
    tax_office: str | None = None
    iban: str | None = None
    address: str | None = None
    city: str | None = None


class VendorLogin(BaseModel):
    email: EmailStr
    password: str


class VendorPublic(BaseModel):
    id: str
    email: EmailStr
    company_name: str
    contact_name: str
    phone: str
    tax_no: str
    tax_office: str | None = None
    iban: str | None = None
    address: str | None = None
    city: str | None = None
    status: VendorStatus
    commission_pct: float
    created_at: str


class VendorTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    vendor: VendorPublic


# ── Product ──────────────────────────────────────────────────────────────────
class PriceTier(BaseModel):
    """Kademeli fiyat: min_qty adet ve üzeri için price_try birim fiyat."""

    min_qty: int = Field(ge=1)
    price_try: float = Field(gt=0)


class Promotion(BaseModel):
    """Promosyon / kampanya — opsiyonel min_qty ve son tarih ile."""

    title: str = Field(min_length=2, max_length=120)
    discount_pct: float = Field(gt=0, le=90)
    min_qty: int | None = Field(default=None, ge=1)
    valid_until: str | None = None  # ISO date string


class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str | None = None
    category: ProductCategory
    images: list[str] = Field(default_factory=list)
    price_try: float = Field(gt=0)
    unit: str = Field(default="adet", max_length=30)  # adet, paket, koli
    pack_size: int = Field(default=1, ge=1)
    moq: int = Field(default=1, ge=1)  # minimum order quantity
    stock: int = Field(default=0, ge=0)
    is_active: bool = True
    # Esnek fiyat & teslim & vade (Elektraweb tedarik portalı muadili)
    price_tiers: list[PriceTier] = Field(default_factory=list)
    promotions: list[Promotion] = Field(default_factory=list)
    lead_time_days: int = Field(default=0, ge=0, le=365)  # ortalama teslim süresi
    payment_terms_days: int = Field(default=0, ge=0, le=365)  # vade (0 = peşin)


class ProductOut(ProductIn):
    id: str
    vendor_id: str
    vendor_name: str
    created_at: str
    updated_at: str


# ── Compare ──────────────────────────────────────────────────────────────────
class CompareOption(BaseModel):
    product_id: str
    product_name: str
    vendor_id: str
    vendor_name: str
    base_price_try: float
    effective_price_try: float  # qty + tier + promotion sonrası birim fiyat
    line_total_try: float
    qty: int
    moq: int
    unit: str
    stock: int
    lead_time_days: int
    payment_terms_days: int
    applied_tier: PriceTier | None = None
    applied_promotion: Promotion | None = None
    savings_pct: float = 0.0  # base'e göre indirim yüzdesi


class CompareResponse(BaseModel):
    category: str | None
    q: str | None
    qty: int
    options: list[CompareOption]  # ucuz → pahalı sıralı
    best_pick_id: str | None  # önerilen vendor (skorlama)


# ── Order ────────────────────────────────────────────────────────────────────
class OrderLineIn(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)


class OrderCreate(BaseModel):
    lines: list[OrderLineIn] = Field(min_length=1)
    payment_method: PaymentMethod
    shipping_address: str = Field(min_length=10, max_length=500)
    contact_name: str = Field(min_length=2, max_length=120)
    contact_phone: str = Field(min_length=7, max_length=30)
    notes: str | None = None


class OrderLineOut(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    unit_price: float
    line_total: float


class ShipmentInfo(BaseModel):
    carrier: str = Field(min_length=2, max_length=80)
    tracking_no: str = Field(min_length=2, max_length=80)
    note: str | None = None


class OrderOut(BaseModel):
    id: str
    order_no: str
    hotel_tenant_id: str
    hotel_name: str
    vendor_id: str
    vendor_name: str
    lines: list[OrderLineOut]
    subtotal: float
    commission_amount: float
    vendor_payout: float
    total: float
    payment_method: PaymentMethod
    status: OrderStatus
    shipping_address: str
    contact_name: str
    contact_phone: str
    notes: str | None = None
    shipment: ShipmentInfo | None = None
    created_at: str
    updated_at: str


class OrderStatusUpdate(BaseModel):
    status: Literal["confirmed", "cancelled"]
    reason: str | None = None
