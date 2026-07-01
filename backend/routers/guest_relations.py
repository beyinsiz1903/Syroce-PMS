"""Guest Relations Smart Profile Entegrasyonu.

Provides predictive analysis of guest preferences (pillow type, SPA choices, minibar habits)
and automates the generation of Room Preparation Directives (housekeeping task + frontdesk alerts)
24 hours prior to guest arrival.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/guest-relations", tags=["Guest Relations Smart Engine"])


class GuestAnalysisResponse(BaseModel):
    guest_id: str
    guest_name: str
    pillow_preference: str
    spa_preference: str
    minibar_preference: str


async def _analyze_guest_preferences(db: Any, tenant_id: str, guest_id: str, guest_name: str) -> dict[str, str]:
    # 1. Pillow preference
    guest = await db.guests.find_one({"id": guest_id, "tenant_id": tenant_id})
    pillow = "Standart (Ortopedik)"
    if guest and guest.get("pillow_preference"):
        pillow = guest["pillow_preference"]
    else:
        # Fallback: scan past bookings for this guest
        past_booking = await db.bookings.find_one({"guest_id": guest_id, "tenant_id": tenant_id, "pillow_type": {"$ne": None}})
        if past_booking and past_booking.get("pillow_type"):
            pillow = past_booking["pillow_type"]

    # 2. SPA preferences (guest_id-specific with guest_name fallback)
    spa_pref = "SPA geçmişi bulunamadı. Genel aroma terapi önerilir."
    spa_appts = await db.spa_appointments.find({"tenant_id": tenant_id, "guest_id": guest_id}).to_list(100)
    if not spa_appts and guest_name:
        spa_appts = await db.spa_appointments.find({"tenant_id": tenant_id, "guest_name": guest_name}).to_list(100)

    if spa_appts:
        services: dict[str, int] = {}
        oils = []
        for appt in spa_appts:
            srv = appt.get("service_name") or "Genel Masaj"
            services[srv] = services.get(srv, 0) + 1
            # Scan therapist notes
            notes = str(appt.get("notes") or "").lower()
            for oil in ["lavanta", "gül", "nane", "kekik", "okaliptüs", "aroma"]:
                if oil in notes:
                    oils.append(oil)

        most_frequent_service = max(services, key=services.get)
        fav_oil = max(set(oils), key=oils.count) if oils else "aroma"
        spa_pref = f"{most_frequent_service} ({fav_oil} yağı tercihi)"

    # 3. Minibar preferences (guest-specific via bookings -> folios -> folio_postings)
    minibar_pref = "Standart minibar kurulumu."
    guest_bookings = await db.bookings.find({"guest_id": guest_id, "tenant_id": tenant_id}, {"_id": 0, "id": 1}).to_list(100)
    booking_ids = [b["id"] for b in guest_bookings if "id" in b]

    postings = []
    if booking_ids:
        guest_folios = await db.folios.find({"booking_id": {"$in": booking_ids}, "tenant_id": tenant_id}, {"_id": 0, "id": 1}).to_list(100)
        folio_ids = [f["id"] for f in guest_folios if "id" in f]
        if folio_ids:
            postings = await db.folio_postings.find(
                {"folio_id": {"$in": folio_ids}, "tenant_id": tenant_id, "description": {"$regex": "Minibar", "$options": "i"}}
            ).to_list(200)

    if postings:
        counts = {"Soda": 0, "Bira": 0, "Kola": 0, "Çikolata": 0, "Su": 0}
        for p in postings:
            desc = str(p.get("description") or "")
            for k in counts:
                if k.lower() in desc.lower():
                    counts[k] += 1

        dominant = max(counts, key=counts.get)
        if counts[dominant] > 0:
            minibar_pref = f"{dominant} ağırlıklı minibar kurulumu."

    return {"pillow_preference": pillow, "spa_preference": spa_pref, "minibar_preference": minibar_pref}


@router.get("/profiles/{guest_id}/analysis", response_model=GuestAnalysisResponse)
async def get_guest_profile_analysis(
    guest_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_guest_list")),
):
    """Retrieve historical preference analysis for a guest."""
    tenant_id = current_user.tenant_id

    guest = await db.guests.find_one({"id": guest_id, "tenant_id": tenant_id})
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")

    pref = await _analyze_guest_preferences(db, tenant_id, guest_id, guest["name"])
    return {"guest_id": guest_id, "guest_name": guest["name"], **pref}


@router.get("/preparations/directives")
async def list_preparation_directives(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_guest_list")),
):
    """List generated guest room preparation directives."""
    directives = await db.guest_prep_directives.find({"tenant_id": current_user.tenant_id}).sort("created_at", -1).to_list(200)
    return {"directives": directives}


@router.post("/preparations/trigger")
async def trigger_room_preparations(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_guests")),
):
    """Find tomorrow's arrivals, generate prep directives, and issue automated tasks."""
    tenant_id = current_user.tenant_id

    now = datetime.now(UTC)
    tomorrow_start = now + timedelta(hours=12)
    tomorrow_end = now + timedelta(hours=36)

    # Find bookings arriving tomorrow
    # Query check_in timestamp range (supports ISO string)
    bookings = await db.bookings.find({"tenant_id": tenant_id, "status": {"$in": ["confirmed", "checked_in", "in_house"]}}).to_list(1000)

    tomorrow_bookings = []
    for b in bookings:
        try:
            ci = datetime.fromisoformat(b["check_in"].replace("Z", "+00:00"))
            if tomorrow_start <= ci <= tomorrow_end:
                tomorrow_bookings.append(b)
        except Exception:
            # Fallback for simple date strings
            if b["check_in"] == (now + timedelta(days=1)).strftime("%Y-%m-%d"):
                tomorrow_bookings.append(b)

    generated_count = 0
    for booking in tomorrow_bookings:
        guest_id = booking.get("guest_id")
        guest_name = booking.get("guest_name") or "Misafir"
        if not guest_id:
            continue

        # Check if directive already exists
        existing = await db.guest_prep_directives.find_one({"booking_id": booking["id"], "tenant_id": tenant_id})
        if existing:
            continue

        # Run preference analysis
        pref = await _analyze_guest_preferences(db, tenant_id, guest_id, guest_name)

        directive_id = str(uuid.uuid4())
        directive_doc = {
            "id": directive_id,
            "tenant_id": tenant_id,
            "booking_id": booking["id"],
            "guest_id": guest_id,
            "guest_name": guest_name,
            "room_id": booking.get("room_id"),
            "check_in": booking["check_in"],
            "created_at": datetime.now(UTC).isoformat(),
            **pref,
        }
        await db.guest_prep_directives.insert_one(directive_doc)

        # Create Automated Housekeeping Task
        hk_task_id = str(uuid.uuid4())
        hk_task = {
            "id": hk_task_id,
            "tenant_id": tenant_id,
            "room_id": booking.get("room_id"),
            "task_type": "special_setup",
            "description": (f"Misafir Odası Hazırlık Direktifi: Yastık Tercihi: {pref['pillow_preference']}, Minibar Alışkanlığı: {pref['minibar_preference']}, SPA Tercihi: {pref['spa_preference']}"),
            "priority": "medium",
            "status": "pending",
            "assigned_to": "Housekeeping",
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.housekeeping_tasks.insert_one(hk_task)

        # Update Booking Special Requests for Front Desk visibility
        existing_requests = booking.get("special_requests") or ""
        directive_alert = f"[MİSAFİR İLİŞKİLERİ DİREKTİFİ] Yastık: {pref['pillow_preference']}, Minibar: {pref['minibar_preference']}, SPA: {pref['spa_preference']}"
        new_requests = f"{existing_requests}\n{directive_alert}".strip()
        await db.bookings.update_one({"id": booking["id"], "tenant_id": tenant_id}, {"$set": {"special_requests": new_requests}})

        generated_count += 1

    return {"success": True, "processed_bookings": len(tomorrow_bookings), "directives_generated": generated_count}
