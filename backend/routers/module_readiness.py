"""Module readiness (see core.module_readiness).

Super admin:   GET /api/admin/tenants/{tenant_id}/module-readiness
Hotel admin:   GET /api/modules/readiness            (own hotel)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core.entitlement import effective_tenant_modules
from core.helpers import require_super_admin_guard
from core.module_readiness import tenant_readiness
from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from routers.marketplace_b2b import _require_hotel_admin

admin_router = APIRouter(prefix="/api/admin/tenants", tags=["Admin / Module readiness"])
hotel_router = APIRouter(prefix="/api/modules", tags=["Module readiness"])
require_super_admin = require_super_admin_guard()


async def _readiness(tenant_id: str) -> dict:
    db = get_system_db()
    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0})
    if not tenant:
        raise HTTPException(404, "Otel bulunamadı")
    modules = await effective_tenant_modules(tenant)
    return {"tenant_id": tenant_id, "modules": await tenant_readiness(db, tenant_id, modules)}


@admin_router.get("/{tenant_id}/module-readiness")
async def admin_module_readiness(tenant_id: str, current_user: User = Depends(require_super_admin)):
    return await _readiness(tenant_id)


@hotel_router.get("/readiness")
async def hotel_module_readiness(current_user: User = Depends(get_current_user)):
    return await _readiness(_require_hotel_admin(current_user))
