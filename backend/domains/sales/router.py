"""
Domain Router: Sales CRM, Marketing & Service Recovery

Extracted from legacy_routes.py — leads, funnel, activities,
campaigns, segments, complaints, spa, events.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_module as require_module_v97  # v97 DW
from modules.pms_core.role_permission_service import require_op  # v98 DW

router = APIRouter(prefix="/api", tags=["sales-crm-domain"])


# ── Sales CRM & Lead Management ────────────────────────────────────

@router.post("/sales/leads")
async def create_lead(
    lead_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """Yeni satis lead'i olustur"""
    lead = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "company_name": lead_data.get("company_name"),
        "contact_name": lead_data.get("contact_name") or lead_data.get("contact_person"),
        "contact_email": lead_data["contact_email"],
        "contact_phone": lead_data.get("contact_phone"),
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
    await db.sales_leads.insert_one(lead)
    return {"success": True, "message": "Lead basariyla olusturuldu", "lead_id": lead["id"]}


@router.get("/sales/leads")
async def get_leads(
    status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Lead'leri listele"""
    query = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status
    leads = await db.sales_leads.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"leads": leads, "total": len(leads)}


@router.get("/sales/funnel")
async def get_sales_funnel(current_user: User = Depends(get_current_user)):
    """Satis hunisi metrikleri"""
    statuses = ["new", "contacted", "qualified", "proposal_sent", "negotiating", "won", "lost"]
    funnel = {}
    for s in statuses:
        count = await db.sales_leads.count_documents(
            {"tenant_id": current_user.tenant_id, "status": s}
        )
        funnel[s] = count
    total = sum(funnel.values())
    return {
        "funnel": funnel,
        "total_leads": total,
        "win_rate": round((funnel["won"] / total * 100) if total > 0 else 0, 2),
    }


@router.post("/sales/activity")
async def log_sales_activity(
    activity_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """Satis aktivitesi kaydet"""
    activity = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "lead_id": activity_data["lead_id"],
        "activity_type": activity_data["activity_type"],
        "subject": activity_data["subject"],
        "description": activity_data.get("description"),
        "created_by": current_user.id,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.sales_activities.insert_one(activity)
    await db.sales_leads.update_one(
        {"id": activity_data["lead_id"]},
        {"$set": {"last_contacted_at": datetime.now(UTC).isoformat()}},
    )
    return {"success": True, "message": "Aktivite kaydedildi"}


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


# ── Meetings & Events ──────────────────────────────────────────────

@router.post("/events/bookings")
async def create_event_booking(
    event_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    event = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **event_data,
        "status": "confirmed",
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.event_bookings.insert_one(event)
    return {"success": True, "event_id": event["id"]}


@router.get("/events/bookings")
async def get_event_bookings(current_user: User = Depends(get_current_user)):
    events = await db.event_bookings.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).to_list(100)
    return {"events": events, "total": len(events)}
