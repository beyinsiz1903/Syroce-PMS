"""
Revenue / Pricing Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
from __future__ import annotations
from modules.pms_core.role_permission_service import require_op  # v92 DW

import logging
import uuid
from datetime import UTC, datetime, timedelta
from datetime import date as DateType
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field

from core.database import db
from core.security import (
    get_current_user,
    security,
)
from models.enums import CancellationPolicyType, ChannelType, MarketSegment, RateType
from models.schemas import Package, RatePlan, User

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator


router = APIRouter(prefix="/api", tags=["Revenue / Pricing"])


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


# ─── Endpoints (split: rates) ───


@router.get("/rates/rate-plans", response_model=list[RatePlan])
async def list_rate_plans(
    channel: ChannelType | None = None,
    company_id: str | None = None,
    stay_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
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
                {"$or": [
                    {"valid_from": {"$lte": d.isoformat()}},
                    {"valid_from": None},
                ]},
                {"$or": [
                    {"valid_to": {"$gte": d.isoformat()}},
                    {"valid_to": None},
                ]},
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
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v95 DW
):
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
    rate_plan = RatePlan(**data)
    doc = rate_plan.model_dump()
    await db.rate_plans.insert_one(doc)
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
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v95 DW
):
    data = payload.model_dump()
    data["tenant_id"] = current_user.tenant_id
    package = Package(**data)
    await db.packages.insert_one(package.model_dump())
    return package





@router.get("/rates/campaigns")
async def get_active_campaigns(
    status: str | None = None,  # active, upcoming, expired
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get active promotional campaigns
    """
    await get_current_user(credentials)

    today = datetime.now().date()

    # Sample campaigns
    campaigns = [
        {
            'id': str(uuid.uuid4()),
            'name': 'Early Booking Discount',
            'description': '20% discount for reservations 30+ days in advance',
            'discount_type': 'percentage',
            'discount_value': 20,
            'start_date': (today - timedelta(days=10)).isoformat(),
            'end_date': (today + timedelta(days=50)).isoformat(),
            'status': 'active',
            'bookings_count': 45,
            'revenue_generated': 67500
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Weekend Special',
            'description': 'Fixed rate for Friday-Sunday stays',
            'discount_type': 'fixed',
            'discount_value': 1500,
            'start_date': today.isoformat(),
            'end_date': (today + timedelta(days=90)).isoformat(),
            'status': 'active',
            'bookings_count': 23,
            'revenue_generated': 34500
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Extended Stay',
            'description': '25% discount for stays of 7 nights or more',
            'discount_type': 'percentage',
            'discount_value': 25,
            'start_date': (today - timedelta(days=30)).isoformat(),
            'end_date': (today + timedelta(days=60)).isoformat(),
            'status': 'active',
            'bookings_count': 12,
            'revenue_generated': 28000
        }
    ]

    # Filter by status
    if status:
        campaigns = [c for c in campaigns if c['status'] == status]

    return {
        'campaigns': campaigns,
        'count': len(campaigns),
        'total_revenue': sum(c['revenue_generated'] for c in campaigns),
        'total_bookings': sum(c['bookings_count'] for c in campaigns)
    }


# 2. GET /api/rates/discount-codes - Discount codes




@router.get("/rates/discount-codes")
async def get_discount_codes(
    active_only: bool = True,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get discount codes
    """
    await get_current_user(credentials)

    codes = [
        {
            'id': str(uuid.uuid4()),
            'code': 'WELCOME20',
            'description': 'First booking discount',
            'discount_type': 'percentage',
            'discount_value': 20,
            'usage_count': 156,
            'usage_limit': 500,
            'valid_from': (datetime.now() - timedelta(days=60)).isoformat()[:10],
            'valid_until': (datetime.now() + timedelta(days=30)).isoformat()[:10],
            'is_active': True
        },
        {
            'id': str(uuid.uuid4()),
            'code': 'SUMMER50',
            'description': 'Summer campaign',
            'discount_type': 'fixed',
            'discount_value': 500,
            'usage_count': 89,
            'usage_limit': 200,
            'valid_from': (datetime.now() - timedelta(days=30)).isoformat()[:10],
            'valid_until': (datetime.now() + timedelta(days=60)).isoformat()[:10],
            'is_active': True
        }
    ]

    if active_only:
        codes = [c for c in codes if c['is_active']]

    return {
        'discount_codes': codes,
        'count': len(codes),
        'total_usage': sum(c['usage_count'] for c in codes)
    }


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
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'room_type': request.room_type,
        'date': request.date,
        'new_rate': request.new_rate,
        'reason': request.reason,
        'created_by': current_user.name,
        'created_at': datetime.now(UTC).isoformat(),
        'status': 'pending_approval' if request.requires_approval else 'applied'
    }

    if request.requires_approval:
        # Create approval request
        approval = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'approval_type': 'price_override',
            'reference_id': override['id'],
            'amount': request.new_rate,
            'reason': request.reason,
            'status': 'pending',
            'requested_by': current_user.name,
            'request_date': datetime.now(UTC).isoformat()
        }
        await db.approvals.insert_one(approval)

        return {
            'message': 'Price change sent for approval',
            'override_id': override['id'],
            'approval_id': approval['id'],
            'status': 'pending_approval'
        }
    else:
        await db.rate_overrides.insert_one(override)
        return {
            'message': 'Price change applied',
            'override_id': override['id'],
            'status': 'applied'
        }


# 4. GET /api/rates/promotional - Promotional rates




@router.get("/rates/promotional")
async def get_promotional_rates(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get promotional rates
    """
    await get_current_user(credentials)

    promo_rates = [
        {
            'room_type': 'Standard Room',
            'regular_rate': 1200,
            'promo_rate': 960,
            'discount_pct': 20,
            'valid_dates': f"{datetime.now().date().isoformat()} - {(datetime.now().date() + timedelta(days=30)).isoformat()}",
            'conditions': 'Minimum 2 gece konaklama'
        },
        {
            'room_type': 'Deluxe Room',
            'regular_rate': 1800,
            'promo_rate': 1620,
            'discount_pct': 10,
            'valid_dates': f"{datetime.now().date().isoformat()} - {(datetime.now().date() + timedelta(days=14)).isoformat()}",
            'conditions': 'Weekday reservations'
        }
    ]

    return {
        'promotional_rates': promo_rates,
        'count': len(promo_rates)
    }


# ============================================================================
# CHANNEL MANAGER MOBILE
# ============================================================================

# 1. GET /api/channels/status - Channel connection status


