"""
PMS Dashboard Router — Extracted from routers/pms.py (Stage 2 decomposition)
Dashboard overview, operational alerts, room alternatives.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from core.database import db
from core.security import get_current_user
from models.schemas import User

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

router = APIRouter(prefix="/api", tags=["pms"])


@router.get("/pms/dashboard")
@cached(ttl=30, key_prefix="pms_dashboard")  # Cache for 30 seconds - very fast refresh
async def get_pms_dashboard(current_user: User = Depends(get_current_user)):
    # Try Redis cache first (FASTEST!)
    try:
        from redis_cache import redis_cache
        if redis_cache:
            cache_key = f"dashboard:{current_user.tenant_id}"
            cached = redis_cache.get(cache_key)
            if cached:
                return cached
    except Exception:
        pass

    # Check pre-warmed cache second
    from cache_warmer import cache_warmer
    if cache_warmer:
        cached_data = cache_warmer.get_cached(f"dashboard:{current_user.tenant_id}")
        if cached_data:
            return cached_data

    # Fallback: Ultra-fast aggregation
    pipeline = [
        {'$match': {'tenant_id': current_user.tenant_id}},
        {'$group': {
            '_id': None,
            'total_rooms': {'$sum': 1},
            'occupied_rooms': {'$sum': {'$cond': [{'$eq': ['$status', 'occupied']}, 1, 0]}}
        }}
    ]

    room_stats = await db.rooms.aggregate(pipeline).to_list(1)
    total_rooms = room_stats[0]['total_rooms'] if room_stats else 0
    occupied_rooms = room_stats[0]['occupied_rooms'] if room_stats else 0

    # Ultra-fast response - minimal queries
    result = {
        'total_rooms': total_rooms,
        'occupied_rooms': occupied_rooms,
        'available_rooms': total_rooms - occupied_rooms,
        'occupancy_rate': round((occupied_rooms / total_rooms * 100), 2) if total_rooms > 0 else 0,
        'today_checkins': 0,  # Skip for max speed
        'total_guests': 0  # Skip for max speed
    }

    # Cache in Redis for 5 seconds
    try:
        from redis_cache import redis_cache
        if redis_cache:
            cache_key = f"dashboard:{current_user.tenant_id}"
            redis_cache.set(cache_key, result, ttl=5)
    except Exception:
        pass

    return result


@router.get("/pms/operational-alerts")
async def get_operational_alerts(current_user: User = Depends(get_current_user)):
    """Decision-driven operational intelligence: what needs attention NOW."""
    tenant_id = current_user.tenant_id
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    alerts = []

    # 1) Dirty rooms blocking check-ins
    dirty_rooms = await db.rooms.find(
        {"tenant_id": tenant_id, "status": {"$in": ["dirty", "cleaning"]}},
        {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "floor": 1, "status": 1}
    ).to_list(200)

    arrivals_today = await db.bookings.find(
        {"tenant_id": tenant_id, "status": {"$in": ["confirmed", "guaranteed"]},
         "check_in": {"$regex": f"^{today}"}},
        {"_id": 0, "id": 1, "guest_name": 1, "room_number": 1, "room_id": 1}
    ).to_list(200)

    dirty_room_numbers = {str(r["room_number"]) for r in dirty_rooms}
    blocked_checkins = []
    for arr in arrivals_today:
        rn = str(arr.get("room_number", ""))
        if rn in dirty_room_numbers:
            blocked_checkins.append({
                "booking_id": arr["id"],
                "guest_name": arr.get("guest_name", "Misafir"),
                "room_number": rn,
                "reason": "dirty"
            })

    if blocked_checkins:
        alerts.append({
            "type": "dirty_rooms_blocking",
            "severity": "high",
            "title": f"{len(blocked_checkins)} oda hazir degil",
            "description": "Check-in bekleyen misafirlerin odalari henuz temizlenmedi",
            "count": len(blocked_checkins),
            "items": blocked_checkins[:5],
            "action": "housekeeping",
            "action_label": "Kat Hizmetlerine Git"
        })

    # 2) Pending payments (balance > 0 for checked-in guests)
    unpaid = await db.bookings.find(
        {"tenant_id": tenant_id, "status": "checked_in",
         "$expr": {"$gt": [{"$subtract": [{"$ifNull": ["$total_amount", 0]}, {"$ifNull": ["$paid_amount", 0]}]}, 0.01]}},
        {"_id": 0, "id": 1, "guest_name": 1, "room_number": 1, "total_amount": 1, "paid_amount": 1}
    ).to_list(200)

    pending_payments = []
    total_outstanding = 0
    for b in unpaid:
        balance = round((b.get("total_amount", 0) or 0) - (b.get("paid_amount", 0) or 0), 2)
        if balance > 0.01:
            total_outstanding += balance
            pending_payments.append({
                "booking_id": b["id"],
                "guest_name": b.get("guest_name", "Misafir"),
                "room_number": str(b.get("room_number", "")),
                "balance": balance
            })

    if pending_payments:
        alerts.append({
            "type": "pending_payments",
            "severity": "medium",
            "title": f"{len(pending_payments)} odenmemis hesap",
            "description": f"Toplam {total_outstanding:,.2f} TL tahsil edilmedi",
            "count": len(pending_payments),
            "total_amount": round(total_outstanding, 2),
            "items": sorted(pending_payments, key=lambda x: -x["balance"])[:5],
            "action": "payments",
            "action_label": "Odemelere Git"
        })

    # 3) VIP arrivals today
    vip_arrivals = []
    for arr in arrivals_today:
        guest_id = arr.get("guest_id")
        if guest_id:
            guest = await db.guests.find_one(
                {"id": guest_id, "tenant_id": tenant_id},
                {"_id": 0, "name": 1, "vip_status": 1, "total_stays": 1, "preferences": 1}
            )
            if guest and guest.get("vip_status"):
                vip_arrivals.append({
                    "booking_id": arr["id"],
                    "guest_name": guest.get("name", arr.get("guest_name", "VIP")),
                    "room_number": str(arr.get("room_number", "")),
                    "total_stays": guest.get("total_stays", 0),
                    "preferences": guest.get("preferences", {})
                })

    if vip_arrivals:
        alerts.append({
            "type": "vip_arrivals",
            "severity": "info",
            "title": f"{len(vip_arrivals)} VIP gelis",
            "description": "Bugun VIP misafir gelisi bekleniyor",
            "count": len(vip_arrivals),
            "items": vip_arrivals[:5],
            "action": "frontdesk",
            "action_label": "Resepsiyona Git"
        })

    # 4) Today's departures with balance
    departures_with_balance = await db.bookings.find(
        {"tenant_id": tenant_id, "status": "checked_in",
         "check_out": {"$regex": f"^{today}"},
         "$expr": {"$gt": [{"$subtract": [{"$ifNull": ["$total_amount", 0]}, {"$ifNull": ["$paid_amount", 0]}]}, 0.01]}},
        {"_id": 0, "id": 1, "guest_name": 1, "room_number": 1, "total_amount": 1, "paid_amount": 1}
    ).to_list(200)

    if departures_with_balance:
        dep_items = []
        for d in departures_with_balance:
            bal = round((d.get("total_amount", 0) or 0) - (d.get("paid_amount", 0) or 0), 2)
            dep_items.append({
                "booking_id": d["id"],
                "guest_name": d.get("guest_name", "Misafir"),
                "room_number": str(d.get("room_number", "")),
                "balance": bal
            })
        alerts.append({
            "type": "departures_with_balance",
            "severity": "high",
            "title": f"{len(dep_items)} cikis bakiyeli",
            "description": "Bugun cikis yapacak misafirlerin acik bakiyesi var",
            "count": len(dep_items),
            "items": dep_items[:5],
            "action": "frontdesk",
            "action_label": "Cikislara Git"
        })

    # 5) Summary stats
    all_arrivals_count = len(arrivals_today)
    departures_today = await db.bookings.count_documents(
        {"tenant_id": tenant_id, "status": "checked_in", "check_out": {"$regex": f"^{today}"}}
    )
    inhouse_count = await db.bookings.count_documents(
        {"tenant_id": tenant_id, "status": "checked_in"}
    )
    dirty_count = len(dirty_rooms)

    # 6) Alternative rooms for dirty room situations
    available_clean = await db.rooms.find(
        {"tenant_id": tenant_id, "status": "available"},
        {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "floor": 1}
    ).to_list(50)

    return {
        "alerts": alerts,
        "summary": {
            "arrivals_today": all_arrivals_count,
            "departures_today": departures_today,
            "inhouse": inhouse_count,
            "dirty_rooms": dirty_count,
            "pending_payments_count": len(pending_payments),
            "vip_arrivals": len(vip_arrivals),
            "total_outstanding": round(total_outstanding, 2)
        },
        "available_clean_rooms": available_clean[:20]
    }


@router.get("/pms/room-alternatives/{room_number}")
async def get_room_alternatives(room_number: str, current_user: User = Depends(get_current_user)):
    """Get alternative clean rooms of same type for a dirty room."""
    tenant_id = current_user.tenant_id
    target_room = await db.rooms.find_one(
        {"tenant_id": tenant_id, "room_number": room_number},
        {"_id": 0, "room_type": 1, "floor": 1, "capacity": 1}
    )
    if not target_room:
        return {"alternatives": []}

    alternatives = await db.rooms.find(
        {"tenant_id": tenant_id, "status": "available",
         "room_type": target_room.get("room_type")},
        {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "floor": 1, "capacity": 1, "view": 1}
    ).to_list(10)

    # Also get same-type rooms that are clean but different type
    other_alternatives = await db.rooms.find(
        {"tenant_id": tenant_id, "status": "available",
         "room_type": {"$ne": target_room.get("room_type")}},
        {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "floor": 1, "capacity": 1, "view": 1}
    ).to_list(5)

    return {
        "target_room_type": target_room.get("room_type"),
        "same_type": alternatives,
        "other_type": other_alternatives
    }
