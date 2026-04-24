"""
Enterprise Live Router - WebSocket push, messaging, auto-pricing, cross-module integration.
Production-grade endpoints for enterprise hotel operations.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User
from modules.platform_scaling.cross_module_bus import cross_module_bus
from modules.platform_scaling.messaging_gateway import messaging_gateway
from modules.platform_scaling.revenue_autopricing import autopricing
from modules.platform_scaling.websocket_hub import ws_hub
from modules.pms_core.role_permission_service import require_op  # v95 DW

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/enterprise", tags=["enterprise-live"])


# ═══════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════

class SendMessageReq(BaseModel):
    channel: str  # sms, email, whatsapp
    to: str
    subject: str = ""
    body: str
    template_id: str | None = None
    template_vars: dict | None = None
    guest_id: str | None = None
    booking_id: str | None = None

class CreateTemplateReq(BaseModel):
    name: str
    channel: str
    subject: str = ""
    body: str

class UpdateConsentReq(BaseModel):
    guest_id: str
    channel: str
    opted_in: bool

class CreateRecommendationReq(BaseModel):
    room_type: str
    current_rate: float
    suggested_rate: float
    reason: str
    source: str = "manual"
    confidence: float = 0.0
    property_id: str | None = None

class ApproveRejectReq(BaseModel):
    recommendation_id: str
    note: str | None = None

class RejectReq(BaseModel):
    recommendation_id: str
    reason: str = ""

class RollbackReq(BaseModel):
    recommendation_id: str
    reason: str = ""

class ProtectedDatesReq(BaseModel):
    start_date: str
    end_date: str
    reason: str

class AutomationPolicyReq(BaseModel):
    mode: str  # full_auto, supervised, manual
    max_auto_change_pct: float = 10
    min_rate: float = 0
    max_rate: float = 99999
    property_id: str | None = None


# ═══════════════════════════════════════════════════════════
# 1. WEBSOCKET LIVE PUSH
# ═══════════════════════════════════════════════════════════

@router.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket, token: str = Query(...),
                                   last_event_ts: float | None = Query(None)):
    """
    Authenticated WebSocket endpoint for real-time push.
    Connect with: ws://host/api/enterprise/ws/live?token=JWT&last_event_ts=0
    """
    await websocket.accept()
    session = await ws_hub.connect(websocket, token, last_event_ts)
    if not session:
        await websocket.send_json({"type": "auth_error", "message": "Authentication failed"})
        await websocket.close(code=4001)
        return

    try:
        while True:
            raw = await websocket.receive_text()
            await ws_hub.handle_message(session.session_id, raw)
    except WebSocketDisconnect:
        await ws_hub.disconnect(session.session_id)
    except Exception as e:
        logger.error(f"WS error: {e}")
        await ws_hub.disconnect(session.session_id)


@router.get("/ws/stats")
async def get_ws_stats(current_user: User = Depends(get_current_user)):
    """Get WebSocket connection statistics."""
    return ws_hub.get_stats()

@router.get("/ws/live-data")
async def get_live_data(current_user: User = Depends(get_current_user)):
    """Get current live operational data (front desk queue, HK board, etc.)."""
    return await ws_hub.get_tenant_live_data(current_user.tenant_id)


# ═══════════════════════════════════════════════════════════
# 2. MESSAGING GATEWAY
# ═══════════════════════════════════════════════════════════

@router.post("/messaging/send")
async def send_message(req: SendMessageReq, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Send a message through SMS/Email/WhatsApp."""
    result = await messaging_gateway.send_message(
        tenant_id=current_user.tenant_id, channel=req.channel,
        to=req.to, subject=req.subject, body=req.body,
        template_id=req.template_id, template_vars=req.template_vars,
        user_id=current_user.id, guest_id=req.guest_id, booking_id=req.booking_id,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Send failed"))
    return result

@router.post("/messaging/templates")
async def create_template(req: CreateTemplateReq, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Create a message template."""
    return await messaging_gateway.create_template(
        current_user.tenant_id, req.name, req.channel, req.subject, req.body, current_user.id
    )

@router.get("/messaging/templates")
async def get_templates(channel: str | None = None, current_user: User = Depends(get_current_user)):
    """Get message templates."""
    return await messaging_gateway.get_templates(current_user.tenant_id, channel)

@router.get("/messaging/delivery/{delivery_id}")
async def get_delivery_status(delivery_id: str, current_user: User = Depends(get_current_user)):
    """Get message delivery status."""
    result = await messaging_gateway.get_delivery_status(current_user.tenant_id, delivery_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result

@router.get("/messaging/history")
async def get_delivery_history(guest_id: str | None = None, channel: str | None = None,
                                limit: int = 50, current_user: User = Depends(get_current_user)):
    """Get message delivery history."""
    return await messaging_gateway.get_delivery_history(
        current_user.tenant_id, guest_id, channel, limit
    )

@router.post("/messaging/consent")
async def update_consent(req: UpdateConsentReq, current_user: User = Depends(get_current_user)):
    """Update guest messaging consent."""
    return await messaging_gateway.update_consent(
        current_user.tenant_id, req.guest_id, req.channel, req.opted_in
    )

@router.get("/messaging/provider-health")
async def get_provider_health(current_user: User = Depends(get_current_user)):
    """Check messaging provider health."""
    return await messaging_gateway.get_provider_health()

@router.get("/messaging/analytics")
async def get_messaging_analytics(days: int = 7, current_user: User = Depends(get_current_user)):
    """Get messaging analytics."""
    return await messaging_gateway.get_messaging_analytics(current_user.tenant_id, days)


# ═══════════════════════════════════════════════════════════
# 3. REVENUE AUTO-PRICING WORKFLOW
# ═══════════════════════════════════════════════════════════

@router.post("/autopricing/recommendation")
async def create_recommendation(req: CreateRecommendationReq, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v98 DW
):
    """Create a pricing recommendation."""
    return await autopricing.create_recommendation(
        current_user.tenant_id, req.room_type, req.current_rate,
        req.suggested_rate, req.reason, req.source, req.confidence, req.property_id
    )

@router.post("/autopricing/approve")
async def approve_recommendation(req: ApproveRejectReq, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v95 DW
):
    """Approve and apply a pricing recommendation."""
    result = await autopricing.approve_recommendation(
        current_user.tenant_id, req.recommendation_id, current_user.id, req.note
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

@router.post("/autopricing/reject")
async def reject_recommendation(req: RejectReq, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v95 DW
):
    """Reject a pricing recommendation."""
    result = await autopricing.reject_recommendation(
        current_user.tenant_id, req.recommendation_id, current_user.id, req.reason
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

@router.post("/autopricing/rollback")
async def rollback_recommendation(req: RollbackReq, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v98 DW
):
    """Rollback an applied pricing recommendation."""
    result = await autopricing.rollback_recommendation(
        current_user.tenant_id, req.recommendation_id, current_user.id, req.reason
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

@router.get("/autopricing/pending")
async def get_pending_recommendations(current_user: User = Depends(get_current_user)):
    """Get pending pricing recommendations."""
    return await autopricing.get_pending_recommendations(current_user.tenant_id)

@router.get("/autopricing/history")
async def get_recommendation_history(limit: int = 50, current_user: User = Depends(get_current_user)):
    """Get pricing recommendation history."""
    return await autopricing.get_recommendation_history(current_user.tenant_id, limit)

@router.get("/autopricing/audit")
async def get_pricing_audit(limit: int = 50, current_user: User = Depends(get_current_user)):
    """Get pricing audit trail."""
    return await autopricing.get_pricing_audit_trail(current_user.tenant_id, limit)

@router.get("/autopricing/channel-push")
async def get_channel_push_status(rec_id: str | None = None,
                                   current_user: User = Depends(get_current_user)):
    """Get rate push status to channels."""
    return await autopricing.get_channel_push_status(current_user.tenant_id, rec_id)

@router.post("/autopricing/protected-dates")
async def add_protected_dates(req: ProtectedDatesReq, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v98 DW
):
    """Add protected/blackout dates."""
    return await autopricing.add_protected_dates(
        current_user.tenant_id, req.start_date, req.end_date, req.reason, current_user.id
    )

@router.get("/autopricing/protected-dates")
async def get_protected_dates(current_user: User = Depends(get_current_user)):
    """Get protected date rules."""
    return await autopricing.get_protected_dates(current_user.tenant_id)

@router.post("/autopricing/policy")
async def set_automation_policy(req: AutomationPolicyReq, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v98 DW
):
    """Set auto-pricing automation policy."""
    return await autopricing.set_automation_policy(
        current_user.tenant_id, req.mode, req.max_auto_change_pct,
        req.min_rate, req.max_rate, req.property_id, current_user.id
    )

@router.get("/autopricing/dashboard")
async def get_autopricing_dashboard(current_user: User = Depends(get_current_user)):
    """Get auto-pricing dashboard."""
    return await autopricing.get_autopricing_dashboard(current_user.tenant_id)


# ═══════════════════════════════════════════════════════════
# 4. CROSS-MODULE DEEP INTEGRATION
# ═══════════════════════════════════════════════════════════

@router.post("/integration/run-all")
async def run_all_integrations(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v95 DW
):
    """Execute all cross-module integration flows."""
    return await cross_module_bus.run_all_integrations(current_user.tenant_id)

@router.get("/integration/cancellation-overbooking")
async def get_cancellation_overbooking(current_user: User = Depends(get_current_user)):
    """Get cancellation → overbooking strategy signals."""
    return await cross_module_bus.cancellation_to_overbooking(current_user.tenant_id)

@router.get("/integration/booking-confidence")
async def get_booking_confidence(current_user: User = Depends(get_current_user)):
    """Get booking probability → revenue confidence signals."""
    return await cross_module_bus.booking_prob_to_revenue_confidence(current_user.tenant_id)

@router.get("/integration/compset-adr")
async def get_compset_adr(current_user: User = Depends(get_current_user)):
    """Get comp set → ADR adjustment signals."""
    return await cross_module_bus.compset_gap_to_adr(current_user.tenant_id)

@router.get("/integration/guest-hk-priority")
async def get_guest_hk_priority(current_user: User = Depends(get_current_user)):
    """Get guest request → HK priority signals."""
    return await cross_module_bus.guest_requests_to_hk_priority(current_user.tenant_id)

@router.get("/integration/vip-readiness")
async def get_vip_readiness(current_user: User = Depends(get_current_user)):
    """Get VIP → room readiness signals."""
    return await cross_module_bus.vip_to_room_readiness(current_user.tenant_id)

@router.get("/integration/audit-escalation")
async def get_audit_escalation(current_user: User = Depends(get_current_user)):
    """Get audit exception → escalation signals."""
    return await cross_module_bus.audit_exception_to_escalation(current_user.tenant_id)

@router.get("/integration/messaging-fallback")
async def get_messaging_fallback(current_user: User = Depends(get_current_user)):
    """Get failed messaging → fallback signals."""
    return await cross_module_bus.failed_messaging_to_fallback(current_user.tenant_id)

@router.get("/integration/sync-alerts")
async def get_sync_alerts(current_user: User = Depends(get_current_user)):
    """Get sync failure → operations alert signals."""
    return await cross_module_bus.sync_failure_to_ops_alert(current_user.tenant_id)

@router.get("/integration/autopricing-metrics")
async def get_autopricing_metrics(current_user: User = Depends(get_current_user)):
    """Get auto-pricing → dashboard metrics."""
    return await cross_module_bus.autopricing_to_dashboard_metrics(current_user.tenant_id)

@router.get("/integration/risk-badges")
async def get_risk_badges(current_user: User = Depends(get_current_user)):
    """Get reservation risk → front desk warning badges."""
    return await cross_module_bus.reservation_risk_to_frontdesk_badges(current_user.tenant_id)

@router.get("/integration/frontdesk-warnings")
async def get_frontdesk_warnings(current_user: User = Depends(get_current_user)):
    """Get current front desk warning badges."""
    badges = await db.frontdesk_warning_badges.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).to_list(100)
    return {"count": len(badges), "badges": badges}


# Import db for direct queries
from core.database import db
