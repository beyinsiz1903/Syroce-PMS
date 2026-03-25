"""Reservation import, review queue, batch, ACK, audit-trail endpoints."""
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User

from ...application.reservation_import_service import ReservationImportService

logger = logging.getLogger("channel_manager.routers.reservation")

router = APIRouter(tags=["CM Reservations"])


class TriggerImportRequest(BaseModel):
    connector_id: str
    date_start: str | None = None
    date_end: str | None = None


class ApproveReviewRequest(BaseModel):
    reservation_id: str
    room_type_override: str | None = None


class ReprocessReviewRequest(BaseModel):
    room_type_override: str | None = None


# ─── Reservation Import ──────────────────────────────────────────

@router.post("/reservations/pull")
async def trigger_reservation_pull(
    req: TriggerImportRequest,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    result = await svc.pull_and_import(
        tenant_id=current_user.tenant_id,
        connector_id=req.connector_id,
        date_start=req.date_start,
        date_end=req.date_end,
        triggered_by="user",
    )
    return result


@router.get("/reservations/imported")
async def list_imported_reservations(
    connector_id: str | None = None,
    status: str | None = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    reservations = await svc.get_imported_reservations(
        current_user.tenant_id, connector_id, status, limit,
    )
    return {"reservations": reservations, "count": len(reservations)}


@router.get("/reservations/imported/{reservation_id}")
async def get_imported_reservation_detail(
    reservation_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    detail = await svc.get_imported_reservation_detail(current_user.tenant_id, reservation_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Imported reservation not found")
    return detail


@router.get("/reservations/review-queue")
async def get_review_queue(
    connector_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    queue = await svc.get_review_queue(current_user.tenant_id, connector_id)
    return {"queue": queue, "count": len(queue)}


@router.post("/reservations/review-queue/{reservation_id}/reprocess")
async def reprocess_review_reservation(
    reservation_id: str,
    req: ReprocessReviewRequest = None,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    try:
        override = req.room_type_override if req else None
        result = await svc.reprocess_review(
            current_user.tenant_id, reservation_id,
            current_user.id, override,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reservations/review-queue/{reservation_id}/dismiss")
async def dismiss_review_reservation(
    reservation_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    try:
        result = await svc.dismiss_review(
            current_user.tenant_id, reservation_id, current_user.id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reservations/approve")
async def approve_review(
    req: ApproveReviewRequest,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    result = await svc.approve_review(
        current_user.tenant_id, req.reservation_id,
        current_user.id, req.room_type_override,
    )
    return result


@router.get("/reservations/batches")
async def list_import_batches(
    connector_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    batches = await svc.get_import_batches(current_user.tenant_id, connector_id)
    return {"batches": batches, "count": len(batches)}


@router.get("/reservations/batches/{batch_id}")
async def get_import_batch_detail(
    batch_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    try:
        detail = await svc.get_import_batch_detail(current_user.tenant_id, batch_id)
        return detail
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/reservations/stats")
async def get_reservation_stats(
    connector_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    return await svc.get_reservation_stats(current_user.tenant_id, connector_id)


@router.post("/reservations/retry-acks")
async def retry_failed_acks(
    connector_id: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    try:
        return await svc.retry_failed_acks(current_user.tenant_id, connector_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/reservations/lineage/{reservation_id}")
async def get_reservation_lineage(
    reservation_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get the full lineage/history of a reservation by its external ID."""
    svc = ReservationImportService()
    detail = await svc.get_imported_reservation_detail(current_user.tenant_id, reservation_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Imported reservation not found")

    external_id = detail.get("external_reservation_id")
    connector_id = detail.get("connector_id")
    if not external_id:
        return {"reservation": detail, "lineage": [detail]}

    from core.database import db
    lineage_docs = await db["cm_imported_reservations"].find(
        {
            "tenant_id": current_user.tenant_id,
            "connector_id": connector_id,
            "external_reservation_id": external_id,
        },
        {"_id": 0},
    ).sort("created_at", 1).to_list(50)

    return {
        "reservation": detail,
        "lineage": lineage_docs,
        "lineage_count": len(lineage_docs),
    }


@router.get("/reservations/audit-trail")
async def get_reservation_audit_trail(
    connector_id: str | None = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    logs = await svc.get_audit_trail(current_user.tenant_id, connector_id, limit)
    return {"audit_logs": logs, "count": len(logs)}
