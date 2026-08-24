"""
Revenue / Pricing Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from datetime import date as DateType
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.audit import log_audit_event
from core.database import db
from core.security import (
    get_current_user,
    security,
)
from models.enums import CancellationPolicyType, ChannelType, MarketSegment, RateType
from models.schemas import Package, RatePlan, User
from modules.pms_core.role_permission_service import require_op  # v92 DW
from shared_kernel.idempotency import begin_idempotency, get_idempotency_key

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


router = APIRouter(prefix="/api", tags=["Revenue / Pricing"])
_PRICING_CATALOG_INDEX_INIT = False


async def _ensure_pricing_catalog_indexes() -> None:
    """Catalog uniqueness/date indexes are correctness requirements, not hints."""
    global _PRICING_CATALOG_INDEX_INIT
    if _PRICING_CATALOG_INDEX_INIT:
        return
    try:
        await db.rate_campaigns.create_index(
            [("tenant_id", 1), ("starts_on", 1), ("ends_on", 1)],
            name="rate_campaign_window",
        )
        await db.discount_codes.create_index(
            [("tenant_id", 1), ("code", 1)],
            unique=True,
            name="discount_code_tenant_unique",
        )
        await db.promotional_rates.create_index(
            [("tenant_id", 1), ("room_type", 1), ("starts_on", 1), ("ends_on", 1)],
            name="promotional_rate_window",
        )
        _PRICING_CATALOG_INDEX_INIT = True
    except Exception as exc:
        logger.error("Pricing catalog indexes could not be initialized: %s", exc)
        raise HTTPException(503, "Fiyat kataloğu altyapısı hazır değil") from exc


# ── Inline Models ──


class RatePlanFilter(BaseModel):
    channel: ChannelType | None = None
    company_id: str | None = None
    date: DateType | None = None


class RatePlanCreate(BaseModel):
    name: str
    code: str
    type: RateType = RateType.BAR
    currency: str = "EUR"
    base_price: float
    room_type: str = "Standard"  # Default room type
    market_segment: MarketSegment | None = None
    channel_restrictions: list[ChannelType] = []
    company_ids: list[str] = []
    valid_from: DateType | None = None
    valid_to: DateType | None = None
    days_of_week: list[int] = []
    min_stay: int | None = None
    max_stay: int | None = None
    cancellation_policy: CancellationPolicyType | None = None


class PackageCreate(BaseModel):
    name: str
    code: str
    description: str | None = None
    included_services: list[str] = []
    price_type: str = "per_room"
    additional_amount: float = 0.0
    linked_rate_plan_ids: list[str] = []


class DynamicRestrictionsRequest(BaseModel):
    date: str
    room_type: str
    min_los: int | None = None  # Minimum Length of Stay
    cta: bool = False  # Closed to Arrival
    ctd: bool = False  # Closed to Departure
    stop_sell: bool = False


class DemandForecast(BaseModel):
    """Demand forecast model"""

    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    date: str
    room_type: str | None = None
    forecasted_occupancy: float
    confidence: float
    factors: dict[str, Any] = {}  # events, seasonality, historical
    model_version: str = "ml-v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CompetitorRate(BaseModel):
    """Competitor rate scraping"""

    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    competitor_name: str
    date: str
    room_type: str
    rate: float
    source: str  # google_hotels, booking_com, expedia
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RateOverrideRequest(BaseModel):
    room_type: str
    date: str
    new_rate: float
    reason: str
    requires_approval: bool = True


class PromotionWindow(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=500)
    discount_type: Literal["percentage", "fixed"] = "percentage"
    discount_value: float = Field(gt=0, le=10_000_000)
    starts_on: DateType
    ends_on: DateType
    currency: str = Field(default="TRY", min_length=3, max_length=3)
    is_active: bool = True

    @field_validator("name", "description")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _valid_window(self):
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on, starts_on tarihinden önce olamaz")
        if self.discount_type == "percentage" and self.discount_value > 100:
            raise ValueError("Yüzde indirim 100'ü aşamaz")
        return self


class PromotionWindowUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=160)
    description: str | None = Field(None, max_length=500)
    discount_type: Literal["percentage", "fixed"] | None = None
    discount_value: float | None = Field(None, gt=0, le=10_000_000)
    starts_on: DateType | None = None
    ends_on: DateType | None = None
    currency: str | None = Field(None, min_length=3, max_length=3)
    is_active: bool | None = None


class DiscountCodeCreate(BaseModel):
    code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    description: str = Field(default="", max_length=500)
    discount_type: Literal["percentage", "fixed"] = "percentage"
    discount_value: float = Field(gt=0, le=10_000_000)
    starts_on: DateType
    ends_on: DateType
    usage_limit: int | None = Field(None, ge=1, le=10_000_000)
    currency: str = Field(default="TRY", min_length=3, max_length=3)
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def _code(cls, value: str) -> str:
        return str(value).strip().upper()

    @field_validator("currency")
    @classmethod
    def _discount_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _valid_discount(self):
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on, starts_on tarihinden önce olamaz")
        if self.discount_type == "percentage" and self.discount_value > 100:
            raise ValueError("Yüzde indirim 100'ü aşamaz")
        return self


class DiscountCodeUpdate(BaseModel):
    description: str | None = Field(None, max_length=500)
    discount_type: Literal["percentage", "fixed"] | None = None
    discount_value: float | None = Field(None, gt=0, le=10_000_000)
    starts_on: DateType | None = None
    ends_on: DateType | None = None
    usage_limit: int | None = Field(None, ge=1, le=10_000_000)
    currency: str | None = Field(None, min_length=3, max_length=3)
    is_active: bool | None = None


class PromotionalRateCreate(BaseModel):
    room_type: str = Field(min_length=1, max_length=160)
    regular_rate: float = Field(ge=0, le=10_000_000)
    promo_rate: float = Field(ge=0, le=10_000_000)
    starts_on: DateType
    ends_on: DateType
    conditions: str = Field(default="", max_length=500)
    currency: str = Field(default="TRY", min_length=3, max_length=3)
    is_active: bool = True

    @model_validator(mode="after")
    def _valid_promo(self):
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on, starts_on tarihinden önce olamaz")
        if self.promo_rate > self.regular_rate:
            raise ValueError("Promosyon fiyatı normal fiyattan yüksek olamaz")
        return self


class PromotionalRateUpdate(BaseModel):
    regular_rate: float | None = Field(None, ge=0, le=10_000_000)
    promo_rate: float | None = Field(None, ge=0, le=10_000_000)
    starts_on: DateType | None = None
    ends_on: DateType | None = None
    conditions: str | None = Field(None, max_length=500)
    currency: str | None = Field(None, min_length=3, max_length=3)
    is_active: bool | None = None


def _actor(user: User) -> str:
    return str(getattr(user, "id", None) or getattr(user, "email", None) or "unknown")


def _serialize_dates(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value.isoformat() if isinstance(value, DateType) else value for key, value in data.items()}


def _window_status(row: dict[str, Any], today: DateType | None = None) -> str:
    today = today or DateType.today()
    if not row.get("is_active", True):
        return "inactive"
    try:
        starts = DateType.fromisoformat(str(row["starts_on"]))
        ends = DateType.fromisoformat(str(row["ends_on"]))
    except (KeyError, TypeError, ValueError):
        return "invalid"
    if today < starts:
        return "upcoming"
    if today > ends:
        return "expired"
    return "active"


async def _audit_rate_mutation(user: User, action: str, entity_type: str, doc: dict[str, Any], before: dict[str, Any] | None = None) -> None:
    await log_audit_event(
        tenant_id=user.tenant_id,
        user_id=_actor(user),
        action=action,
        entity_type=entity_type,
        entity_id=doc["id"],
        details=f"{entity_type} kaydı güncellendi",
        before_value=before,
        after_value=doc,
        db=db,
    )


# ─── Endpoints (split: rates) ───


@router.get("/rates/rate-plans", response_model=list[RatePlan])
async def list_rate_plans(channel: ChannelType | None = None, company_id: str | None = None, stay_date: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    current_user = await get_current_user(credentials)
    query: dict[str, Any] = {"tenant_id": current_user.tenant_id, "is_active": True}

    if channel:
        query["$or"] = [
            {"channel_restrictions": {"$size": 0}},
            {"channel_restrictions": channel.value},
        ]
    if company_id:
        query["company_ids"] = company_id
    if stay_date:
        try:
            d = datetime.fromisoformat(stay_date).date()
            or_filters = []
            or_filters.append({"valid_from": None})
            or_filters.append({"valid_to": None})
            query["$and"] = [
                {
                    "$or": [
                        {"valid_from": {"$lte": d.isoformat()}},
                        {"valid_from": None},
                    ]
                },
                {
                    "$or": [
                        {"valid_to": {"$gte": d.isoformat()}},
                        {"valid_to": None},
                    ]
                },
            ]
        except Exception:
            pass

    cursor = db.rate_plans.find(query).sort("name", 1)
    results: list[RatePlan] = []
    async for doc in cursor:
        # Normalize date strings to actual date
        if "valid_from" in doc and isinstance(doc["valid_from"], str):
            try:
                doc["valid_from"] = datetime.fromisoformat(doc["valid_from"]).date().isoformat()
            except Exception:
                pass
        if "valid_to" in doc and isinstance(doc["valid_to"], str):
            try:
                doc["valid_to"] = datetime.fromisoformat(doc["valid_to"]).date().isoformat()
            except Exception:
                pass
        results.append(RatePlan(**doc))
    return results


@router.post("/rates/rate-plans", response_model=RatePlan)
async def create_rate_plan(
    payload: RatePlanCreate,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v95 DW
):
    # Zero-Bloat: header-gated Idempotency-Key. Without the header this is a
    # NO-OP and behaviour is byte-identical to before (pilot_drift=0).
    idem_key = get_idempotency_key(http_request)
    guard, replay = await begin_idempotency(
        db,
        http_request,
        tenant_id=current_user.tenant_id,
        scope="rates.rate_plans",
        payload=payload.model_dump(),
    )
    if replay is not None:
        return replay

    data = payload.model_dump()
    data["tenant_id"] = current_user.tenant_id
    # Map base_price to base_rate for the RatePlan model and keep base_price for compatibility
    base_price = data.get("base_price")
    data["base_rate"] = base_price
    data["base_price"] = base_price  # Keep for compatibility
    if data.get("valid_from"):
        data["valid_from"] = data["valid_from"].isoformat()
    if data.get("valid_to"):
        data["valid_to"] = data["valid_to"].isoformat()
    if idem_key:
        # Crash-retry backstop: a deterministic id makes a re-attempt AFTER the
        # idempotency sentinel expired converge on the SAME record instead of
        # inserting a duplicate (there is no unique business index here).
        data["id"] = str(
            uuid.uuid5(
                uuid.NAMESPACE_OID,
                f"{current_user.tenant_id}:rates.rate_plans:{idem_key}",
            )
        )
        existing = await db.rate_plans.find_one({"tenant_id": current_user.tenant_id, "id": data["id"]}, {"_id": 0})
        if existing is not None:
            rate_plan = RatePlan(**existing)
            await guard.complete(rate_plan.model_dump())
            return rate_plan
    rate_plan = RatePlan(**data)
    await db.rate_plans.insert_one(rate_plan.model_dump())
    await guard.complete(rate_plan.model_dump())
    return rate_plan


@router.get("/rates/packages", response_model=list[Package])
async def list_packages(credentials: HTTPAuthorizationCredentials = Depends(security)):
    current_user = await get_current_user(credentials)
    cursor = db.packages.find({"tenant_id": current_user.tenant_id, "is_active": True}).sort("name", 1)
    results: list[Package] = []
    async for doc in cursor:
        results.append(Package(**doc))
    return results


@router.post("/rates/packages", response_model=Package)
async def create_package(
    payload: PackageCreate,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v95 DW
):
    # Zero-Bloat: header-gated Idempotency-Key. Without the header this is a
    # NO-OP and behaviour is byte-identical to before (pilot_drift=0).
    idem_key = get_idempotency_key(http_request)
    guard, replay = await begin_idempotency(
        db,
        http_request,
        tenant_id=current_user.tenant_id,
        scope="rates.packages",
        payload=payload.model_dump(),
    )
    if replay is not None:
        return replay

    data = payload.model_dump()
    data["tenant_id"] = current_user.tenant_id
    if idem_key:
        # Crash-retry backstop: deterministic id converges a post-sentinel-expiry
        # retry on the same record (no unique business index here).
        data["id"] = str(
            uuid.uuid5(
                uuid.NAMESPACE_OID,
                f"{current_user.tenant_id}:rates.packages:{idem_key}",
            )
        )
        existing = await db.packages.find_one({"tenant_id": current_user.tenant_id, "id": data["id"]}, {"_id": 0})
        if existing is not None:
            package = Package(**existing)
            await guard.complete(package.model_dump())
            return package
    package = Package(**data)
    await db.packages.insert_one(package.model_dump())
    await guard.complete(package.model_dump())
    return package


@router.get("/rates/campaigns")
async def get_active_campaigns(
    status: str | None = None,  # active, upcoming, expired
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Tenant kampanyalarını gerçek, kalıcı veri kaynağından getirir."""
    current_user = await get_current_user(credentials)
    rows = await db.rate_campaigns.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("starts_on", -1).to_list(500)
    for row in rows:
        row["status"] = _window_status(row)
        row.setdefault("bookings_count", 0)
        row.setdefault("revenue_generated", 0)
    if status:
        allowed = {"active", "upcoming", "expired", "inactive"}
        if status not in allowed:
            raise HTTPException(400, f"Geçersiz durum. İzinli: {sorted(allowed)}")
        rows = [row for row in rows if row["status"] == status]
    return {
        "campaigns": rows,
        "count": len(rows),
        "data_available": True,
        "total_revenue": sum(float(row.get("revenue_generated", 0) or 0) for row in rows),
        "total_bookings": sum(int(row.get("bookings_count", 0) or 0) for row in rows),
    }


@router.post("/rates/campaigns", status_code=201)
async def create_campaign(
    payload: PromotionWindow,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    await _ensure_pricing_catalog_indexes()
    now = datetime.now(UTC).isoformat()
    doc = {
        **_serialize_dates(payload.model_dump()),
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "bookings_count": 0,
        "revenue_generated": 0.0,
        "created_at": now,
        "created_by": _actor(current_user),
        "updated_at": now,
        "updated_by": _actor(current_user),
    }
    await db.rate_campaigns.insert_one(doc.copy())
    await _audit_rate_mutation(current_user, "rates.campaign.created", "rate_campaign", doc)
    doc.pop("tenant_id", None)
    doc["status"] = _window_status(doc)
    return doc


@router.patch("/rates/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    payload: PromotionWindowUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    query = {"tenant_id": current_user.tenant_id, "id": campaign_id}
    before = await db.rate_campaigns.find_one(query, {"_id": 0})
    if not before:
        raise HTTPException(404, "Kampanya bulunamadı")
    changes = _serialize_dates(payload.model_dump(exclude_unset=True))
    if not changes:
        raise HTTPException(400, "Güncellenecek alan yok")
    merged = {**before, **changes}
    PromotionWindow(**{key: merged[key] for key in PromotionWindow.model_fields})
    changes.update({"updated_at": datetime.now(UTC).isoformat(), "updated_by": _actor(current_user)})
    await db.rate_campaigns.update_one(query, {"$set": changes})
    updated = {**before, **changes}
    await _audit_rate_mutation(current_user, "rates.campaign.updated", "rate_campaign", updated, before)
    updated.pop("tenant_id", None)
    updated["status"] = _window_status(updated)
    return updated


# 2. GET /api/rates/discount-codes - Discount codes


@router.get("/rates/discount-codes")
async def get_discount_codes(active_only: bool = True, credentials: HTTPAuthorizationCredentials = Depends(security)):
    current_user = await get_current_user(credentials)
    query: dict[str, Any] = {"tenant_id": current_user.tenant_id}
    rows = await db.discount_codes.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for row in rows:
        row["status"] = _window_status(row)
        row.setdefault("usage_count", 0)
    if active_only:
        rows = [row for row in rows if row["status"] == "active"]
    return {
        "discount_codes": rows,
        "count": len(rows),
        "data_available": True,
        "total_usage": sum(int(row.get("usage_count", 0) or 0) for row in rows),
    }


@router.post("/rates/discount-codes", status_code=201)
async def create_discount_code(
    payload: DiscountCodeCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    await _ensure_pricing_catalog_indexes()
    exists = await db.discount_codes.find_one(
        {"tenant_id": current_user.tenant_id, "code": payload.code}, {"_id": 1}
    )
    if exists:
        raise HTTPException(409, "Bu indirim kodu zaten kullanılıyor")
    now = datetime.now(UTC).isoformat()
    doc = {
        **_serialize_dates(payload.model_dump()),
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "usage_count": 0,
        "created_at": now,
        "created_by": _actor(current_user),
        "updated_at": now,
        "updated_by": _actor(current_user),
    }
    await db.discount_codes.insert_one(doc.copy())
    await _audit_rate_mutation(current_user, "rates.discount_code.created", "discount_code", doc)
    doc.pop("tenant_id", None)
    doc["status"] = _window_status(doc)
    return doc


@router.patch("/rates/discount-codes/{discount_id}")
async def update_discount_code(
    discount_id: str,
    payload: DiscountCodeUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    query = {"tenant_id": current_user.tenant_id, "id": discount_id}
    before = await db.discount_codes.find_one(query, {"_id": 0})
    if not before:
        raise HTTPException(404, "İndirim kodu bulunamadı")
    changes = _serialize_dates(payload.model_dump(exclude_unset=True))
    if not changes:
        raise HTTPException(400, "Güncellenecek alan yok")
    merged = {**before, **changes}
    DiscountCodeCreate(**{key: merged[key] for key in DiscountCodeCreate.model_fields})
    changes.update({"updated_at": datetime.now(UTC).isoformat(), "updated_by": _actor(current_user)})
    await db.discount_codes.update_one(query, {"$set": changes})
    updated = {**before, **changes}
    await _audit_rate_mutation(current_user, "rates.discount_code.updated", "discount_code", updated, before)
    updated.pop("tenant_id", None)
    updated["status"] = _window_status(updated)
    return updated


# 3. POST /api/rates/override - Rate override


@router.post("/rates/override")
async def create_rate_override(
    request: RateOverrideRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("override_rate")),  # v92 DW
):
    """
    Create rate override (with optional approval flow)
    """
    current_user = await get_current_user(credentials)

    override = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "room_type": request.room_type,
        "date": request.date,
        "new_rate": request.new_rate,
        "reason": request.reason,
        "created_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "pending_approval" if request.requires_approval else "applied",
    }

    if request.requires_approval:
        # Create approval request
        approval = {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "approval_type": "price_override",
            "reference_id": override["id"],
            "amount": request.new_rate,
            "reason": request.reason,
            "status": "pending",
            "requested_by": current_user.name,
            "request_date": datetime.now(UTC).isoformat(),
        }
        await db.approvals.insert_one(approval)

        return {"message": "Price change sent for approval", "override_id": override["id"], "approval_id": approval["id"], "status": "pending_approval"}
    else:
        await db.rate_overrides.insert_one(override)
        return {"message": "Price change applied", "override_id": override["id"], "status": "applied"}


# 4. GET /api/rates/promotional - Promotional rates


@router.get("/rates/promotional")
async def get_promotional_rates(credentials: HTTPAuthorizationCredentials = Depends(security)):
    current_user = await get_current_user(credentials)
    rows = await db.promotional_rates.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("starts_on", -1).to_list(1000)
    for row in rows:
        regular = float(row.get("regular_rate", 0) or 0)
        promo = float(row.get("promo_rate", 0) or 0)
        row["discount_pct"] = round(((regular - promo) / regular) * 100, 2) if regular else 0
        row["status"] = _window_status(row)
    return {"promotional_rates": rows, "count": len(rows), "data_available": True}


@router.post("/rates/promotional", status_code=201)
async def create_promotional_rate(
    payload: PromotionalRateCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    await _ensure_pricing_catalog_indexes()
    now = datetime.now(UTC).isoformat()
    doc = {
        **_serialize_dates(payload.model_dump()),
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "created_at": now,
        "created_by": _actor(current_user),
        "updated_at": now,
        "updated_by": _actor(current_user),
    }
    await db.promotional_rates.insert_one(doc.copy())
    await _audit_rate_mutation(current_user, "rates.promotional.created", "promotional_rate", doc)
    doc.pop("tenant_id", None)
    regular = float(doc["regular_rate"])
    doc["discount_pct"] = round(((regular - float(doc["promo_rate"])) / regular) * 100, 2) if regular else 0
    doc["status"] = _window_status(doc)
    return doc


@router.patch("/rates/promotional/{promo_id}")
async def update_promotional_rate(
    promo_id: str,
    payload: PromotionalRateUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),
):
    query = {"tenant_id": current_user.tenant_id, "id": promo_id}
    before = await db.promotional_rates.find_one(query, {"_id": 0})
    if not before:
        raise HTTPException(404, "Promosyon fiyatı bulunamadı")
    changes = _serialize_dates(payload.model_dump(exclude_unset=True))
    if not changes:
        raise HTTPException(400, "Güncellenecek alan yok")
    merged = {**before, **changes}
    PromotionalRateCreate(**{key: merged[key] for key in PromotionalRateCreate.model_fields})
    changes.update({"updated_at": datetime.now(UTC).isoformat(), "updated_by": _actor(current_user)})
    await db.promotional_rates.update_one(query, {"$set": changes})
    updated = {**before, **changes}
    await _audit_rate_mutation(current_user, "rates.promotional.updated", "promotional_rate", updated, before)
    updated.pop("tenant_id", None)
    regular = float(updated["regular_rate"])
    updated["discount_pct"] = round(((regular - float(updated["promo_rate"])) / regular) * 100, 2) if regular else 0
    updated["status"] = _window_status(updated)
    return updated


# ============================================================================
# CHANNEL MANAGER MOBILE
# ============================================================================

# 1. GET /api/channels/status - Channel connection status
