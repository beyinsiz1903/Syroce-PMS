"""Tenant-facing Onboarding Wizard endpoints.

The cross-tenant admin overview lives under
`/api/admin/tenants/{tenant_id}/onboarding`. This router exposes the
SAME progress engine but scoped to the caller's own tenant — for the
in-app wizard a hotelier sees on first login.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from cache_manager import cached
from core.onboarding import (
    DEFAULT_STEPS,
    get_onboarding_progress,
    mark_step_complete,
)
from core.security import get_current_user
from models.schemas import User

# Steps the wizard is allowed to mark complete by hand. Auto-detected
# steps (rooms_configured, rates_configured, ...) MUST come from the
# real underlying signals — never trust a client to claim them.
MANUAL_STEPS_ALLOWLIST = {"hotel_info_completed"}

# Roles allowed to mutate tenant onboarding state.
ADMIN_ROLES = {"super_admin", "platform_admin", "admin", "owner"}

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


def _db():
    from core.database import _raw_db
    return _raw_db


def _require_tenant(user: User) -> str:
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    return user.tenant_id


def _require_tenant_admin(user: User) -> str:
    """Require both a tenant context AND an admin-grade role for any
    mutation of tenant onboarding state. Receptionists and other
    line-staff users may READ progress but never write."""
    tenant_id = _require_tenant(user)
    role = (user.role or "").lower()
    if role not in ADMIN_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Bu işlem için yönetici yetkisi gerekli",
        )
    return tenant_id


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── Read progress ───────────────────────────────────────────────
@router.get("/progress")
@cached(ttl=60, key_prefix="onboarding_progress")
async def progress(current_user: User = Depends(get_current_user)) -> dict:
    tenant_id = _require_tenant(current_user)
    data = await get_onboarding_progress(tenant_id)
    # Surface dismissed flag from the same progress doc so the UI can
    # decide whether to auto-pop the wizard on login.
    db = _db()
    doc = await db.onboarding_progress.find_one(
        {"tenant_id": tenant_id}, {"_id": 0, "dismissed": 1, "dismissed_at": 1}
    ) or {}
    data["dismissed"] = bool(doc.get("dismissed"))
    data["dismissed_at"] = doc.get("dismissed_at")
    return data


# ── Manual step completion ──────────────────────────────────────
class StepIn(BaseModel):
    step_id: str


@router.post("/complete-step")
async def complete_step(
    payload: StepIn,
    current_user: User = Depends(get_current_user),
) -> dict:
    tenant_id = _require_tenant_admin(current_user)
    # Whitelist guard: only manual-allowlisted steps can be claimed by
    # the client. All others are derived from real PMS data and must
    # not be settable from the wizard.
    if payload.step_id not in MANUAL_STEPS_ALLOWLIST:
        # Reject with a clear, non-leaky message — also helps catch
        # client bugs that try to mark the wrong key.
        valid_keys = {s["step_id"] for s in DEFAULT_STEPS}
        if payload.step_id not in valid_keys:
            raise HTTPException(
                status_code=400, detail="Geçersiz adım kimliği"
            )
        raise HTTPException(
            status_code=400,
            detail="Bu adım otomatik algılanır; manuel işaretleme kabul edilmiyor",
        )
    await mark_step_complete(tenant_id, payload.step_id)
    return await get_onboarding_progress(tenant_id)


# ── Dismiss / undismiss the wizard auto-popup ───────────────────
@router.post("/dismiss")
async def dismiss(current_user: User = Depends(get_current_user)) -> dict:
    """User clicked "Şimdilik atla" — don't auto-show the wizard
    anymore. Progress itself is preserved; user can still open the
    wizard manually from the nav. Admin-only: a non-admin user must
    not be able to suppress the wizard for the entire tenant."""
    tenant_id = _require_tenant_admin(current_user)
    await _db().onboarding_progress.update_one(
        {"tenant_id": tenant_id},
        {
            "$set": {"dismissed": True, "dismissed_at": _now_iso()},
            "$setOnInsert": {"tenant_id": tenant_id, "created_at": _now_iso()},
        },
        upsert=True,
    )
    return {"ok": True, "dismissed": True}


@router.post("/resume")
async def resume(current_user: User = Depends(get_current_user)) -> dict:
    tenant_id = _require_tenant_admin(current_user)
    await _db().onboarding_progress.update_one(
        {"tenant_id": tenant_id},
        {"$set": {"dismissed": False, "updated_at": _now_iso()}},
    )
    return {"ok": True, "dismissed": False}


# ── Step 1: Hotel info update ───────────────────────────────────
class HotelInfoIn(BaseModel):
    property_name: str | None = Field(default=None, max_length=200)
    property_type: str | None = Field(default=None, max_length=50)
    contact_phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=200)
    total_rooms: int | None = Field(default=None, ge=1, le=10000)


@router.patch("/hotel-info")
async def update_hotel_info(
    payload: HotelInfoIn,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Step 1 of the wizard: persists basic property fields onto the
    tenant document. Empty / null fields are NOT cleared (partial
    update). Admin-only: only the tenant owner/admin may mutate
    property profile."""
    tenant_id = _require_tenant_admin(current_user)
    update: dict = {}
    for k, v in payload.model_dump(exclude_unset=True).items():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        update[k] = v.strip() if isinstance(v, str) else v

    if not update:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")

    update["updated_at"] = _now_iso()
    res = await _db().tenants.update_one({"id": tenant_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tenant bulunamadı")

    # Auto-mark hotel-info step done so it shows ✓ in progress.
    await mark_step_complete(tenant_id, "hotel_info_completed")

    tenant = await _db().tenants.find_one(
        {"id": tenant_id},
        {"_id": 0, "id": 1, "property_name": 1, "property_type": 1,
         "contact_phone": 1, "address": 1, "location": 1, "total_rooms": 1},
    )
    return {"ok": True, "tenant": tenant, "updated_fields": list(update.keys())}
