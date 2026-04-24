"""
Guest Journey Layer Router - Pre-arrival, stay management, messaging, reviews.
All endpoints under /api/guest-journey/
"""

from fastapi import APIRouter, Depends, HTTPException
from modules.pms_core.role_permission_service import require_op  # v100 DW
from modules.pms_core.role_permission_service import require_module as require_module_v100  # v100 DW
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User
from modules.guest_journey.guest_journey_service import GuestJourneyService

router = APIRouter(prefix="/api/guest-journey", tags=["guest-journey"])
journey_svc = GuestJourneyService()


class OnlineCheckinRequest(BaseModel):
    booking_id: str
    arrival_time: str | None = None
    flight_number: str | None = None
    room_preference: str | None = None
    bed_type: str | None = None
    floor_preference: str | None = None
    special_requests: str | None = None
    dietary_restrictions: str | None = None
    accessibility_needs: str | None = None
    passport_number: str | None = None
    nationality: str | None = None


class GuestRequestCreate(BaseModel):
    booking_id: str
    request_type: str
    description: str
    priority: str = "normal"
    room_id: str | None = None


class RequestStatusUpdate(BaseModel):
    request_id: str
    new_status: str
    notes: str | None = None


class AssignRequestBody(BaseModel):
    request_id: str
    assignee_id: str


class SendMessageRequest(BaseModel):
    booking_id: str
    channel: str
    message_type: str
    content: str


class SubmitReviewRequest(BaseModel):
    booking_id: str
    rating: int
    comment: str | None = None
    categories: dict | None = None


# ── PRE-ARRIVAL ──

@router.post("/online-checkin")
async def api_online_checkin(req: OnlineCheckinRequest, current_user: User = Depends(get_current_user)):
    """Submit online check-in."""
    result = await journey_svc.submit_online_checkin(current_user.tenant_id, req.booking_id, req.model_dump())
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/pre-arrival/{booking_id}")
async def api_pre_arrival_status(booking_id: str, current_user: User = Depends(get_current_user)):
    """Get pre-arrival status for a booking."""
    return await journey_svc.get_pre_arrival_status(current_user.tenant_id, booking_id)


# ── STAY MANAGEMENT ──

@router.post("/guest-request")
async def api_create_guest_request(req: GuestRequestCreate, current_user: User = Depends(get_current_user)):
    """Create a guest request."""
    result = await journey_svc.create_guest_request(
        current_user.tenant_id, req.booking_id, req.request_type, req.description, req.priority, req.room_id
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/guest-request/status")
async def api_update_request_status(req: RequestStatusUpdate, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v100("frontdesk")),  # v100 DW
):
    """Update guest request status."""
    result = await journey_svc.update_request_status(
        current_user.tenant_id, req.request_id, req.new_status, current_user.id, req.notes
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/guest-request/assign")
async def api_assign_request(req: AssignRequestBody, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v100("frontdesk")),  # v100 DW
):
    """Assign a guest request to staff."""
    result = await journey_svc.assign_request(
        current_user.tenant_id, req.request_id, req.assignee_id, current_user.id
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/guest-requests")
async def api_list_requests(
    booking_id: str | None = None,
    status: str | None = None,
    request_type: str | None = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    """List guest requests with filters."""
    return await journey_svc.get_guest_requests(current_user.tenant_id, booking_id, status, request_type, limit)


# ── MESSAGING ──

@router.post("/send-message")
async def api_send_message(req: SendMessageRequest, current_user: User = Depends(get_current_user)):
    """Send a message to a guest."""
    result = await journey_svc.send_message(
        current_user.tenant_id, req.booking_id, req.channel, req.message_type, req.content, current_user.id
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/messages/{booking_id}")
async def api_get_messages(booking_id: str, current_user: User = Depends(get_current_user)):
    """Get messages for a booking."""
    return await journey_svc.get_messages(current_user.tenant_id, booking_id)


@router.get("/message-templates")
async def api_message_templates(current_user: User = Depends(get_current_user)):
    """Get automated message templates."""
    return await journey_svc.get_auto_message_templates(current_user.tenant_id)


# ── REVIEW CAPTURE ──

@router.post("/request-review")
async def api_request_review(booking_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Request a post-checkout review."""
    result = await journey_svc.request_review(current_user.tenant_id, booking_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/submit-review")
async def api_submit_review(req: SubmitReviewRequest, current_user: User = Depends(get_current_user)):
    """Submit a guest review."""
    result = await journey_svc.submit_review(
        current_user.tenant_id, req.booking_id, req.rating, req.comment, req.categories
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/reputation-summary")
async def api_reputation_summary(current_user: User = Depends(get_current_user)):
    """Get reputation tracking summary."""
    return await journey_svc.get_reputation_summary(current_user.tenant_id)


# ── GUEST DASHBOARD ──

@router.get("/satisfaction-dashboard")
async def api_satisfaction_dashboard(current_user: User = Depends(get_current_user)):
    """Get guest satisfaction dashboard."""
    return await journey_svc.get_guest_satisfaction_dashboard(current_user.tenant_id)
