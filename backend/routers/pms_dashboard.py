"""
PMS Dashboard Router — Extracted from routers/pms.py (Stage 2 decomposition)
Dashboard overview, operational alerts, room alternatives.
"""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

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

    # Fallback: Ultra-fast aggregation — exclude virtual rooms
    pipeline = [
        {'$match': {
            'tenant_id': current_user.tenant_id,
            '$or': [{'is_virtual': False}, {'is_virtual': {'$exists': False}}],
        }},
        {'$group': {
            '_id': None,
            'total_rooms': {'$sum': 1},
            'occupied_rooms': {'$sum': {'$cond': [{'$eq': ['$status', 'occupied']}, 1, 0]}}
        }}
    ]

    room_stats = await db.rooms.aggregate(pipeline).to_list(1)
    total_rooms = room_stats[0]['total_rooms'] if room_stats else 0
    physically_occupied = room_stats[0]['occupied_rooms'] if room_stats else 0

    # Count bookings overlapping today (confirmed + checked_in + guaranteed)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    booking_occupied = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
        'check_in': {'$lte': today + 'T23:59:59'},
        'check_out': {'$gt': today}
    })

    # Use the higher of physical room status or booking count
    occupied_rooms = max(physically_occupied, booking_occupied)

    # Today's check-ins
    today_checkins = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
        'check_in': {'$regex': f'^{today}'}
    })

    # Total active guests
    total_guests = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
        'check_in': {'$lte': today + 'T23:59:59'},
        'check_out': {'$gte': today}
    })

    # Ultra-fast response
    result = {
        'total_rooms': total_rooms,
        'occupied_rooms': occupied_rooms,
        'available_rooms': max(0, total_rooms - occupied_rooms),
        'occupancy_rate': round((occupied_rooms / total_rooms * 100), 2) if total_rooms > 0 else 0,
        'today_checkins': today_checkins,
        'total_guests': total_guests
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
    today = datetime.now(UTC).strftime("%Y-%m-%d")
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
    active_statuses = ["confirmed", "guaranteed", "checked_in"]
    departures_today = await db.bookings.count_documents(
        {"tenant_id": tenant_id, "status": {"$in": active_statuses}, "check_out": {"$regex": f"^{today}"}}
    )
    inhouse_count = await db.bookings.count_documents(
        {"tenant_id": tenant_id, "status": {"$in": active_statuses},
         "check_in": {"$lte": today + "T23:59:59"},
         "check_out": {"$gt": today}}
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


NO_SHOW_REASON_LABELS = {
    "misafir_gelmedi": "Misafir Gelmedi",
    "iptal_gec_islendi": "Iptal Gec Islendi",
    "overbooking": "Overbooking",
}


@router.get("/pms/no-show-analytics")
async def get_no_show_analytics(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
):
    """No-show analytics: daily counts, by room type, by channel."""
    tenant_id = current_user.tenant_id
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    no_shows = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": "no_show",
            "no_show_at": {"$gte": cutoff},
        },
        {
            "_id": 0,
            "id": 1,
            "no_show_at": 1,
            "no_show_reason": 1,
            "room_type": 1,
            "source_channel": 1,
            "channel": 1,
            "total_amount": 1,
            "guest_name": 1,
        },
    ).to_list(5000)

    # --- Daily counts ---
    daily_map: dict[str, int] = {}
    for b in no_shows:
        day = (b.get("no_show_at") or "")[:10]
        if day:
            daily_map[day] = daily_map.get(day, 0) + 1
    daily = [{"date": d, "count": c} for d, c in sorted(daily_map.items())]

    # --- By room type ---
    rt_map: dict[str, dict] = {}
    for b in no_shows:
        rt = b.get("room_type") or "Bilinmiyor"
        if rt not in rt_map:
            rt_map[rt] = {"room_type": rt, "count": 0, "revenue_loss": 0}
        rt_map[rt]["count"] += 1
        rt_map[rt]["revenue_loss"] += b.get("total_amount") or 0
    by_room_type = sorted(rt_map.values(), key=lambda x: -x["count"])

    # --- By channel ---
    ch_map: dict[str, dict] = {}
    for b in no_shows:
        ch = b.get("source_channel") or b.get("channel") or "direct"
        if ch not in ch_map:
            ch_map[ch] = {"channel": ch, "count": 0, "revenue_loss": 0}
        ch_map[ch]["count"] += 1
        ch_map[ch]["revenue_loss"] += b.get("total_amount") or 0
    by_channel = sorted(ch_map.values(), key=lambda x: -x["count"])

    # --- By reason ---
    reason_map: dict[str, int] = {}
    for b in no_shows:
        reason = b.get("no_show_reason") or "belirtilmemis"
        reason_map[reason] = reason_map.get(reason, 0) + 1
    by_reason = [
        {"reason": r, "label": NO_SHOW_REASON_LABELS.get(r, r), "count": c}
        for r, c in sorted(reason_map.items(), key=lambda x: -x[1])
    ]

    total_revenue_loss = sum(b.get("total_amount") or 0 for b in no_shows)

    # Recent no-shows (last 10)
    recent = sorted(no_shows, key=lambda x: x.get("no_show_at", ""), reverse=True)[:10]
    recent_list = [
        {
            "id": b.get("id"),
            "guest_name": b.get("guest_name") or "Bilinmiyor",
            "room_type": b.get("room_type") or "-",
            "channel": b.get("source_channel") or b.get("channel") or "direct",
            "reason": b.get("no_show_reason") or "belirtilmemis",
            "reason_label": NO_SHOW_REASON_LABELS.get(b.get("no_show_reason", ""), b.get("no_show_reason") or "Belirtilmemis"),
            "amount": b.get("total_amount") or 0,
            "date": (b.get("no_show_at") or "")[:10],
        }
        for b in recent
    ]

    return {
        "total_no_shows": len(no_shows),
        "total_revenue_loss": round(total_revenue_loss, 2),
        "period_days": days,
        "daily": daily,
        "by_room_type": by_room_type,
        "by_channel": by_channel,
        "by_reason": by_reason,
        "recent": recent_list,
    }
