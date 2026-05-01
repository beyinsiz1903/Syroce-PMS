"""
Domain Router: Sales CRM, Marketing & Service Recovery

Extracted from legacy_routes.py — leads, funnel, activities,
campaigns, segments, complaints, spa, events.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_module as require_module_v97  # v97 DW
from modules.pms_core.role_permission_service import require_op  # v98 DW

router = APIRouter(prefix="/api", tags=["sales-crm-domain"])

# Geçerli lead aşamaları (frontend ile uyumlu 7'li huni).
LEAD_STAGES = {
    "new", "contacted", "qualified", "proposal_sent",
    "negotiating", "won", "lost",
}
# Geçerli aktivite tipleri.
ACTIVITY_TYPES = {"call", "email", "meeting", "note", "task"}

# Atlas 500 koleksiyon limiti dolu olduğundan, sales_leads/sales_activities
# yerine boş duran mice_opportunities/mice_opportunity_activities
# koleksiyonları yeniden kullanılır. _kind ayraç alanı ile MICE
# opportunity kayıtlarından (sales_catering.py) ayrılır.
LEAD_KIND = "lead"
ACTIVITY_KIND = "lead_activity"


# ── Sales CRM & Lead Management ────────────────────────────────────

@router.post("/sales/leads")
async def create_lead(
    lead_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """Yeni satis lead'i olustur"""
    contact_name = lead_data.get("contact_name") or lead_data.get("contact_person")
    contact_email = lead_data.get("contact_email") or lead_data.get("email")
    if not contact_name or not contact_email:
        raise HTTPException(status_code=400, detail="contact_name ve contact_email zorunlu")
    lead = {
        "_kind": LEAD_KIND,
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "company_name": lead_data.get("company_name"),
        "contact_name": contact_name,
        "contact_email": contact_email,
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
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    await db.mice_opportunities.insert_one(lead)
    return {"success": True, "message": "Lead basariyla olusturuldu", "lead_id": lead["id"]}


@router.get("/sales/leads")
async def get_leads(
    status: str | None = None,
    q: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # GET'lere de yetki kontrolü
):
    """Lead'leri listele (status filtresi + isim/şirket/e-posta arama)."""
    query: dict = {"_kind": LEAD_KIND, "tenant_id": current_user.tenant_id}
    if status and status in LEAD_STAGES:
        query["status"] = status
    if q:
        rx = {"$regex": q.strip(), "$options": "i"}
        query["$or"] = [
            {"contact_name": rx},
            {"company_name": rx},
            {"contact_email": rx},
        ]
    leads = await db.mice_opportunities.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"leads": leads, "total": len(leads)}


@router.get("/sales/funnel")
async def get_sales_funnel(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # GET'e de yetki kontrolü
):
    """Satis hunisi metrikleri — tek aggregation ile (eski 7 sorgu yerine)."""
    pipeline = [
        {"$match": {"_kind": LEAD_KIND, "tenant_id": current_user.tenant_id}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    rows = await db.mice_opportunities.aggregate(pipeline).to_list(50)
    funnel = {s: 0 for s in [
        "new", "contacted", "qualified", "proposal_sent",
        "negotiating", "won", "lost",
    ]}
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
    lead = await db.mice_opportunities.find_one(
        {"_kind": LEAD_KIND, "id": lead_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Lead bulunamadı")
    activities = await db.mice_opportunity_activities.find(
        {"_kind": ACTIVITY_KIND, "tenant_id": current_user.tenant_id, "lead_id": lead_id},
        {"_id": 0},
    ).sort("created_at", -1).to_list(50)
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
        {"_kind": LEAD_KIND, "id": lead_id, "tenant_id": current_user.tenant_id},
        {"$set": {
            "status": new_status,
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": current_user.id,
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lead bulunamadı")
    # Aşama değişimini aktivite olarak da kaydet (denetim izi).
    await db.mice_opportunity_activities.insert_one({
        "_kind": ACTIVITY_KIND,
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "lead_id": lead_id,
        "activity_type": "stage_change",
        "subject": f"Aşama: {new_status}",
        "description": (payload or {}).get("note"),
        "created_by": current_user.id,
        "created_at": datetime.now(UTC).isoformat(),
    })
    return {"success": True, "lead_id": lead_id, "status": new_status}


@router.delete("/sales/leads/{lead_id}")
async def delete_lead(
    lead_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """Lead sil (ve bağlı aktiviteleri)."""
    res = await db.mice_opportunities.delete_one(
        {"_kind": LEAD_KIND, "id": lead_id, "tenant_id": current_user.tenant_id}
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Lead bulunamadı")
    await db.mice_opportunity_activities.delete_many(
        {"_kind": ACTIVITY_KIND, "tenant_id": current_user.tenant_id, "lead_id": lead_id}
    )
    return {"success": True, "lead_id": lead_id}


@router.post("/sales/activity")
async def log_sales_activity(
    activity_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """Satis aktivitesi kaydet"""
    a_type = activity_data.get("activity_type")
    if a_type not in ACTIVITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Geçersiz aktivite tipi: {a_type}")
    if not activity_data.get("lead_id") or not activity_data.get("subject"):
        raise HTTPException(status_code=400, detail="lead_id ve subject zorunlu")
    # Lead'in bu tenant'a ait olduğunu doğrula.
    owns = await db.mice_opportunities.count_documents(
        {"_kind": LEAD_KIND, "id": activity_data["lead_id"], "tenant_id": current_user.tenant_id}
    )
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
        "follow_up_at": activity_data.get("follow_up_at"),
        "created_by": current_user.id,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.mice_opportunity_activities.insert_one(activity)
    await db.mice_opportunities.update_one(
        {
            "_kind": LEAD_KIND,
            "id": activity_data["lead_id"],
            "tenant_id": current_user.tenant_id,
        },
        {"$set": {"last_contacted_at": datetime.now(UTC).isoformat()}},
    )
    return {"success": True, "message": "Aktivite kaydedildi", "activity_id": activity["id"]}


# ── Marketing Automation ────────────────────────────────────────────

@router.post("/marketing/campaigns")
async def create_campaign(
    campaign_data: dict, current_user: User = Depends(get_current_user),
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
    complaint_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """Şikayet kaydı oluştur"""
    allowed_fields = {
        "booking_id", "guest_id", "guest_name", "room_id", "room_number",
        "room_type", "category", "severity", "subject", "description",
        "assigned_department", "assigned_to",
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
        "history": [{
            "action": "created",
            "actor_id": current_user.id,
            "actor_name": actor_name,
            "at": now,
        }],
    }
    await db.service_complaints.insert_one(complaint)
    return {"success": True, "message": "Şikayet kaydedildi", "complaint_id": complaint["id"]}


# ── Spa & Wellness ──────────────────────────────────────────────────

@router.post("/spa/appointments")
async def create_spa_appointment(
    appointment_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    appointment = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **appointment_data,
        "status": "confirmed",
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.spa_appointments.insert_one(appointment)
    return {"success": True, "appointment_id": appointment["id"]}


@router.get("/spa/appointments")
async def get_spa_appointments(current_user: User = Depends(get_current_user)):
    appointments = await db.spa_appointments.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).to_list(100)
    return {"appointments": appointments, "total": len(appointments)}


# NOT: /events/bookings uçları kaldırıldı.
# MICE etkinlik yönetimi için backend/routers/mice.py kullanılır
# (mice_events koleksiyonu, /api/mice/events* uçları).
