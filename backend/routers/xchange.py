"""Syroce Xchange admin router — partner config, message log, replay."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.security import get_current_user
from core.tenant_db import get_system_db
from integrations.xchange.bus import bus
from integrations.xchange.registry import PARTNERS, list_partners
from integrations.xchange.schemas import MessageType
from models.schemas import User

router = APIRouter(prefix="/api/xchange", tags=["xchange"])

_ADMIN_ROLES = {"super_admin", "platform_admin", "admin", "owner"}


def _require_admin(user: User) -> None:
    if (user.role or "").lower() not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Yönetici yetkisi gerekli")


def _require_tenant(user: User) -> str:
    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant bağlamı gerekli")
    return user.tenant_id


# ── Catalog ───────────────────────────────────────────────────────
@router.get("/partners")
async def get_partners_catalog(current_user: User = Depends(get_current_user)) -> dict:
    _require_admin(current_user)
    return {"partners": list_partners()}


# ── Per-tenant config ────────────────────────────────────────────
class PartnerConfigIn(BaseModel):
    enabled: bool = True
    config: dict[str, Any]


@router.get("/configs")
async def list_configs(current_user: User = Depends(get_current_user)) -> dict:
    _require_admin(current_user)
    tenant_id = _require_tenant(current_user)
    db = get_system_db()
    cur = db.xchange_partner_configs.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    )
    docs = [doc async for doc in cur]
    # Mask secret fields in response
    for d in docs:
        partner = PARTNERS.get(d["partner_code"])
        if partner:
            for fname, fmeta in partner.config_schema.items():
                if fmeta.get("type") == "secret" and (d.get("config") or {}).get(fname):
                    d["config"][fname] = "***masked***"
    return {"configs": docs}


@router.put("/configs/{partner_code}")
async def upsert_config(
    partner_code: str,
    body: PartnerConfigIn,
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_admin(current_user)
    tenant_id = _require_tenant(current_user)
    if partner_code not in PARTNERS:
        raise HTTPException(status_code=404, detail="Bilinmeyen partner")
    # If a secret field arrives masked, keep the existing value.
    db = get_system_db()
    existing = await db.xchange_partner_configs.find_one(
        {"tenant_id": tenant_id, "partner_code": partner_code}
    )
    partner = PARTNERS[partner_code]
    config = dict(body.config or {})
    for fname, fmeta in partner.config_schema.items():
        if fmeta.get("type") == "secret":
            if config.get(fname) in (None, "", "***masked***") and existing:
                config[fname] = (existing.get("config") or {}).get(fname, "")
    doc = await bus.upsert_partner_config(
        tenant_id, partner_code, config=config, enabled=body.enabled
    )
    doc.pop("_id", None)
    return {"ok": True, "config": doc}


@router.delete("/configs/{partner_code}")
async def delete_config(
    partner_code: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_admin(current_user)
    tenant_id = _require_tenant(current_user)
    db = get_system_db()
    res = await db.xchange_partner_configs.delete_one(
        {"tenant_id": tenant_id, "partner_code": partner_code}
    )
    return {"ok": True, "deleted": res.deleted_count}


# ── Message log ──────────────────────────────────────────────────
@router.get("/deliveries")
async def list_deliveries(
    current_user: User = Depends(get_current_user),
    partner: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    _require_admin(current_user)
    tenant_id = _require_tenant(current_user)
    db = get_system_db()
    q: dict[str, Any] = {"tenant_id": tenant_id}
    if partner:
        q["partner_code"] = partner
    if status:
        q["status"] = status
    cur = db.xchange_deliveries.find(q, {"_id": 0, "envelope": 0}).sort("created_at", -1).limit(limit)
    items = [doc async for doc in cur]
    # Aggregate counts
    pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    counts: dict[str, int] = {}
    async for row in db.xchange_deliveries.aggregate(pipeline):
        counts[row["_id"]] = row["count"]
    return {"deliveries": items, "counts": counts}


@router.get("/deliveries/{delivery_id}")
async def get_delivery(
    delivery_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_admin(current_user)
    tenant_id = _require_tenant(current_user)
    db = get_system_db()
    doc = await db.xchange_deliveries.find_one(
        {"id": delivery_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Delivery bulunamadı")
    return doc


@router.post("/deliveries/{delivery_id}/replay")
async def replay(
    delivery_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_admin(current_user)
    tenant_id = _require_tenant(current_user)
    db = get_system_db()
    doc = await db.xchange_deliveries.find_one(
        {"id": delivery_id, "tenant_id": tenant_id}, {"_id": 0, "tenant_id": 1}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Delivery bulunamadı")
    try:
        return await bus.replay_delivery(delivery_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Test publish (admin-only sandbox) ────────────────────────────
class TestPublishIn(BaseModel):
    message_type: str
    payload: dict[str, Any]


@router.post("/test-publish")
async def test_publish(
    body: TestPublishIn,
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_admin(current_user)
    tenant_id = _require_tenant(current_user)
    try:
        mt = MessageType(body.message_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Geçersiz mesaj tipi")
    return await bus.publish(
        tenant_id=tenant_id, message_type=mt, payload=body.payload
    )
