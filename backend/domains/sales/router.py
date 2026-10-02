"""
Domain Router: Sales CRM, Marketing & Service Recovery

Extracted from legacy_routes.py — leads, funnel, activities,
campaigns, segments, complaints, spa, events.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.helpers import create_audit_log
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_module as require_module_v97  # v97 DW
from modules.pms_core.role_permission_service import require_op  # v98 DW

router = APIRouter(prefix="/api", tags=["sales-crm-domain"])

# Geçerli lead aşamaları (frontend ile uyumlu 7'li huni).
LEAD_STAGES = {
    "new",
    "contacted",
    "qualified",
    "proposal_sent",
    "negotiating",
    "won",
    "lost",
}
# Geçerli aktivite tipleri.
ACTIVITY_TYPES = {"call", "email", "meeting", "note", "task"}

# Atlas 500 koleksiyon limiti dolu olduğundan, sales_leads/sales_activities
# yerine boş duran mice_opportunities/mice_opportunity_activities
# koleksiyonları yeniden kullanılır. _kind ayraç alanı ile MICE
# opportunity kayıtlarından (sales_catering.py) ayrılır.
LEAD_KIND = "lead"
ACTIVITY_KIND = "lead_activity"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _follow_up_iso(value: object) -> str | None:
    """Normalize a browser follow-up value to an unambiguous UTC timestamp."""
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="Takip tarihi geçersiz")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Takip tarihi geçersiz") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _active_lead_query(tenant_id: str, **extra: object) -> dict:
    return {"_kind": LEAD_KIND, "tenant_id": tenant_id, "deleted_at": {"$exists": False}, **extra}


def _open_follow_up_query(tenant_id: str, activity_id: str | None = None) -> dict:
    """Build the tenant-scoped selector for a follow-up that is still open."""
    query: dict = {
        "_kind": ACTIVITY_KIND,
        "tenant_id": tenant_id,
        "follow_up_at": {"$nin": [None, ""]},
        "follow_up_completed_at": {"$exists": False},
    }
    if activity_id:
        query["id"] = activity_id
    return query


# ── Sales CRM & Lead Management ────────────────────────────────────


@router.post("/sales/leads")
async def create_lead(
    lead_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """Yeni satis lead'i olustur"""
    contact_name = lead_data.get("contact_name") or lead_data.get("contact_person")
    contact_email = lead_data.get("contact_email") or lead_data.get("email")
    if not contact_name or not contact_email:
        raise HTTPException(status_code=400, detail="contact_name ve contact_email zorunlu")
    normalized_email = str(contact_email).strip().lower()
    duplicate = await db.mice_opportunities.find_one(
        _active_lead_query(current_user.tenant_id, contact_email_lower=normalized_email, status={"$nin": ["won", "lost"]}),
        {"_id": 0, "id": 1},
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Bu e-posta için açık bir lead zaten var")
    lead = {
        "_kind": LEAD_KIND,
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "company_name": lead_data.get("company_name"),
        "contact_name": contact_name,
        "contact_email": normalized_email,
        "contact_phone": lead_data.get("contact_phone") or lead_data.get("phone"),
        "source": lead_data.get("source") or lead_data.get("lead_source", "website"),
        "status": "new",
        "priority": lead_data.get("priority", "medium"),
        "estimated_value": lead_data.get("estimated_value"),
        "estimated_rooms": lead_data.get("estimated_rooms"),
        "target_checkin": lead_data.get("target_checkin"),
        "assigned_to": lead_data.get("assigned_to", current_user.id),
        "lead_score": 50,
        "notes": lead_data.get("notes"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    from security.search_normalize import apply_collection_normalized_fields

    apply_collection_normalized_fields(lead, collection="mice_opportunities")
    await db.mice_opportunities.insert_one(lead)
    await create_audit_log(current_user.tenant_id, current_user, "sales_lead_created", "sales_lead", lead["id"], {"source": lead["source"]})
    return {"success": True, "message": "Lead basariyla olusturuldu", "lead_id": lead["id"]}


@router.get("/sales/leads")
async def get_leads(
    status: str | None = None,
    q: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # GET'lere de yetki kontrolü
):
    """Lead'leri listele (status filtresi + isim/şirket/e-posta arama)."""
    query: dict = _active_lead_query(current_user.tenant_id)
    if status and status in LEAD_STAGES:
        query["status"] = status
    if q:
        # Index-serviceable anchored prefix search on `<field>_lower` companions
        # (backed by (tenant_id, <field>_lower) indexes), replacing the
        # un-indexable unanchored case-insensitive regex scan.
        from security.search_normalize import prefix_conditions

        conds = prefix_conditions(["contact_name", "company_name", "contact_email"], q)
        if conds:
            query["$or"] = conds
    leads = await db.mice_opportunities.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"leads": leads, "total": len(leads)}


@router.get("/sales/funnel")
async def get_sales_funnel(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # GET'e de yetki kontrolü
):
    """Satis hunisi metrikleri — tek aggregation ile (eski 7 sorgu yerine)."""
    pipeline = [
        {"$match": _active_lead_query(current_user.tenant_id)},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    rows = await db.mice_opportunities.aggregate(pipeline).to_list(50)
    funnel = dict.fromkeys(["new", "contacted", "qualified", "proposal_sent", "negotiating", "won", "lost"], 0)
    for r in rows:
        s = r.get("_id")
        if s in funnel:
            funnel[s] = int(r.get("count", 0))
    total = sum(funnel.values())
    return {
        "funnel": funnel,
        "total_leads": total,
        "win_rate": round((funnel["won"] / total * 100) if total > 0 else 0, 2),
    }


@router.get("/sales/leads/{lead_id}")
async def get_lead_detail(
    lead_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),
):
    """Tek lead + son aktiviteler."""
    lead = await db.mice_opportunities.find_one(_active_lead_query(current_user.tenant_id, id=lead_id), {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead bulunamadı")
    activities = (
        await db.mice_opportunity_activities.find(
            {"_kind": ACTIVITY_KIND, "tenant_id": current_user.tenant_id, "lead_id": lead_id},
            {"_id": 0},
        )
        .sort("created_at", -1)
        .to_list(50)
    )
    return {"lead": lead, "activities": activities}


@router.put("/sales/leads/{lead_id}/stage")
async def update_lead_stage(
    lead_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """Lead aşaması (status) güncelle."""
    new_status = (payload or {}).get("status")
    if new_status not in LEAD_STAGES:
        raise HTTPException(status_code=400, detail=f"Geçersiz aşama: {new_status}")
    res = await db.mice_opportunities.update_one(
        _active_lead_query(current_user.tenant_id, id=lead_id),
        {
            "$set": {
                "status": new_status,
                "updated_at": _now(),
                "updated_by": current_user.id,
            }
        },
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lead bulunamadı")
    # Aşama değişimini aktivite olarak da kaydet (denetim izi).
    await db.mice_opportunity_activities.insert_one(
        {
            "_kind": ACTIVITY_KIND,
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "lead_id": lead_id,
            "activity_type": "stage_change",
            "subject": f"Aşama: {new_status}",
            "description": (payload or {}).get("note"),
            "created_by": current_user.id,
            "created_at": _now(),
        }
    )
    await create_audit_log(current_user.tenant_id, current_user, "sales_lead_stage_changed", "sales_lead", lead_id, {"status": new_status})
    return {"success": True, "lead_id": lead_id, "status": new_status}


@router.delete("/sales/leads/{lead_id}")
async def delete_lead(
    lead_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """Lead'i geri getirilebilir şekilde arşivle; satış denetim izi korunur."""
    res = await db.mice_opportunities.update_one(
        _active_lead_query(current_user.tenant_id, id=lead_id),
        {"$set": {"deleted_at": _now(), "deleted_by": current_user.id, "updated_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lead bulunamadı")
    await create_audit_log(current_user.tenant_id, current_user, "sales_lead_archived", "sales_lead", lead_id)
    return {"success": True, "lead_id": lead_id, "archived": True}


@router.post("/sales/activity")
async def log_sales_activity(
    activity_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """Satis aktivitesi kaydet"""
    a_type = activity_data.get("activity_type")
    if a_type not in ACTIVITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Geçersiz aktivite tipi: {a_type}")
    if not activity_data.get("lead_id") or not activity_data.get("subject"):
        raise HTTPException(status_code=400, detail="lead_id ve subject zorunlu")
    # Lead'in bu tenant'a ait olduğunu doğrula.
    owns = await db.mice_opportunities.count_documents(_active_lead_query(current_user.tenant_id, id=activity_data["lead_id"]))
    if owns == 0:
        raise HTTPException(status_code=404, detail="Lead bulunamadı")
    activity = {
        "_kind": ACTIVITY_KIND,
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "lead_id": activity_data["lead_id"],
        "activity_type": a_type,
        "subject": activity_data["subject"],
        "description": activity_data.get("description"),
        "follow_up_at": _follow_up_iso(activity_data.get("follow_up_at")),
        "created_by": current_user.id,
        "created_at": _now(),
    }
    await db.mice_opportunity_activities.insert_one(activity)
    await db.mice_opportunities.update_one(
        {
            "_kind": LEAD_KIND,
            "id": activity_data["lead_id"],
            "tenant_id": current_user.tenant_id,
        },
        {"$set": {"last_contacted_at": _now(), "updated_at": _now()}},
    )
    await create_audit_log(current_user.tenant_id, current_user, "sales_lead_activity_logged", "sales_lead", activity_data["lead_id"], {"activity_type": a_type, "follow_up_at": activity["follow_up_at"]})
    return {"success": True, "message": "Aktivite kaydedildi", "activity_id": activity["id"]}


@router.post("/sales/activity/{activity_id}/complete")
async def complete_sales_follow_up(
    activity_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """Mark one scheduled sales follow-up complete without deleting its audit trail."""
    completed_at = _now()
    result = await db.mice_opportunity_activities.update_one(
        _open_follow_up_query(current_user.tenant_id, activity_id),
        {"$set": {"follow_up_completed_at": completed_at, "follow_up_completed_by": current_user.id}},
    )
    if result.matched_count:
        activity = await db.mice_opportunity_activities.find_one(
            {"_kind": ACTIVITY_KIND, "tenant_id": current_user.tenant_id, "id": activity_id},
            {"_id": 0, "lead_id": 1},
        )
        # The update selector and tenant scope guarantee a document exists;
        # retain the defensive branch for adapters with eventual reads.
        lead_id = activity.get("lead_id") if activity else None
        await create_audit_log(
            current_user.tenant_id,
            current_user,
            "sales_follow_up_completed",
            "sales_activity",
            activity_id,
            {"lead_id": lead_id},
        )
        return {"success": True, "activity_id": activity_id, "completed_at": completed_at, "idempotent": False}

    # Two operators can complete the same task together. The second request
    # is a safe replay, not an error, but a non-follow-up/foreign ID remains
    # invisible or invalid.
    activity = await db.mice_opportunity_activities.find_one(
        {"_kind": ACTIVITY_KIND, "tenant_id": current_user.tenant_id, "id": activity_id},
        {"_id": 0, "follow_up_at": 1, "follow_up_completed_at": 1},
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Takip kaydı bulunamadı")
    if activity.get("follow_up_completed_at"):
        return {
            "success": True,
            "activity_id": activity_id,
            "completed_at": activity["follow_up_completed_at"],
            "idempotent": True,
        }
    raise HTTPException(status_code=409, detail="Bu aktivite için planlanmış açık takip yok")


@router.get("/sales/attention")
async def get_sales_attention(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),
):
    """Open sales follow-ups, separated into overdue and upcoming without fake counts."""
    active_leads = await db.mice_opportunities.find(
        _active_lead_query(current_user.tenant_id, status={"$nin": ["won", "lost"]}),
        {"_id": 0, "id": 1, "contact_name": 1, "company_name": 1, "status": 1},
    ).to_list(500)
    lead_by_id = {lead["id"]: lead for lead in active_leads}
    if not lead_by_id:
        return {"overdue": [], "upcoming": [], "data_available": False}
    follow_up_query = _open_follow_up_query(current_user.tenant_id)
    follow_up_query["lead_id"] = {"$in": list(lead_by_id)}
    rows = await db.mice_opportunity_activities.find(
        follow_up_query,
        {"_id": 0, "id": 1, "lead_id": 1, "subject": 1, "activity_type": 1, "follow_up_at": 1},
    ).sort("follow_up_at", 1).to_list(500)
    now = datetime.now(UTC)
    overdue, upcoming = [], []
    for row in rows:
        try:
            due = datetime.fromisoformat(str(row["follow_up_at"]).replace("Z", "+00:00"))
            if due.tzinfo is None:
                due = due.replace(tzinfo=UTC)
        except (KeyError, TypeError, ValueError):
            continue
        item = {**row, "lead": lead_by_id[row["lead_id"]]}
        (overdue if due < now else upcoming).append(item)
    return {"overdue": overdue[:50], "upcoming": upcoming[:50], "data_available": bool(rows)}


# ── Marketing Automation ────────────────────────────────────────────


@router.post("/marketing/campaigns")
async def create_campaign(
    campaign_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """Pazarlama kampanyasi olustur"""
    campaign = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "name": campaign_data["name"],
        "subject": campaign_data["subject"],
        "message": campaign_data["message"],
        "segment": campaign_data.get("segment", "all"),
        "status": "draft",
        "sent_count": 0,
        "created_by": current_user.id,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.marketing_campaigns.insert_one(campaign)
    return {"success": True, "message": "Kampanya olusturuldu", "campaign_id": campaign["id"]}


@router.get("/marketing/segments")
async def get_customer_segments(current_user: User = Depends(get_current_user)):
    """Musteri segmentleri"""
    vip_count = await db.guests.count_documents({"tenant_id": current_user.tenant_id, "tags": "vip"})
    total = await db.guests.count_documents({"tenant_id": current_user.tenant_id})
    return {"segments": [{"name": "VIP", "count": vip_count}, {"name": "All", "count": total}]}


# ── Service Recovery ────────────────────────────────────────────────


@router.post("/service/complaints")
async def create_complaint(
    complaint_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """Şikayet kaydı oluştur"""
    allowed_fields = {
        "booking_id",
        "guest_id",
        "guest_name",
        "room_id",
        "room_number",
        "room_type",
        "category",
        "severity",
        "subject",
        "description",
        "assigned_department",
        "assigned_to",
    }
    safe_data = {k: v for k, v in complaint_data.items() if k in allowed_fields}
    now = datetime.now(UTC).isoformat()
    actor_name = getattr(current_user, "full_name", None) or getattr(current_user, "username", None) or current_user.email
    complaint = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **safe_data,
        "status": "open",
        "created_by": current_user.id,
        "created_at": now,
        "updated_at": now,
        "history": [
            {
                "action": "created",
                "actor_id": current_user.id,
                "actor_name": actor_name,
                "at": now,
            }
        ],
    }
    await db.service_complaints.insert_one(complaint)
    return {"success": True, "message": "Şikayet kaydedildi", "complaint_id": complaint["id"]}


# NOT: Spa & Wellness uçları (/spa/appointments POST+GET) kaldırıldı.
# Tam sürüm domains/spa/router.py'de; çakışma riski sebebiyle stub'lar burada
# tutulmuyor. Frontend zaten gerçek modülü çağırıyor (services/therapists/
# rooms/appointments CRUD + status update + delete + daily-summary).


# NOT: /events/bookings uçları kaldırıldı.
# MICE etkinlik yönetimi için backend/routers/mice.py kullanılır
# (mice_events koleksiyonu, /api/mice/events* uçları).
