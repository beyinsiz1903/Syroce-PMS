"""Block Management — Cutoff alerts, Wash, Pickup raporları (Opera-uyumlu).
Mevcut group_blocks koleksiyonu üzerine çalışır.

Yetkilendirme:
  - Listing/raporlar: require_op("view_finance_reports")
  - Mutating (wash): require_op("post_charge")
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/block-mgmt", tags=["PMS / Block Management"])


class WashBody(BaseModel):
    wash_count: int = Field(..., ge=0, description="Bırakılacak (geri verilecek) oda sayısı")
    note: str | None = None


@router.get("/cutoff-alerts")
async def cutoff_alerts(
    days_ahead: int = 7,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    """Önümüzdeki N gün içinde cutoff'u dolacak gruplar."""
    db = get_system_db()
    today = datetime.now(UTC)
    horizon = today + timedelta(days=days_ahead)
    cur = db.group_blocks.find({
        "tenant_id": user.tenant_id,
        "status": {"$in": ["tentative", "definite"]},
        "cutoff_date": {"$gte": today.isoformat(), "$lte": horizon.isoformat()},
    }).sort("cutoff_date", 1)
    out = []
    async for g in cur:
        g.pop("_id", None)
        cutoff = g.get("cutoff_date")
        days_left = None
        if cutoff:
            try:
                cd = datetime.fromisoformat(str(cutoff).replace("Z", "+00:00"))
                days_left = (cd - today).days
            except Exception:
                pass
        out.append({
            "id": g.get("id"),
            "group_name": g.get("group_name"),
            "organization": g.get("organization"),
            "cutoff_date": cutoff,
            "days_left": days_left,
            "total_rooms": g.get("total_rooms", 0),
            "rooms_picked_up": g.get("rooms_picked_up", 0),
            "remaining": g.get("total_rooms", 0) - g.get("rooms_picked_up", 0),
            "status": g.get("status"),
        })
    return {"count": len(out), "alerts": out}


@router.post("/{block_id}/wash")
async def wash_block(
    block_id: str,
    body: WashBody,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),
):
    """Grup bloğundan kullanılmayacağı anlaşılan odaları envantere geri verir."""
    db = get_system_db()
    g = await db.group_blocks.find_one({"id": block_id, "tenant_id": user.tenant_id})
    if not g:
        raise HTTPException(404, "Grup bloğu bulunamadı")
    total = g.get("total_rooms", 0)
    picked = g.get("rooms_picked_up", 0)
    available_to_wash = total - picked
    if body.wash_count > available_to_wash:
        raise HTTPException(
            400, f"En fazla {available_to_wash} oda wash edilebilir"
        )
    new_total = total - body.wash_count
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
    """Bir grubun günlük pickup eğrisi: ne zaman kaç oda alındı."""
    db = get_system_db()
    g = await db.group_blocks.find_one({"id": block_id, "tenant_id": user.tenant_id})
    if not g:
        raise HTTPException(404, "Grup bloğu bulunamadı")
    # Bu grup adına yapılan rezervasyonları topla
    cur = db.bookings.find({
        "tenant_id": user.tenant_id,
        "$or": [{"group_block_id": block_id}, {"group_id": block_id}],
        "status": {"$ne": "cancelled"},
    })
    by_day: dict[str, int] = {}
    total_picked = 0
    async for b in cur:
        created = (b.get("created_at") or "")[:10]
        by_day[created] = by_day.get(created, 0) + 1
        total_picked += 1
    series = [
        {"date": d, "rooms": by_day[d]} for d in sorted(by_day.keys())
    ]
    cumulative = 0
    for s in series:
        cumulative += s["rooms"]
        s["cumulative"] = cumulative
    return {
        "block_id": block_id,
        "group_name": g.get("group_name"),
        "total_rooms": g.get("total_rooms", 0),
        "picked_up": total_picked,
        "remaining": g.get("total_rooms", 0) - total_picked,
        "cutoff_date": g.get("cutoff_date"),
        "pickup_curve": series,
    }


@router.get("/summary")
async def summary(
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    """Tüm aktif grupların özet pickup/wash tablosu."""
    db = get_system_db()
    cur = db.group_blocks.find({
        "tenant_id": user.tenant_id,
        "status": {"$in": ["tentative", "definite"]},
    }).sort("check_in", 1)
    out: list[dict[str, Any]] = []
    async for g in cur:
        g.pop("_id", None)
        total = g.get("total_rooms", 0)
        picked = g.get("rooms_picked_up", 0)
        out.append({
            "id": g.get("id"),
            "group_name": g.get("group_name"),
            "check_in": g.get("check_in"),
            "check_out": g.get("check_out"),
            "cutoff_date": g.get("cutoff_date"),
            "total_rooms": total,
            "rooms_picked_up": picked,
            "washed_count": g.get("washed_count", 0),
            "pickup_pct": round((picked / total * 100) if total else 0, 1),
            "status": g.get("status"),
        })
    return {"count": len(out), "blocks": out}
