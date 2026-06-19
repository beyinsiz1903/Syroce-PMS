"""
Revenue / Pricing Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
from __future__ import annotations

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
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

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


# ─── Endpoints (split: anomaly) ───


@router.get("/anomaly/detect")
@cached(ttl=120, key_prefix="anomaly_detect")
async def detect_anomalies(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v86 DV: revenue anomaly detection
):
    """
    Detect real-time anomalies in key metrics
    Returns active anomalies with severity levels
    """

    anomalies = []

    # Get recent data for comparison
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    # 1. Occupancy Drop Detection
    today_occupancy = await db.rooms.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'occupied'
    })
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})

    yesterday_bookings = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': yesterday.isoformat()
    })

    if total_rooms > 0:
        today_occ_pct = today_occupancy / total_rooms * 100
        yesterday_occ_pct = yesterday_bookings / total_rooms * 100

        if yesterday_occ_pct > 0 and (yesterday_occ_pct - today_occ_pct) > 15:
            anomalies.append({
                'id': str(uuid.uuid4()),
                'type': 'occupancy_drop',
                'severity': 'high',
                'title': 'Sudden Occupancy Drop',
                'message': f'Occupancy dropped from {yesterday_occ_pct:.1f}% to {today_occ_pct:.1f}%',
                'metric': 'occupancy',
                'current_value': round(today_occ_pct, 1),
                'previous_value': round(yesterday_occ_pct, 1),
                'variance': round(today_occ_pct - yesterday_occ_pct, 1),
                'detected_at': datetime.now(UTC).isoformat()
            })

    # 2. Cancellation Spike Detection
    today_cancellations = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'cancelled',
        'updated_at': {'$gte': today.isoformat()}
    })

    week_avg_cancellations = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'cancelled',
        'updated_at': {'$gte': week_ago.isoformat()}
    }) / 7

    if today_cancellations > week_avg_cancellations * 2:
        anomalies.append({
            'id': str(uuid.uuid4()),
            'type': 'cancellation_spike',
            'severity': 'high',
            'title': 'Cancellation Increase Detected',
            'message': f'{today_cancellations} cancellations today (weekly avg: {week_avg_cancellations:.1f})',
            'metric': 'cancellations',
            'current_value': today_cancellations,
            'previous_value': round(week_avg_cancellations, 1),
            'variance': round(today_cancellations - week_avg_cancellations, 1),
            'detected_at': datetime.now(UTC).isoformat()
        })

    # 3. Revenue Deviation Detection
    today_revenue = 0
    async for payment in db.payments.find({
        'tenant_id': current_user.tenant_id,
        'payment_date': {'$gte': today.isoformat()}
    }):
        today_revenue += payment.get('amount', 0)

    # Get average revenue from last week
    week_revenue = 0
    async for payment in db.payments.find({
        'tenant_id': current_user.tenant_id,
        'payment_date': {'$gte': week_ago.isoformat()}
    }):
        week_revenue += payment.get('amount', 0)

    avg_daily_revenue = week_revenue / 7 if week_revenue > 0 else 10000

    if avg_daily_revenue > 0 and abs(today_revenue - avg_daily_revenue) / avg_daily_revenue > 0.2:
        severity = 'high' if today_revenue < avg_daily_revenue else 'medium'
        anomalies.append({
            'id': str(uuid.uuid4()),
            'type': 'revpar_deviation',
            'severity': severity,
            'title': 'Revenue Deviation Detected',
            'message': f'Daily revenue deviates {abs(today_revenue - avg_daily_revenue) / avg_daily_revenue * 100:.1f}% from expected',
            'metric': 'revenue',
            'current_value': round(today_revenue, 2),
            'previous_value': round(avg_daily_revenue, 2),
            'variance': round(today_revenue - avg_daily_revenue, 2),
            'detected_at': datetime.now(UTC).isoformat()
        })

    # 4. Maintenance Spike Detection
    urgent_maintenance = await db.maintenance_tasks.count_documents({
        'tenant_id': current_user.tenant_id,
        'priority': {'$in': ['high', 'urgent']},
        'status': 'pending',
        'created_at': {'$gte': today.isoformat()}
    })

    # Önceki dönem (dün) gerçek bekleyen urgent maintenance sayısı (sabit 2 kaldırıldı)
    prev_day = today - timedelta(days=1)
    prev_urgent_maintenance = await db.maintenance_tasks.count_documents({
        'tenant_id': current_user.tenant_id,
        'priority': {'$in': ['high', 'urgent']},
        'status': 'pending',
        'created_at': {'$gte': prev_day.isoformat(), '$lt': today.isoformat()}
    })

    if urgent_maintenance > 5:
        anomalies.append({
            'id': str(uuid.uuid4()),
            'type': 'maintenance_spike',
            'severity': 'medium',
            'title': 'Maintenance Requests Increase',
            'message': f'{urgent_maintenance} urgent maintenance request(s) pending',
            'metric': 'maintenance',
            'current_value': urgent_maintenance,
            'previous_value': prev_urgent_maintenance,
            'variance': urgent_maintenance - prev_urgent_maintenance,
            'detected_at': datetime.now(UTC).isoformat()
        })

    return {
        'anomalies': anomalies,
        'count': len(anomalies),
        'high_severity_count': len([a for a in anomalies if a['severity'] == 'high']),
        'detected_at': datetime.now(UTC).isoformat()
    }


# 2. GET /api/anomaly/alerts - Get active anomaly alerts




@router.get("/anomaly/alerts")
async def get_anomaly_alerts(
    severity: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get stored anomaly alerts
    Filter by severity
    """
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}
    if severity:
        query['severity'] = severity

    alerts = []
    async for alert in db.anomaly_alerts.find(query).sort('detected_at', -1).limit(50):
        alerts.append({
            'id': alert['id'],
            'type': alert['type'],
            'severity': alert['severity'],
            'title': alert['title'],
            'message': alert['message'],
            'metric': alert.get('metric'),
            'current_value': alert.get('current_value'),
            'previous_value': alert.get('previous_value'),
            'detected_at': alert['detected_at'],
            'resolved': alert.get('resolved', False)
        })

    return {
        'alerts': alerts,
        'count': len(alerts)
    }


# ============================================================================
# GM ENHANCED DASHBOARD
# ============================================================================

# 1. GET /api/gm/team-performance - Team performance metrics


