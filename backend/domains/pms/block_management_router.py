"""Block Management — Cutoff alerts, Wash, Pickup raporları (Opera-uyumlu).
Mevcut group_blocks koleksiyonu üzerine çalışır.

Yetkilendirme:
  - Listing/raporlar: require_op("view_finance_reports")
  - Mutating (wash, create): require_op("post_charge")

Cache:
  - /summary ve /cutoff-alerts → 60s TTL (cache_manager.cache).
  - /wash ve /create yazma sonrası tenant cache invalidate edilir.
  - Legacy POST /api/groups/create-block aynı koleksiyona yazar fakat
    bu router'ın cache key'lerinden haberi yoktur; en kötü 60s gecikme
    olur.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from cache_manager import cache as _cache
from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/block-mgmt", tags=["PMS / Block Management"])

_BLOCK_CACHE_TTL = 60
_BLOCK_CACHE_PREFIXES = ("block_summary", "block_cutoff_alerts")


def _block_cache_key(name: str, tenant_id: str, suffix: str = "") -> str:
    sfx = f":{suffix}" if suffix else ""
    return f"cache:{tenant_id}:{name}{sfx}"


def _invalidate_block_cache(tenant_id: str) -> None:
    for p in _BLOCK_CACHE_PREFIXES:
        _cache.safe_invalidate(tenant_id, p)


def _to_datetime(value: Any) -> datetime | None:
    """str (ISO) | datetime | date → tz-aware datetime; aksi takdirde None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return None
    return None


class WashBody(BaseModel):
    wash_count: int = Field(..., ge=1, description="Bırakılacak (geri verilecek) oda sayısı")
    note: str | None = None


class CreateBlockBody(BaseModel):
    group_name: str = Field(..., min_length=1)
    organization: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    check_in: str = Field(..., description="ISO YYYY-MM-DD")
    check_out: str = Field(..., description="ISO YYYY-MM-DD")
    cutoff_date: str | None = None
    total_rooms: int = Field(..., ge=1)
    group_rate: float | None = None
    room_type: str | None = "Standard"
    special_requirements: str | None = None
    status: str = Field("tentative", description="'tentative' veya 'definite'")


@router.get("/cutoff-alerts")
async def cutoff_alerts(
    days_ahead: int = 7,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
    _nocache: bool = Query(False, alias="nocache"),
):
    """Önümüzdeki N gün içinde cutoff'u dolacak gruplar.

    DB'de cutoff_date hem string (ISO) hem datetime saklanabildiği için
    karşılaştırma Python tarafında, tip-tolerant `_to_datetime` ile yapılır.
    Önceki sürüm `{"$gte": today.isoformat()}` ile sessizce 0 sonuç
    döndürüyordu (datetime saklı dokümanlarda).
    """
    cache_key = _block_cache_key("block_cutoff_alerts", user.tenant_id, str(days_ahead))
    if not _nocache:
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

    db = get_system_db()
    today = datetime.now(UTC)
    horizon = today + timedelta(days=days_ahead)
    cur = db.group_blocks.find({
        "tenant_id": user.tenant_id,
        "status": {"$in": ["tentative", "definite"]},
        "cutoff_date": {"$ne": None},
    }).sort("cutoff_date", 1)
    out: list[dict[str, Any]] = []
    async for g in cur:
        g.pop("_id", None)
        cd = _to_datetime(g.get("cutoff_date"))
        if cd is None or cd < today or cd > horizon:
            continue
        days_left = (cd - today).days
        total = int(g.get("total_rooms", 0) or 0)
        picked = int(g.get("rooms_picked_up", 0) or 0)
        out.append({
            "id": g.get("id"),
            "group_name": g.get("group_name"),
            "organization": g.get("organization"),
            "cutoff_date": g.get("cutoff_date"),
            "days_left": days_left,
            "total_rooms": total,
            "rooms_picked_up": picked,
            "remaining": max(total - picked, 0),
            "status": g.get("status"),
        })
    payload = {"count": len(out), "alerts": out}
    _cache.set(cache_key, payload, ttl=_BLOCK_CACHE_TTL)
    return payload


@router.post("/{block_id}/wash")
async def wash_block(
    block_id: str,
    body: WashBody,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),
):
    """Grup bloğundan kullanılmayacağı anlaşılan odaları envantere geri verir.

    Defensive guards:
      - total_rooms <= rooms_picked_up ise wash imkânsız (400)
      - new_total < rooms_picked_up'a düşmeye izin verilmez (data-corruption şeridi)
      - wash_count >= 1 (Pydantic ge=1)
    """
    db = get_system_db()
    g = await db.group_blocks.find_one({"id": block_id, "tenant_id": user.tenant_id})
    if not g:
        raise HTTPException(404, "Grup bloğu bulunamadı")
    total = int(g.get("total_rooms", 0) or 0)
    picked = int(g.get("rooms_picked_up", 0) or 0)
    available_to_wash = max(total - picked, 0)
    if available_to_wash <= 0:
        raise HTTPException(400, "Bırakılacak müsait oda yok (alınmış oda sayısı toplamı yakaladı)")
    if body.wash_count > available_to_wash:
        raise HTTPException(400, f"En fazla {available_to_wash} oda wash edilebilir")
    new_total = total - body.wash_count
    if new_total < picked:
        # Tip kontrol — buraya normalde düşülmez ama veri tutarsızlığında patla
        raise HTTPException(400, "Yeni toplam, alınmış oda sayısının altına inemez")
    await db.group_blocks.update_one(
        {"id": block_id, "tenant_id": user.tenant_id},
        {
            "$set": {
                "total_rooms": new_total,
                "last_wash_at": datetime.now(UTC).isoformat(),
                "last_wash_by": user.email,
            },
            "$inc": {"washed_count": body.wash_count},
            "$push": {
                "wash_history": {
                    "count": body.wash_count,
                    "note": body.note,
                    "by": user.email,
                    "at": datetime.now(UTC).isoformat(),
                }
            },
        },
    )
    _invalidate_block_cache(user.tenant_id)
    return {
        "ok": True,
        "block_id": block_id,
        "washed": body.wash_count,
        "new_total_rooms": new_total,
        "rooms_picked_up": picked,
    }


@router.get("/{block_id}/pickup")
async def pickup_report(
    block_id: str,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    """Bir grubun günlük pickup eğrisi.

    Pickup tanımı (Opera): bloktan check-in OLMUŞ rezervasyon. Anchor
    önceliği:
      1. checked_in_at  — gerçek pickup
      2. rooming_added_at  — rooming-list'e eklenme
      3. created_at  — eski davranış (fallback)
    """
    db = get_system_db()
    g = await db.group_blocks.find_one({"id": block_id, "tenant_id": user.tenant_id})
    if not g:
        raise HTTPException(404, "Grup bloğu bulunamadı")
    cur = db.bookings.find({
        "tenant_id": user.tenant_id,
        "$or": [{"group_block_id": block_id}, {"group_id": block_id}],
        "status": {"$ne": "cancelled"},
    })
    by_day: dict[str, int] = {}
    total_picked = 0
    async for b in cur:
        anchor = (
            b.get("checked_in_at")
            or b.get("rooming_added_at")
            or b.get("created_at")
            or ""
        )
        d = str(anchor)[:10]
        if not d:
            continue
        by_day[d] = by_day.get(d, 0) + 1
        total_picked += 1
    series = [{"date": d, "rooms": by_day[d]} for d in sorted(by_day.keys())]
    cumulative = 0
    for s in series:
        cumulative += s["rooms"]
        s["cumulative"] = cumulative
    total_rooms = int(g.get("total_rooms", 0) or 0)
    return {
        "block_id": block_id,
        "group_name": g.get("group_name"),
        "total_rooms": total_rooms,
        "picked_up": total_picked,
        "remaining": max(total_rooms - total_picked, 0),
        "cutoff_date": g.get("cutoff_date"),
        "pickup_curve": series,
        "anchor_field": "checked_in_at|rooming_added_at|created_at",
    }


@router.get("/summary")
async def summary(
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
    _nocache: bool = Query(False, alias="nocache"),
):
    """Tüm aktif grupların özet pickup/wash tablosu (60s cache)."""
    cache_key = _block_cache_key("block_summary", user.tenant_id)
    if not _nocache:
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached
    db = get_system_db()
    cur = db.group_blocks.find({
        "tenant_id": user.tenant_id,
        "status": {"$in": ["tentative", "definite"]},
    }).sort("check_in", 1)
    out: list[dict[str, Any]] = []
    async for g in cur:
        g.pop("_id", None)
        total = int(g.get("total_rooms", 0) or 0)
        picked = int(g.get("rooms_picked_up", 0) or 0)
        out.append({
            "id": g.get("id"),
            "group_name": g.get("group_name"),
            "check_in": g.get("check_in"),
            "check_out": g.get("check_out"),
            "cutoff_date": g.get("cutoff_date"),
            "total_rooms": total,
            "rooms_picked_up": picked,
            "washed_count": int(g.get("washed_count", 0) or 0),
            "pickup_pct": round((picked / total * 100) if total else 0, 1),
            "status": g.get("status"),
        })
    payload = {"count": len(out), "blocks": out}
    _cache.set(cache_key, payload, ttl=_BLOCK_CACHE_TTL)
    return payload


@router.post("/create")
async def create_block(
    body: CreateBlockBody,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),
):
    """Yeni grup bloğu oluştur (BlockManagement sayfasından).

    `groups_router.create_group_block` (POST /api/groups/create-block) ile
    AYNI koleksiyona (`group_blocks`) yazar; UI tutarlılığı için bu router
    üzerinden de erişilebilir kılındı (yazma sonrası cache invalidation).
    """
    db = get_system_db()
    ci = _to_datetime(body.check_in)
    co = _to_datetime(body.check_out)
    if not ci or not co:
        raise HTTPException(400, "Geçersiz check_in/check_out tarihi (YYYY-MM-DD bekleniyor)")
    if co <= ci:
        raise HTTPException(400, "check_out, check_in'den sonra olmalı")
    if body.status not in ("tentative", "definite"):
        raise HTTPException(400, "status 'tentative' veya 'definite' olmalı")

    cutoff = body.cutoff_date or body.check_in
    block = {
        "id": str(uuid.uuid4()),
        "tenant_id": user.tenant_id,
        "group_name": body.group_name.strip(),
        "organization": body.organization,
        "contact_name": body.contact_name,
        "contact_email": body.contact_email,
        "contact_phone": body.contact_phone,
        "check_in": body.check_in,
        "check_out": body.check_out,
        "cutoff_date": cutoff,
        "total_rooms": int(body.total_rooms),
        "rooms_picked_up": 0,
        "washed_count": 0,
        "group_rate": body.group_rate,
        "room_type": body.room_type or "Standard",
        "special_requirements": body.special_requirements,
        "status": body.status,
        "created_by": getattr(user, "email", None) or getattr(user, "id", None),
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    await db.group_blocks.insert_one(block)
    _invalidate_block_cache(user.tenant_id)
    block.pop("_id", None)
    return {"success": True, "block": block}
