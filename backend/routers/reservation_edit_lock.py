"""Authenticated reservation-detail edit-lock endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from core.database import _raw_db
from core.reservation_edit_lock import (
    ReservationEditLockConflict,
    ReservationEditLockLost,
    acquire_reservation_edit_lock,
    release_reservation_edit_lock,
    renew_reservation_edit_lock,
)
from core.security import get_current_user
from models.schemas import User, _ensure_hotel_context

router = APIRouter(prefix="/api/pms/reservations", tags=["reservation-edit-lock"])


class EditLockRequest(BaseModel):
    lock_id: UUID


def _scope(current_user: User) -> tuple[str, str]:
    _ensure_hotel_context(current_user)
    return str(current_user.tenant_id), str(current_user.id)


async def _ensure_booking_exists(tenant_id: str, booking_id: str) -> None:
    booking = await _raw_db.bookings.find_one(
        {"tenant_id": tenant_id, "id": booking_id},
        {"_id": 0, "id": 1},
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Reservation not found")


@router.post("/{booking_id}/edit-lock/acquire")
async def acquire_edit_lock(
    booking_id: str,
    request: EditLockRequest,
    current_user: User = Depends(get_current_user),
):
    tenant_id, owner_user_id = _scope(current_user)
    await _ensure_booking_exists(tenant_id, booking_id)
    try:
        lease = await acquire_reservation_edit_lock(
            _raw_db,
            tenant_id=tenant_id,
            booking_id=booking_id,
            owner_user_id=owner_user_id,
            lock_id=str(request.lock_id),
        )
    except ReservationEditLockConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "RESERVATION_EDIT_LOCKED", "message": str(exc)},
        ) from exc
    return lease.public_dict()


@router.post("/{booking_id}/edit-lock/heartbeat")
async def heartbeat_edit_lock(
    booking_id: str,
    request: EditLockRequest,
    current_user: User = Depends(get_current_user),
):
    tenant_id, owner_user_id = _scope(current_user)
    try:
        lease = await renew_reservation_edit_lock(
            _raw_db,
            tenant_id=tenant_id,
            booking_id=booking_id,
            owner_user_id=owner_user_id,
            lock_id=str(request.lock_id),
        )
    except ReservationEditLockLost as exc:
        raise HTTPException(
            status_code=423,
            detail={"code": "RESERVATION_EDIT_LOCK_LOST", "message": str(exc)},
        ) from exc
    return lease.public_dict()


@router.delete("/{booking_id}/edit-lock")
async def release_edit_lock(
    booking_id: str,
    request: EditLockRequest,
    current_user: User = Depends(get_current_user),
):
    tenant_id, owner_user_id = _scope(current_user)
    try:
        released = await release_reservation_edit_lock(
            _raw_db,
            tenant_id=tenant_id,
            booking_id=booking_id,
            owner_user_id=owner_user_id,
            lock_id=str(request.lock_id),
        )
    except ReservationEditLockConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "RESERVATION_EDIT_LOCK_OWNER_MISMATCH", "message": str(exc)},
        ) from exc
    return {"released": released}
