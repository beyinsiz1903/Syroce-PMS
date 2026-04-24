"""KBS (Konaklama Bildirim Sistemi) — Kullanıcı oturumu tabanlı uçlar.

Bu router, masaüstü/yardımcı KBS uygulamasının PMS otel kullanıcısının
kendi e-posta + şifre bilgileriyle (POST /api/auth/login) giriş yapıp
dönen JWT token'ı ile çalışmasını sağlar. Her otel için ayrı API key
dağıtmaya gerek yoktur — tenant_id, oturumdaki kullanıcıdan otomatik
çözülür ve kullanıcı sadece kendi otelinin verisini görür.

Endpoint'ler:
  GET  /api/kbs/guests             — bir günün KBS'ye girecek misafirleri
  POST /api/kbs/report             — gönderim işareti (rapor kaydı)
  GET  /api/kbs/reports            — geçmiş raporlar
  GET  /api/kbs/reports/{id}       — rapor detayı
"""

from __future__ import annotations
from modules.pms_core.role_permission_service import require_op  # v98 DW

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from core.tenant_db import tenant_context
from models.schemas import User

router = APIRouter(prefix="/api/kbs", tags=["KBS"])


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


@router.get("/guests")
async def kbs_guest_list(
    date: str | None = Query(None, description="YYYY-MM-DD (varsayılan: bugün)"),
    status: str | None = Query(None, description="Booking status filtresi"),
    limit: int = Query(200, le=500),
    current_user: User = Depends(get_current_user),
):
    """KBS bildirimine girecek misafir listesi (oturumdaki kullanıcının oteli için)."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    target_date = date or datetime.now(UTC).strftime("%Y-%m-%d")
    status_filter = (
        [status] if status
        else ["checked_in", "confirmed", "guaranteed"]
    )

    with tenant_context(tenant_id):
        bookings = await db.bookings.find(
            {
                "tenant_id": tenant_id,
                "status": {"$in": status_filter},
                "check_in": {
                    "$gte": target_date + "T00:00:00",
                    "$lte": target_date + "T23:59:59",
                },
            },
            {
                "_id": 0, "id": 1, "guest_id": 1, "guest_name": 1,
                "guest_email": 1, "guest_phone": 1, "room_number": 1,
                "check_in": 1, "check_out": 1, "adults": 1, "children": 1,
                "status": 1, "confirmation_code": 1,
            },
        ).sort("check_in", 1).to_list(limit)

        guest_ids = [b.get("guest_id") for b in bookings if b.get("guest_id")]
        guest_map: dict[str, dict] = {}
        if guest_ids:
            async for g in db.guests.find(
                {"tenant_id": tenant_id, "id": {"$in": guest_ids}},
                {"_id": 0, "id": 1, "nationality": 1, "id_number": 1,
                 "passport_number": 1, "birth_date": 1, "gender": 1,
                 "address": 1, "father_name": 1, "mother_name": 1,
                 "birth_place": 1},
            ):
                guest_map[g["id"]] = g

        for b in bookings:
            g = guest_map.get(b.get("guest_id"), {})
            b["nationality"] = g.get("nationality", "")
            b["id_number"] = g.get("id_number", "")
            b["passport_number"] = g.get("passport_number", "")
            b["birth_date"] = g.get("birth_date", "")
            b["gender"] = g.get("gender", "")
            b["address"] = g.get("address", "")
            b["father_name"] = g.get("father_name", "")
            b["mother_name"] = g.get("mother_name", "")
            b["birth_place"] = g.get("birth_place", "")
            b["kbs_ready"] = bool(
                (g.get("id_number") or g.get("passport_number"))
                and g.get("birth_date")
                and g.get("nationality")
            )

        reports = await db.kbs_reports.find(
            {"tenant_id": tenant_id, "date": target_date},
            {"_id": 0},
        ).sort("created_at", -1).to_list(50)

    return {
        "date": target_date,
        "tenant_id": tenant_id,
        "guests": bookings,
        "guest_count": len(bookings),
        "ready_count": sum(1 for b in bookings if b.get("kbs_ready")),
        "missing_info_count": sum(1 for b in bookings if not b.get("kbs_ready")),
        "reports": reports,
        "report_count": len(reports),
    }


class KBSReportCreate(BaseModel):
    date: str
    booking_ids: list[str] = []
    notes: str = ""
    submission_reference: str = ""


@router.post("/report")
async def kbs_create_report(
    data: KBSReportCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    """KBS resmi servisine gönderim sonrası PMS'e işaret bırak."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    report_id = _uuid()
    report = {
        "id": report_id,
        "tenant_id": tenant_id,
        "date": data.date,
        "status": "submitted",
        "guest_count": len(data.booking_ids),
        "guest_ids": data.booking_ids,
        "notes": data.notes,
        "submission_reference": data.submission_reference,
        "submitted_by": f"user:{current_user.id}",
        "submitted_by_email": current_user.email,
        "created_at": _now_iso(),
    }
    with tenant_context(tenant_id):
        await db.kbs_reports.insert_one(report)
        if data.booking_ids:
            await db.bookings.update_many(
                {"tenant_id": tenant_id, "id": {"$in": data.booking_ids}},
                {"$set": {
                    "kbs_reported": True,
                    "kbs_report_id": report_id,
                    "kbs_reported_at": _now_iso(),
                }},
            )
    report.pop("_id", None)
    return {"ok": True, "report": report}


@router.get("/reports")
async def kbs_list_reports(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    """Geçmiş KBS raporları (oturumdaki kullanıcının oteli için)."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    q: dict = {"tenant_id": tenant_id}
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to

    with tenant_context(tenant_id):
        docs = await db.kbs_reports.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"reports": docs, "total": len(docs)}


@router.get("/reports/{report_id}")
async def kbs_get_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    with tenant_context(tenant_id):
        doc = await db.kbs_reports.find_one(
            {"tenant_id": tenant_id, "id": report_id}, {"_id": 0}
        )
    if not doc:
        raise HTTPException(404, "KBS raporu bulunamadı")
    return {"report": doc}


@router.get("/me")
async def kbs_who_am_i(current_user: User = Depends(get_current_user)):
    """KBS uygulaması için 'login başarılı mı, hangi otele bağlıyım' kontrolü."""
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "full_name": getattr(current_user, "full_name", ""),
        "tenant_id": current_user.tenant_id,
        "role": getattr(current_user, "role", ""),
    }
