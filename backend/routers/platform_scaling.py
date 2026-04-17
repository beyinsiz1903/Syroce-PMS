"""
Platform Scaling Router - Unified API for all enterprise scaling modules:
- Real-Time Event Architecture
- Multi-Property Platform
- Revenue ML
- Competitive Set Analysis
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.cache import cached
from core.security import get_current_user
from models.schemas import User
from modules.platform_scaling.competitive_analysis import (
    ADRAdjustmentEngine,
    CompetitiveSetDashboard,
    CompetitorPriceTracker,
    MarketPositioning,
)
from modules.platform_scaling.event_architecture import EnhancedEventBus
from modules.platform_scaling.multi_property_platform import (
    CentralReservationService,
    CentralRevenueManagement,
    GlobalAlertSystem,
)
from modules.platform_scaling.revenue_ml import (
    BookingProbabilityModel,
    CancellationPredictionModel,
    DemandForecastingModel,
    RateElasticityModel,
    RevenueMLDashboard,
)

router = APIRouter(prefix="/api/platform", tags=["platform-scaling"])

# Service instances
event_bus = EnhancedEventBus()
crs = CentralReservationService()
crm = CentralRevenueManagement()
alerts = GlobalAlertSystem()
demand_model = DemandForecastingModel()
elasticity_model = RateElasticityModel()
booking_prob = BookingProbabilityModel()
cancellation_model = CancellationPredictionModel()
ml_dashboard = RevenueMLDashboard()
comp_tracker = CompetitorPriceTracker()
market_pos = MarketPositioning()
adr_engine = ADRAdjustmentEngine()
comp_dashboard = CompetitiveSetDashboard()


# ═══════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════

class PublishEventReq(BaseModel):
    event_type: str
    payload: dict
    property_id: str | None = None
    priority: str | None = None

class MarkNotificationsReadReq(BaseModel):
    notification_ids: list[str]

class AcknowledgeEventReq(BaseModel):
    event_id: str
    note: str | None = None

class CrossPropertySearchReq(BaseModel):
    check_in: str
    check_out: str
    room_type: str | None = None
    guests: int = 2

class TransferReservationReq(BaseModel):
    booking_id: str
    target_property_id: str
    reason: str | None = None

class GlobalRateAdjustReq(BaseModel):
    adjustment_pct: float
    room_type: str | None = None

class BookingProbReq(BaseModel):
    check_in: str
    check_out: str
    source: str = "direct"
    room_type: str = "Standard"
    rate: float = 0

class AddCompetitorReq(BaseModel):
    name: str
    star_rating: int = 4
    room_types: list[str] | None = None
    location: str | None = None

class RecordCompRateReq(BaseModel):
    competitor_id: str
    room_type: str
    rate: float
    date: str
    source: str = "manual"

class BulkCompRatesReq(BaseModel):
    rates: list[dict]

class ApplyADRReq(BaseModel):
    room_type: str
    new_rate: float


# ═══════════════════════════════════════════════════════════
# 1. REAL-TIME EVENT ARCHITECTURE
# ═══════════════════════════════════════════════════════════

@router.post("/events/publish")
async def api_publish_event(req: PublishEventReq, current_user: User = Depends(get_current_user)):
    """Publish a platform-level event."""
    result = await event_bus.publish_event(
        current_user.tenant_id, req.event_type, req.payload,
        current_user.id, req.property_id, req.priority
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

@router.get("/events/stream")
async def api_event_stream(
    limit: int = 100, event_type: str | None = None,
    priority: str | None = None, property_id: str | None = None,
    since: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Get platform event stream."""
    return await event_bus.get_event_stream(
        current_user.tenant_id, limit, event_type, priority, property_id, since
    )

@router.get("/events/notifications")
async def api_notifications(
    role: str | None = None, unread_only: bool = False, limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    """Get notifications for a role."""
    return await event_bus.get_notifications(
        current_user.tenant_id, role, unread_only, limit
    )

@router.post("/events/notifications/read")
async def api_mark_read(req: MarkNotificationsReadReq, current_user: User = Depends(get_current_user)):
    """Mark notifications as read."""
    return await event_bus.mark_notifications_read(current_user.tenant_id, req.notification_ids)

@router.post("/events/acknowledge")
async def api_ack_event(req: AcknowledgeEventReq, current_user: User = Depends(get_current_user)):
    """Acknowledge a platform event."""
    result = await event_bus.acknowledge_event(
        current_user.tenant_id, req.event_id, current_user.id, req.note
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

@router.get("/events/analytics")
async def api_event_analytics(hours: int = 24, current_user: User = Depends(get_current_user)):
    """Get event analytics."""
    return await event_bus.get_event_analytics(current_user.tenant_id, hours)

@router.get("/events/escalation-queue")
async def api_escalation_queue(current_user: User = Depends(get_current_user)):
    """Get events requiring escalation."""
    return await event_bus.get_escalation_queue(current_user.tenant_id)

@router.get("/events/gateway-stats")
async def api_gateway_stats(current_user: User = Depends(get_current_user)):
    """Get WebSocket gateway statistics."""
    return event_bus.gateway.get_gateway_stats()


# ═══════════════════════════════════════════════════════════
# 2. MULTI-PROPERTY PLATFORM
# ═══════════════════════════════════════════════════════════

@router.get("/multi-property/portfolio")
async def api_portfolio_overview(current_user: User = Depends(get_current_user)):
    """Get portfolio-wide overview."""
    return await crs.get_portfolio_overview(current_user.tenant_id)

@router.post("/multi-property/search-availability")
async def api_cross_property_search(req: CrossPropertySearchReq, current_user: User = Depends(get_current_user)):
    """Search availability across all properties."""
    return await crs.search_availability_cross_property(
        current_user.tenant_id, req.check_in, req.check_out, req.room_type, req.guests
    )

@router.post("/multi-property/transfer-reservation")
async def api_transfer_reservation(req: TransferReservationReq, current_user: User = Depends(get_current_user)):
    """Transfer reservation to another property."""
    result = await crs.transfer_reservation(
        current_user.tenant_id, req.booking_id, req.target_property_id,
        current_user.id, req.reason
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

@router.get("/multi-property/revenue")
async def api_portfolio_revenue(days: int = 30, current_user: User = Depends(get_current_user)):
    """Get portfolio-wide revenue metrics."""
    return await crm.get_portfolio_revenue(current_user.tenant_id, days)

@router.post("/multi-property/global-rate-adjust")
async def api_global_rate_adjust(req: GlobalRateAdjustReq, current_user: User = Depends(get_current_user)):
    """Apply global rate adjustment across all properties."""
    return await crm.apply_global_rate_adjustment(
        current_user.tenant_id, req.adjustment_pct, req.room_type, current_user.id
    )

@router.get("/multi-property/alerts")
async def api_global_alerts(current_user: User = Depends(get_current_user)):
    """Get global alerts across all properties."""
    return await alerts.get_global_alerts(current_user.tenant_id)

@router.get("/multi-property/dashboard")
async def api_multi_property_dashboard(current_user: User = Depends(get_current_user)):
    """Get comprehensive multi-property dashboard."""
    return await alerts.get_multi_property_dashboard(current_user.tenant_id)


# ═══════════════════════════════════════════════════════════
# 3. REVENUE ML
# ═══════════════════════════════════════════════════════════

@router.get("/ml/demand-forecast")
async def api_demand_forecast(days: int = 30, current_user: User = Depends(get_current_user)):
    """Get ML demand forecast."""
    if days > 90:
        raise HTTPException(status_code=400, detail="Max 90 days")
    return await demand_model.forecast_demand(current_user.tenant_id, days)

@router.get("/ml/rate-elasticity")
async def api_rate_elasticity(room_type: str | None = None, current_user: User = Depends(get_current_user)):
    """Analyze rate elasticity."""
    return await elasticity_model.analyze_elasticity(current_user.tenant_id, room_type)

@router.get("/ml/optimal-prices")
async def api_optimal_prices(current_user: User = Depends(get_current_user)):
    """Get optimal price points per room type."""
    return await elasticity_model.get_optimal_price_points(current_user.tenant_id)

@router.post("/ml/booking-probability")
async def api_booking_probability(req: BookingProbReq, current_user: User = Depends(get_current_user)):
    """Predict booking conversion probability."""
    return await booking_prob.predict_conversion(
        current_user.tenant_id, req.check_in, req.check_out,
        req.source, req.room_type, req.rate
    )

@router.get("/ml/conversion-rates")
async def api_conversion_rates(current_user: User = Depends(get_current_user)):
    """Get portfolio conversion rates by source."""
    return await booking_prob.get_portfolio_conversion_rates(current_user.tenant_id)

@router.get("/ml/cancellation-risk/{booking_id}")
async def api_cancellation_risk(booking_id: str, current_user: User = Depends(get_current_user)):
    """Predict cancellation risk for a booking."""
    result = await cancellation_model.predict_cancellation_risk(current_user.tenant_id, booking_id)
    if not result.get("booking_id") and result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result

@router.get("/ml/at-risk-bookings")
async def api_at_risk_bookings(min_risk: float = 0.3, current_user: User = Depends(get_current_user)):
    """Get bookings with high cancellation risk."""
    return await cancellation_model.get_at_risk_bookings(current_user.tenant_id, min_risk)

@router.get("/ml/dashboard")
@cached(ttl=180, key_prefix="ml_dashboard")
async def api_ml_dashboard(current_user: User = Depends(get_current_user)):
    """Get comprehensive Revenue ML dashboard."""
    return await ml_dashboard.get_ml_dashboard(current_user.tenant_id)


# ═══════════════════════════════════════════════════════════
# 4. COMPETITIVE SET ANALYSIS
# ═══════════════════════════════════════════════════════════

@router.post("/competitive/add-competitor")
async def api_add_competitor(req: AddCompetitorReq, current_user: User = Depends(get_current_user)):
    """Add a competitor to the comp set."""
    return await comp_tracker.add_competitor(
        current_user.tenant_id, req.name, req.star_rating, req.room_types, req.location
    )

@router.get("/competitive/competitors")
async def api_get_competitors(current_user: User = Depends(get_current_user)):
    """Get all competitors in the comp set."""
    return await comp_tracker.get_competitors(current_user.tenant_id)

@router.post("/competitive/record-rate")
async def api_record_rate(req: RecordCompRateReq, current_user: User = Depends(get_current_user)):
    """Record a competitor rate."""
    return await comp_tracker.record_competitor_rate(
        current_user.tenant_id, req.competitor_id, req.room_type, req.rate, req.date, req.source
    )

@router.post("/competitive/bulk-rates")
async def api_bulk_rates(req: BulkCompRatesReq, current_user: User = Depends(get_current_user)):
    """Bulk import competitor rates."""
    return await comp_tracker.bulk_record_rates(current_user.tenant_id, req.rates)

@router.get("/competitive/rates")
async def api_comp_rates(
    target_date: str | None = None, competitor_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Get competitor rates."""
    return await comp_tracker.get_competitor_rates(current_user.tenant_id, target_date, competitor_id)

@router.get("/competitive/market-position")
async def api_market_position(room_type: str = "Standard", current_user: User = Depends(get_current_user)):
    """Get market position analysis."""
    return await market_pos.get_market_position(current_user.tenant_id, room_type)

@router.get("/competitive/rate-parity")
async def api_rate_parity(current_user: User = Depends(get_current_user)):
    """Check rate parity across comp set."""
    return await market_pos.get_rate_parity_check(current_user.tenant_id)

@router.get("/competitive/adr-suggestions")
async def api_adr_suggestions(current_user: User = Depends(get_current_user)):
    """Get ADR adjustment suggestions."""
    return await adr_engine.get_adr_suggestions(current_user.tenant_id)

@router.post("/competitive/apply-adr")
async def api_apply_adr(req: ApplyADRReq, current_user: User = Depends(get_current_user)):
    """Apply ADR adjustment."""
    return await adr_engine.apply_suggestion(
        current_user.tenant_id, req.room_type, req.new_rate, current_user.id
    )

@router.get("/competitive/dashboard")
async def api_comp_dashboard(current_user: User = Depends(get_current_user)):
    """Get comprehensive competitive analysis dashboard."""
    return await comp_dashboard.get_dashboard(current_user.tenant_id)
