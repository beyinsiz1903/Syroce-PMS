"""
Domain Router: Guest Profile Management

Extracted from legacy_routes.py — VIP protocols, blacklist, celebrations,
enhanced preferences, complete profile, VIP list.
"""
import uuid
from modules.pms_core.role_permission_service import require_op  # v100 DW
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api", tags=["guest-profile-domain"])


# Bug AR (April 2026): server-controlled fields that must NEVER be set from
# client request body via dict spread (`**protocol_data` / `**preferences`).
# Without this filter, a caller can smuggle `guest_id` to attribute their
# action to a different guest (audit trail spoofing), choose a deterministic
# `id` to pre-collide / pre-leak doc identity, or reset `active`/`created_at`.
_RESERVED_DOC_FIELDS = frozenset({
    "id", "_id", "guest_id", "tenant_id",
    "approved_by", "approved_at", "reported_by",
    "active", "created_at", "updated_at",
})


def _strip_reserved(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    return {k: v for k, v in payload.items() if k not in _RESERVED_DOC_FIELDS}


@router.post("/guests/{guest_id}/vip-protocol")
async def create_vip_protocol(
    guest_id: str,
    protocol_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """VIP protokol olustur veya guncelle"""
    protocol_data = _strip_reserved(protocol_data)
    guest = await db.guests.find_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")

    existing = await db.vip_protocols.find_one(
        {"guest_id": guest_id, "tenant_id": current_user.tenant_id}
    )

    if existing:
        await db.vip_protocols.update_one(
            {"guest_id": guest_id, "tenant_id": current_user.tenant_id},
            {"$set": {**protocol_data, "updated_at": datetime.now(UTC).isoformat()}},
        )
        message = "VIP protokol guncellendi"
    else:
        protocol = {
            "id": str(uuid.uuid4()),
            "guest_id": guest_id,
            "tenant_id": current_user.tenant_id,
            **protocol_data,
            "approved_by": current_user.id,
            "approved_at": datetime.now(UTC).isoformat(),
            "active": True,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.vip_protocols.insert_one(protocol)
        message = "VIP protokol olusturuldu"

    current_tags = guest.get("tags", [])
    if "vip" not in current_tags:
        current_tags.append("vip")
        await db.guests.update_one(
            {"id": guest_id}, {"$set": {"tags": current_tags, "vip_status": True}}
        )

    return {"success": True, "message": message, "guest_id": guest_id}


@router.get("/guests/{guest_id}/vip-protocol")
async def get_vip_protocol(
    guest_id: str, current_user: User = Depends(get_current_user)
):
    """VIP protokol detaylarini getir"""
    protocol = await db.vip_protocols.find_one(
        {"guest_id": guest_id, "tenant_id": current_user.tenant_id, "active": True},
        {"_id": 0},
    )
    if not protocol:
        return {"has_protocol": False, "guest_id": guest_id, "message": "VIP protokol bulunamadi"}
    return {"has_protocol": True, "protocol": protocol}


@router.post("/guests/{guest_id}/blacklist")
async def add_to_blacklist(
    guest_id: str,
    entry_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v100 DW
):
    """Misafiri blacklist'e ekle"""
    entry_data = _strip_reserved(entry_data)  # Bug AR — defense in depth (manual extract today, but harden against future ** spread refactors)
    guest = await db.guests.find_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")

    entry = {
        "id": str(uuid.uuid4()),
        "guest_id": guest_id,
        "tenant_id": current_user.tenant_id,
        "reason": entry_data.get("reason"),
        "severity": entry_data.get("severity", "medium"),
        "incident_date": entry_data.get("incident_date", datetime.now(UTC).isoformat()),
        "detailed_notes": entry_data.get("detailed_notes", ""),
        "reported_by": current_user.id,
        "approved_by": entry_data.get("approved_by"),
        "action_taken": entry_data.get("action_taken", "warning"),
        "active": True,
        "permanent": entry_data.get("permanent", False),
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.blacklist_entries.insert_one(entry)

    current_tags = guest.get("tags", [])
    action = entry_data.get("action_taken", "warning")
    if action == "blacklist" and "blacklist" not in current_tags:
        current_tags.append("blacklist")
    if action == "do_not_rent" and "do_not_rent" not in current_tags:
        current_tags.append("do_not_rent")

    await db.guests.update_one(
        {"id": guest_id},
        {"$set": {"tags": current_tags, "blacklist_status": action in ["blacklist", "do_not_rent"]}},
    )

    return {"success": True, "message": f"Misafir {action} listesine eklendi", "entry_id": entry["id"], "action_taken": action}


@router.get("/guests/{guest_id}/blacklist")
async def get_blacklist_history(
    guest_id: str, current_user: User = Depends(get_current_user)
):
    """Misafirin blacklist gecmisi"""
    entries = await db.blacklist_entries.find(
        {"guest_id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)

    return {
        "guest_id": guest_id,
        "entries": entries,
        "total": len(entries),
        "has_active_entry": any(e.get("active", False) for e in entries),
    }


@router.post("/guests/{guest_id}/celebration")
async def update_celebration_tracking(
    guest_id: str,
    celebration_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Kutlama bilgilerini guncelle"""
    celebration_data = _strip_reserved(celebration_data)  # Bug AR (architect follow-up)
    guest = await db.guests.find_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")

    existing = await db.celebration_tracking.find_one(
        {"guest_id": guest_id, "tenant_id": current_user.tenant_id}
    )

    if existing:
        await db.celebration_tracking.update_one(
            {"guest_id": guest_id, "tenant_id": current_user.tenant_id},
            {"$set": {**celebration_data, "updated_at": datetime.now(UTC).isoformat()}},
        )
    else:
        celebration = {
            "guest_id": guest_id,
            "tenant_id": current_user.tenant_id,
            **celebration_data,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        await db.celebration_tracking.insert_one(celebration)

    return {"success": True, "message": "Kutlama bilgileri kaydedildi", "guest_id": guest_id}


@router.get("/guests/{guest_id}/celebration")
async def get_celebration_info(
    guest_id: str, current_user: User = Depends(get_current_user)
):
    """Kutlama bilgilerini getir"""
    celebration = await db.celebration_tracking.find_one(
        {"guest_id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )

    if not celebration:
        return {"has_celebration": False, "guest_id": guest_id}

    upcoming = []
    today = date.today()

    if celebration.get("birthday"):
        bday = celebration["birthday"]
        if isinstance(bday, str):
            bday = datetime.fromisoformat(bday).date()
        this_year_bday = bday.replace(year=today.year)
        days_until = (this_year_bday - today).days
        if 0 <= days_until <= 30:
            upcoming.append({"type": "birthday", "date": this_year_bday.isoformat(), "days_until": days_until})

    if celebration.get("anniversary"):
        anniv = celebration["anniversary"]
        if isinstance(anniv, str):
            anniv = datetime.fromisoformat(anniv).date()
        this_year_anniv = anniv.replace(year=today.year)
        days_until = (this_year_anniv - today).days
        if 0 <= days_until <= 30:
            upcoming.append({"type": "anniversary", "date": this_year_anniv.isoformat(), "days_until": days_until})

    return {"has_celebration": True, "celebration": celebration, "upcoming_celebrations": upcoming}


@router.post("/guests/{guest_id}/enhanced-preferences")
async def update_enhanced_preferences(
    guest_id: str,
    preferences: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Gelismis tercihleri guncelle"""
    preferences = _strip_reserved(preferences)  # Bug AR
    guest = await db.guests.find_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")

    existing = await db.enhanced_guest_preferences.find_one(
        {"guest_id": guest_id, "tenant_id": current_user.tenant_id}
    )

    if existing:
        await db.enhanced_guest_preferences.update_one(
            {"guest_id": guest_id, "tenant_id": current_user.tenant_id},
            {"$set": {**preferences, "updated_at": datetime.now(UTC).isoformat()}},
        )
    else:
        pref_doc = {
            "guest_id": guest_id,
            "tenant_id": current_user.tenant_id,
            **preferences,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        await db.enhanced_guest_preferences.insert_one(pref_doc)

    return {"success": True, "message": "Tercihler basariyla kaydedildi", "guest_id": guest_id}


@router.get("/guests/{guest_id}/complete-profile")
async def get_complete_guest_profile(
    guest_id: str, current_user: User = Depends(get_current_user)
):
    """Misafirin tam profili - tum detaylar"""
    guest = await db.guests.find_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")

    stays = await db.bookings.find(
        {"guest_id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("check_in", -1).to_list(100)

    vip_protocol = await db.vip_protocols.find_one(
        {"guest_id": guest_id, "tenant_id": current_user.tenant_id, "active": True}, {"_id": 0}
    )

    preferences = await db.enhanced_guest_preferences.find_one(
        {"guest_id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )

    celebration = await db.celebration_tracking.find_one(
        {"guest_id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )

    blacklist = await db.blacklist_entries.find(
        {"guest_id": guest_id, "tenant_id": current_user.tenant_id, "active": True}, {"_id": 0}
    ).to_list(10)

    total_spent = sum([s.get("total_amount", 0) for s in stays])
    total_nights = sum([
        (datetime.fromisoformat(s["check_out"].replace("Z", "+00:00")) -
         datetime.fromisoformat(s["check_in"].replace("Z", "+00:00"))).days
        for s in stays if s.get("check_in") and s.get("check_out")
    ])

    spending_profile = {
        "total_stays": len(stays),
        "total_nights": total_nights,
        "total_spent": round(total_spent, 2),
        "avg_spend_per_stay": round(total_spent / len(stays), 2) if len(stays) > 0 else 0,
        "lifetime_value_tier": "vip" if total_spent > 10000 else "high_value" if total_spent > 5000 else "valuable" if total_spent > 2000 else "regular",
    }

    return {
        "guest": guest,
        "stay_history": stays[:10],
        "total_stays": len(stays),
        "vip_protocol": vip_protocol,
        "has_vip_protocol": vip_protocol is not None,
        "enhanced_preferences": preferences,
        "has_preferences": preferences is not None,
        "celebration_tracking": celebration,
        "has_celebrations": celebration is not None,
        "blacklist_entries": blacklist,
        "is_blacklisted": len(blacklist) > 0,
        "spending_profile": spending_profile,
    }


@router.get("/vip/list")
async def get_vip_guests(
    tier: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """VIP misafirleri listele"""
    query = {"tenant_id": current_user.tenant_id, "active": True}
    if tier:
        query["vip_tier"] = tier

    protocols = await db.vip_protocols.find(query, {"_id": 0}).to_list(100)

    enriched = []
    for protocol in protocols:
        # Bug DZ — defense in depth: tenant scope on enrichment lookup
        guest = await db.guests.find_one(
            {"id": protocol["guest_id"], "tenant_id": current_user.tenant_id},
            {"_id": 0, "name": 1, "email": 1, "phone": 1},
        )
        enriched.append({**protocol, "guest": guest})

    return {"vip_guests": enriched, "total": len(enriched)}
