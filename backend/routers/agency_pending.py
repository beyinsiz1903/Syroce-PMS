"""Pending work for either Agency Extranet party (see core.pending_actions).

Hotel (PMS JWT):   GET /api/marketplace/hotel/pending-actions
Agency (portal):   GET /api/marketplace/v1/pending-actions
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from core.pending_actions import pending_actions
from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from routers.marketplace_b2b import _require_hotel_admin, get_marketplace_agency

hotel_router = APIRouter(prefix="/api/marketplace/hotel/pending-actions", tags=["Marketplace / Pending actions (hotel)"])
agency_router = APIRouter(prefix="/api/marketplace/v1/pending-actions", tags=["Marketplace / Pending actions (agency)"])


@hotel_router.get("")
async def hotel_pending_actions(current_user: User = Depends(get_current_user)):
    tenant_id = _require_hotel_admin(current_user)
    return await pending_actions(get_system_db(), side="hotel", scope={"tenant_id": tenant_id}, today=datetime.now(UTC).date())


@agency_router.get("")
async def agency_pending_actions(agency: dict = Depends(get_marketplace_agency)):
    return await pending_actions(get_system_db(), side="agency", scope={"agency_id": agency["agency_id"]}, today=datetime.now(UTC).date())
