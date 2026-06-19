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
from pydantic import BaseModel, ConfigDict, Field
from pymongo import UpdateOne

from core.database import db
from core.outbox_service import RATE_UPDATED, enqueue_outbox_event
from core.security import (
    get_current_user,
)
from models.enums import CancellationPolicyType, ChannelType, MarketSegment, RateType
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v99 DW

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


# ─── Endpoints (split: ai_pricing) ───


@router.post("/rms/ai-pricing/train-model")
async def train_demand_forecast_model(
    historical_days: int = 365,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    """
    Train ML demand forecast model
    - Uses historical booking data
    - Considers seasonality, events, day of week
    - Basic ML: Linear Regression or XGBoost
    """
    # In production: Use scikit-learn, XGBoost, or TensorFlow
    # Collect historical data
    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=historical_days)

    # Get historical bookings
    bookings = []
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': start_dt.isoformat(),
            '$lte': end_dt.isoformat()
        }
    }):
        bookings.append(booking)

    # Fail-closed: real ML demand-forecast training runs in the dedicated ML
    # service (ml_service / ml_trainers, dispatched to the 'ml' Celery queue),
    # NOT inline here. We must never fabricate accuracy/MAE for a model we did
    # not actually train. Report the real available training-sample count and
    # direct the caller to the real pipeline.
    return {
        'success': False,
        'model_trained': False,
        'data_available': False,
        'samples_available': len(bookings),
        'historical_days': historical_days,
        'message': (
            'Talep tahmin modeli bu uctan egitilmiyor. Gercek ML egitimi adanmis '
            'ML servisi (ml_service) uzerinden calisir; bu uctan sahte dogruluk/MAE '
            'uretilmez.'
        ),
    }






@router.post("/rms/ai-pricing/competitor-scrape")
async def scrape_competitor_rates(
    date: str,
    competitors: list[str],
    room_types: list[str],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    """
    Scrape competitor rates
    - Google Hotels API
    - OTA APIs (Booking.com, Expedia)
    - Real-time pricing intelligence
    """
    # In production: Integrate with:
    # - Google Hotels API
    # - Booking.com Connectivity API
    # - Expedia Partner API
    # - Web scraping (Selenium/Playwright)

    # Fail-closed: no competitor-rate data source is configured (Google Hotels /
    # Booking.com / Expedia connectivity APIs are not wired). We must NOT
    # fabricate competitor rates or persist invented numbers (the previous
    # implementation wrote `100 + len(name)*5` as if scraped). Return unavailable.
    return {
        'success': False,
        'data_available': False,
        'date': date,
        'rates_scraped': 0,
        'competitor_rates': [],
        'message': (
            'Rakip fiyat veri kaynagi (Google Hotels / Booking.com / Expedia API) '
            'yapilandirilmamis. Sahte rakip fiyati uretilmez.'
        ),
    }






@router.post("/rms/ai-pricing/calculate-elasticity")
async def calculate_price_elasticity(
    room_type: str,
    analysis_days: int = 90,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    """
    Price elasticity analysis
    - How demand changes with price changes
    - Optimal pricing point
    - Revenue optimization
    """
    # Get historical bookings with different prices
    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=analysis_days)

    # Scope to the requested room_type. Bookings may store `room_type` directly
    # OR only reference a room via `room_id` (room_type resolved by joining the
    # rooms collection), so we match EITHER. Without this scope the elasticity
    # coefficient would be computed across ALL room types yet returned labelled
    # as the requested one (a misleading calculation).
    room_ids: list[str] = []
    async for _room in db.rooms.find(
        {'tenant_id': current_user.tenant_id, 'room_type': room_type},
        {'_id': 0, 'id': 1},
    ):
        if _room.get('id'):
            room_ids.append(_room['id'])

    room_match: list[dict] = [{'room_type': room_type}]
    if room_ids:
        room_match.append({'room_id': {'$in': room_ids}})

    # Collect price-demand pairs
    bookings = []
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': start_dt.isoformat(),
            '$lte': end_dt.isoformat()
        },
        '$or': room_match,
    }):
        bookings.append(booking)

    # Real price elasticity from observed booking data. We build a price ->
    # demand(count) curve from real per-night prices and fit a constant-
    # elasticity model ln(Q) = a + e*ln(P) by ordinary least squares; the slope
    # `e` is the elasticity. This is an empirical estimate (cross-sectional, so
    # other factors are not controlled) but it is derived entirely from real
    # data. When there is not enough price variation we FAIL CLOSED rather than
    # invent a coefficient.
    import math

    insufficient = {
        'room_type': room_type,
        'analysis_period_days': analysis_days,
        'bookings_analyzed': len(bookings),
        'data_available': False,
        'message': (
            'Fiyat esnekligi icin yeterli fiyat-talep verisi yok (farkli fiyat '
            'seviyelerinde yeterli rezervasyon gerekir).'
        ),
    }

    prices: list[float] = []
    for b in bookings:
        amt = b.get('total_amount') or 0
        if amt <= 0:
            continue
        try:
            _ci = datetime.fromisoformat(str(b.get('check_in')).replace('Z', '+00:00'))
            _co = datetime.fromisoformat(str(b.get('check_out')).replace('Z', '+00:00'))
            _nights = max(1, (_co.date() - _ci.date()).days)
        except Exception:
            _nights = 1
        prices.append(amt / _nights)

    if len(prices) < 20:
        return insufficient

    lo, hi = min(prices), max(prices)
    if hi <= lo:
        return insufficient

    n_buckets = 6
    width = (hi - lo) / n_buckets
    counts = [0] * n_buckets
    sums = [0.0] * n_buckets
    for p in prices:
        idx = min(n_buckets - 1, int((p - lo) / width))
        counts[idx] += 1
        sums[idx] += p
    pts = [(sums[i] / counts[i], counts[i]) for i in range(n_buckets) if counts[i] > 0]
    if len(pts) < 3:
        return insufficient

    xs = [math.log(p) for p, _q in pts]
    ys = [math.log(q) for _p, q in pts]
    m = len(xs)
    mean_x = sum(xs) / m
    mean_y = sum(ys) / m
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return insufficient
    slope = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(m)) / sxx
    intercept = mean_y - slope * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((ys[i] - (intercept + slope * xs[i])) ** 2 for i in range(m))
    r2 = (1 - ss_res / ss_tot) if ss_tot > 0 else 0.0

    avg_price = sum(prices) / len(prices)

    # Optimal price within the OBSERVED band that maximises modelled revenue
    # R(P) = exp(intercept) * P^(slope+1). We never extrapolate beyond observed.
    best_p, best_rev = avg_price, -1.0
    steps = 50
    for k in range(steps + 1):
        p = lo + (hi - lo) * k / steps
        if p <= 0:
            continue
        rev = math.exp(intercept) * (p ** (slope + 1))
        if rev > best_rev:
            best_rev, best_p = rev, p
    rev_at_avg = math.exp(intercept) * (avg_price ** (slope + 1)) if avg_price > 0 else 0
    revenue_lift_pct = round(((best_rev - rev_at_avg) / rev_at_avg) * 100, 1) if rev_at_avg > 0 else 0.0

    if slope < -1:
        interpretation = 'Esnek talep: fiyat artisi toplam geliri dusurur (talep fiyata duyarli).'
        sensitivity = 'High'
        recommendations = [
            'Esnek talep: agresif fiyat artislarindan kacinin, doluluk odakli fiyatlayin.',
            'Hafta ici / hafta sonu ayrimi ile dinamik fiyatlama uygulayin.',
        ]
    elif slope < 0:
        interpretation = 'Inelastik talep: olcap fiyat artislari toplam geliri artirabilir.'
        sensitivity = 'Low'
        recommendations = [
            'Inelastik talep: yuksek talepli tarihlerde fiyati kademeli artirin.',
            'Hafta ici / hafta sonu ayrimi ile dinamik fiyatlama uygulayin.',
        ]
    else:
        interpretation = 'Pozitif egim: karistirici faktorler/veri gurultusu olabilir, dikkatli yorumlayin.'
        sensitivity = 'Unknown'
        recommendations = [
            'Daha guvenilir esneklik icin daha genis fiyat-talep verisi toplayin.',
        ]

    return {
        'room_type': room_type,
        'analysis_period_days': analysis_days,
        'avg_historical_price': round(avg_price, 2),
        'bookings_analyzed': len(bookings),
        'price_points_used': len(pts),
        'data_available': True,
        'elasticity_coefficient': round(slope, 2),
        'fit_r2': round(r2, 2),
        'interpretation': interpretation,
        'optimal_price_point': round(best_p, 2),
        'expected_revenue_lift': f"{revenue_lift_pct}%",
        'price_sensitivity': sensitivity,
        'recommendations': recommendations,
    }






@router.post("/rms/ai-pricing/auto-publish-rates")
async def auto_publish_rates_based_on_forecast(
    start_date: str,
    end_date: str,
    strategy: str = "revenue_optimization",  # occupancy_maximization, revenue_optimization, balanced
    dry_run: bool = True,  # fail-closed: default suppresses ALL writes + outbox
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    """
    Auto-publish rates based on AI forecast
    - Revenue optimization strategy
    - Occupancy maximization strategy
    - Balanced approach

    Server-side dry_run kill-switch (fail-closed; default ``dry_run=True``):
      * ``dry_run=True``  → compute recommendations ONLY. No persistent writes,
        no outbox events. Response reports ``dry_run=True``,
        ``rates_persisted=0``, ``outbox_events_emitted=0`` and every entry in
        ``published_rates`` carries ``published=False``.
      * ``dry_run=False`` → persist each recommended rate to
        ``ai_pricing_publications`` (tenant-scoped upsert) AND enqueue one
        ``RATE_UPDATED`` outbox event per date for downstream channel delivery.

    The pricing algorithm itself is identical in both modes; the flag only
    gates the side effects (persistence + outbox), so the stress suite can
    hard-assert "dry_run ⇒ zero writes ⇒ external_calls=[]".
    """
    # Get demand forecast
    forecasts = []
    async for forecast in db.demand_forecasts.find({
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': start_date, '$lte': end_date}
    }).sort('date', 1):
        forecasts.append(forecast)

    # Fail-closed: never fabricate demand forecasts. If the tenant has no real
    # forecast rows for this range, refuse rather than invent occupancy numbers
    # that would drive real (channel-published) rate changes.
    if not forecasts:
        return {
            'success': False,
            'data_available': False,
            'dry_run': dry_run,
            'start_date': start_date,
            'end_date': end_date,
            'strategy': strategy,
            'rates_published': 0,
            'rates_persisted': 0,
            'outbox_events_emitted': 0,
            'published_rates': [],
            'avg_rate': 0,
            'message': (
                'Bu tarih araliginda gercek talep tahmini bulunmuyor. Sahte tahmin '
                'uretilmez; once talep tahmini olusturun.'
            ),
        }

    # Base nightly rate is derived from the tenant's real recent per-night prices
    # (last 90 days, non-cancelled, paid), NOT a hardcoded constant. Fail closed
    # if we cannot derive a real base rate.
    base_start = (datetime.now(UTC) - timedelta(days=90)).isoformat()
    night_prices: list[float] = []
    async for _b in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': base_start},
        'status': {'$nin': ['cancelled', 'no_show']},
        'total_amount': {'$gt': 0},
    }):
        _amt = _b.get('total_amount') or 0
        try:
            _ci = datetime.fromisoformat(str(_b.get('check_in')).replace('Z', '+00:00'))
            _co = datetime.fromisoformat(str(_b.get('check_out')).replace('Z', '+00:00'))
            _nights = max(1, (_co.date() - _ci.date()).days)
        except Exception:
            _nights = 1
        night_prices.append(_amt / _nights)

    if not night_prices:
        return {
            'success': False,
            'data_available': False,
            'dry_run': dry_run,
            'start_date': start_date,
            'end_date': end_date,
            'strategy': strategy,
            'rates_published': 0,
            'rates_persisted': 0,
            'outbox_events_emitted': 0,
            'published_rates': [],
            'avg_rate': 0,
            'message': (
                'Gercek taban fiyat (son 90 gun) hesaplanamadi; yeterli rezervasyon '
                'verisi yok. Fiyat yayinlanmadi.'
            ),
        }

    # Fail-closed: every forecast row MUST carry a real numeric occupancy. We
    # never default a missing/invalid occupancy to a synthetic value (the old
    # code silently used 0.7), because fabricated demand would drive real
    # published rates. `demand_forecasts` stores occupancy as a PERCENTAGE
    # (0-100); we normalise to a fraction here (and tolerate legacy fraction
    # rows) so the pricing multiplier math is correct. Any row with a missing or
    # out-of-range occupancy aborts the whole publish rather than guessing.
    normalized: list[tuple] = []
    for _f in forecasts:
        _raw_occ = _f.get('forecasted_occupancy')
        if isinstance(_raw_occ, bool) or not isinstance(_raw_occ, (int, float)):
            return {
                'success': False,
                'data_available': False,
                'dry_run': dry_run,
                'start_date': start_date,
                'end_date': end_date,
                'strategy': strategy,
                'rates_published': 0,
                'rates_persisted': 0,
                'outbox_events_emitted': 0,
                'published_rates': [],
                'avg_rate': 0,
                'message': (
                    'Talep tahmini kayitlarinda gecerli sayisal doluluk degeri '
                    'eksik. Sahte doluluk varsayilmaz; fiyat yayinlanmadi.'
                ),
            }
        _occ = float(_raw_occ)
        if _occ > 1:  # stored as percentage (0-100) -> fraction
            _occ = _occ / 100.0
        if not (0.0 <= _occ <= 1.0):
            return {
                'success': False,
                'data_available': False,
                'dry_run': dry_run,
                'start_date': start_date,
                'end_date': end_date,
                'strategy': strategy,
                'rates_published': 0,
                'rates_persisted': 0,
                'outbox_events_emitted': 0,
                'published_rates': [],
                'avg_rate': 0,
                'message': (
                    'Talep tahmini doluluk degeri gecerli aralik disinda. Fiyat '
                    'yayinlanmadi.'
                ),
            }
        normalized.append((_f.get('date'), _occ))

    # Calculate recommended rates
    published_rates = []
    base_rate = round(sum(night_prices) / len(night_prices), 2)

    for forecast_date, occupancy in normalized:
        if strategy == "revenue_optimization":
            # High demand = high price
            multiplier = 1 + (occupancy - 0.5)  # 50% occupancy = base rate
        elif strategy == "occupancy_maximization":
            # Low demand = lower price to fill rooms
            multiplier = 1 - (occupancy - 0.5) * 0.5
        else:  # balanced
            multiplier = 1 + (occupancy - 0.5) * 0.5

        recommended_rate = round(base_rate * multiplier, 2)

        published_rates.append({
            'date': forecast_date,
            'forecasted_occupancy': round(occupancy * 100, 1),
            'recommended_rate': recommended_rate,
            'published': (not dry_run),
            'strategy': strategy
        })

    # Side effects (persistence + outbox) are gated behind the dry_run flag.
    # When dry_run=True (default) NOTHING below runs → no writes, no outbox
    # events, no downstream channel delivery.
    rates_persisted = 0
    outbox_events_emitted = 0
    if not dry_run and published_rates:
        now_iso = datetime.now(UTC).isoformat()
        ops = [
            UpdateOne(
                {
                    'tenant_id': current_user.tenant_id,
                    'date': r['date'],
                    'strategy': strategy,
                },
                {'$set': {
                    'tenant_id': current_user.tenant_id,
                    'date': r['date'],
                    'strategy': strategy,
                    'recommended_rate': r['recommended_rate'],
                    'forecasted_occupancy': r['forecasted_occupancy'],
                    'published_at': now_iso,
                    'published_by': current_user.email,
                }},
                upsert=True,
            )
            for r in published_rates
        ]
        await db.ai_pricing_publications.bulk_write(ops, ordered=False)
        rates_persisted = len(ops)

        for r in published_rates:
            await enqueue_outbox_event(
                db,
                tenant_id=current_user.tenant_id,
                event_type=RATE_UPDATED,
                entity_type='ai_pricing_publication',
                entity_id=f"{current_user.tenant_id}:{r['date']}:{strategy}",
                payload={
                    'date': r['date'],
                    'recommended_rate': r['recommended_rate'],
                    'strategy': strategy,
                    'source': 'ai_auto_publish',
                },
            )
            outbox_events_emitted += 1

    return {
        'success': True,
        'dry_run': dry_run,
        'start_date': start_date,
        'end_date': end_date,
        'strategy': strategy,
        'rates_published': len(published_rates),
        'rates_persisted': rates_persisted,
        'outbox_events_emitted': outbox_events_emitted,
        'published_rates': published_rates,
        'avg_rate': (
            round(sum(r['recommended_rate'] for r in published_rates) / len(published_rates), 2)
            if published_rates else 0
        ),
        'note': (
            'Dry-run: recommendations computed only; no rates persisted and no '
            'channel/outbox events emitted.'
            if dry_run else
            'Rates persisted to ai_pricing_publications and queued for channel '
            'delivery via outbox.'
        ),
    }


# ============= RBAC 2.0 (ENHANCED ACCESS CONTROL) =============



