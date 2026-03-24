"""
Guest Journey Layer Router - Pre-arrival, stay management, messaging, reviews.
All endpoints under /api/guest-journey/
"""
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User
from modules.guest_journey.guest_journey_service import GuestJourneyService

router = APIRouter(prefix="/api/guest-journey", tags=["guest-journey"])
journey_svc = GuestJourneyService()


class OnlineCheckinRequest(BaseModel):
    booking_id: str
    arrival_time: Optional[str] = None
    flight_number: Optional[str] = None
    room_preference: Optional[str] = None
    bed_type: Optional[str] = None
    floor_preference: Optional[str] = None
    special_requests: Optional[str] = None
    dietary_restrictions: Optional[str] = None
    accessibility_needs: Optional[str] = None
    passport_number: Optional[str] = None
    nationality: Optional[str] = None


class GuestRequestCreate(BaseModel):
    booking_id: str
    request_type: str
    description: str
    priority: str = "normal"
    room_id: Optional[str] = None


class RequestStatusUpdate(BaseModel):
    request_id: str
    new_status: str
    notes: Optional[str] = None


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
    comment: Optional[str] = None
    categories: Optional[Dict] = None


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
async def api_update_request_status(req: RequestStatusUpdate, current_user: User = Depends(get_current_user)):
    """Update guest request status."""
    result = await journey_svc.update_request_status(
        current_user.tenant_id, req.request_id, req.new_status, current_user.id, req.notes
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/guest-request/assign")
async def api_assign_request(req: AssignRequestBody, current_user: User = Depends(get_current_user)):
    """Assign a guest request to staff."""
    result = await journey_svc.assign_request(
        current_user.tenant_id, req.request_id, req.assignee_id, current_user.id
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/guest-requests")
async def api_list_requests(
    booking_id: Optional[str] = None,
    status: Optional[str] = None,
    request_type: Optional[str] = None,
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
async def api_request_review(booking_id: str, current_user: User = Depends(get_current_user)):
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
