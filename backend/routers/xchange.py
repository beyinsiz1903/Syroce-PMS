"""Syroce Xchange admin router — partner config, message log, replay."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.security import _is_super_admin, get_current_user
from core.tenant_db import get_system_db
from integrations.xchange.bus import bus
from integrations.xchange.registry import PARTNERS, list_partners
from integrations.xchange.schemas import MessageType
from models.schemas import User

router = APIRouter(prefix="/api/xchange", tags=["xchange"])

_ADMIN_ROLES = {"super_admin", "platform_admin", "admin", "owner"}


def _require_admin(user: User) -> None:
    if _is_super_admin(user):
        return
    if (user.role or "").lower() in _ADMIN_ROLES:
        return
    roles = getattr(user, "roles", None) or []
    if isinstance(roles, list) and any(((r or "").lower() in _ADMIN_ROLES) for r in roles):
        return
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
    # P1 #7: deterministik sıra (en son güncellenen önce, sonra partner_code).
    cur = db.xchange_partner_configs.find({"tenant_id": tenant_id}, {"_id": 0}).sort([("updated_at", -1), ("partner_code", 1)])
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
    existing = await db.xchange_partner_configs.find_one({"tenant_id": tenant_id, "partner_code": partner_code})
    partner = PARTNERS[partner_code]
    config = dict(body.config or {})
    for fname, fmeta in partner.config_schema.items():
        if fmeta.get("type") == "secret":
            if config.get(fname) in (None, "", "***masked***") and existing:
                config[fname] = (existing.get("config") or {}).get(fname, "")
    doc = await bus.upsert_partner_config(tenant_id, partner_code, config=config, enabled=body.enabled)
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
    res = await db.xchange_partner_configs.delete_one({"tenant_id": tenant_id, "partner_code": partner_code})
    return {"ok": True, "deleted": res.deleted_count}


# ── Message log ──────────────────────────────────────────────────
@router.get("/deliveries")
async def list_deliveries(
    current_user: User = Depends(get_current_user),
    partner: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(
        None,
        description="P1 #8: pagination cursor — bir önceki sayfadaki son kaydın created_at ISO timestamp'i",
    ),
) -> dict:
    _require_admin(current_user)
    tenant_id = _require_tenant(current_user)
    db = get_system_db()
    q: dict[str, Any] = {"tenant_id": tenant_id}
    if partner:
        q["partner_code"] = partner
    if status:
        q["status"] = status
    if cursor:
        # cursor = en son görülen created_at (ISO) — keyset pagination
        q["created_at"] = {"$lt": cursor}
    cur = (
        db.xchange_deliveries.find(q, {"_id": 0, "envelope": 0}).sort("created_at", -1).limit(limit + 1)  # extra row → next_cursor varsa belirle
    )
    items = [doc async for doc in cur]
    next_cursor = None
    if len(items) > limit:
        next_cursor = items[limit - 1].get("created_at")
        items = items[:limit]
    # Aggregate counts (filtre uygulanmış scope üzerinde)
    counts_match: dict[str, Any] = {"tenant_id": tenant_id}
    if partner:
        counts_match["partner_code"] = partner
    pipeline = [
        {"$match": counts_match},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    counts: dict[str, int] = {}
    async for row in db.xchange_deliveries.aggregate(pipeline):
        counts[row["_id"]] = row["count"]
    return {"deliveries": items, "counts": counts, "next_cursor": next_cursor}


# P1 #13: envelope içindeki Authorization header / API key / partner secret
# alanları detail response'unda maskelenir (operatör görüntülerken plaintext sızmasın).
_SECRET_KEY_HINTS = (
    "authorization",
    "auth_token",
    "token",
    "secret",
    "api_key",
    "apikey",
    "password",
    "pass",
    "x-api-key",
    "bearer",
    "session",
    "cookie",
    "private_key",
)


def _sanitize_envelope(env: Any) -> Any:
    """Recursively mask values whose key looks like a secret/credential."""
    if isinstance(env, dict):
        masked: dict[str, Any] = {}
        for k, v in env.items():
            kl = str(k).lower()
            if any(h in kl for h in _SECRET_KEY_HINTS):
                masked[k] = "***masked***"
            else:
                masked[k] = _sanitize_envelope(v)
        return masked
    if isinstance(env, list):
        return [_sanitize_envelope(x) for x in env]
    return env


# P0 #3: replay yalnız bu durumlardan yapılabilir → çift posting riski engellenir.
_REPLAYABLE_STATUSES = {"failed", "dead_letter"}


@router.get("/deliveries/{delivery_id}")
async def get_delivery(
    delivery_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_admin(current_user)
    tenant_id = _require_tenant(current_user)
    db = get_system_db()
    doc = await db.xchange_deliveries.find_one({"id": delivery_id, "tenant_id": tenant_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Delivery bulunamadı")
    if "envelope" in doc:
        doc["envelope"] = _sanitize_envelope(doc["envelope"])
    return doc


@router.post("/deliveries/{delivery_id}/replay")
async def replay(
    delivery_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """P0 #3: yalnız failed / dead_letter durumdaki mesajlar replay edilebilir.

    delivered/in_flight/pending/skipped → 409 Conflict (çift posting riski)."""
    _require_admin(current_user)
    tenant_id = _require_tenant(current_user)
    db = get_system_db()
    doc = await db.xchange_deliveries.find_one(
        {"id": delivery_id, "tenant_id": tenant_id},
        {"_id": 0, "tenant_id": 1, "status": 1},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Delivery bulunamadı")
    cur_status = (doc.get("status") or "").lower()
    if cur_status not in _REPLAYABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(f"Replay yalnız failed/dead_letter durumdaki mesajlar için yapılabilir (mevcut durum: {cur_status or 'bilinmiyor'}). Çift gönderim riski engellendi."),
        )
    try:
        return await bus.replay_delivery(delivery_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Bulk replay ──────────────────────────────────────────────────
class BulkReplayIn(BaseModel):
    delivery_ids: list[str]


@router.post("/deliveries/replay-bulk")
async def replay_bulk(
    body: BulkReplayIn,
    current_user: User = Depends(get_current_user),
) -> dict:
    """P1 #9: toplu replay (max 50 kayıt) — failed/dead_letter olmayan atlanır."""
    _require_admin(current_user)
    tenant_id = _require_tenant(current_user)
    if not body.delivery_ids:
        raise HTTPException(status_code=400, detail="delivery_ids boş")
    if len(body.delivery_ids) > 50:
        raise HTTPException(status_code=400, detail="Tek seferde en çok 50 mesaj replay edilebilir")
    db = get_system_db()
    results: list[dict[str, Any]] = []
    ok_count = 0
    skipped_count = 0
    for did in body.delivery_ids:
        d = await db.xchange_deliveries.find_one({"id": did, "tenant_id": tenant_id}, {"_id": 0, "status": 1})
        if not d:
            results.append({"id": did, "ok": False, "skipped": True, "reason": "not_found"})
            skipped_count += 1
            continue
        if (d.get("status") or "").lower() not in _REPLAYABLE_STATUSES:
            results.append({"id": did, "ok": False, "skipped": True, "reason": f"status={d.get('status')}"})
            skipped_count += 1
            continue
        try:
            r = await bus.replay_delivery(did)
            results.append({"id": did, "ok": True, "status": r.get("status"), "attempts": r.get("attempts")})
            ok_count += 1
        except Exception as e:
            results.append({"id": did, "ok": False, "error": str(e)})
    return {"ok": True, "replayed": ok_count, "skipped": skipped_count, "results": results}


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
    return await bus.publish(tenant_id=tenant_id, message_type=mt, payload=body.payload)
