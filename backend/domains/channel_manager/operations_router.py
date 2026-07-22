"""
Channel Manager / Operations Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import (
    get_current_user,
    security,
)
from models.enums import ChannelHealth, ChannelStatus, ChannelType, ParityStatus
from models.schemas import (
    Booking,
    BookingCreate,
    ChannelConnection,
    ExceptionQueue,
    Guest,
    GuestCreate,
    RoomMapping,
    RoomMappingCreate,
    User,
)

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


# v66 Bug DC: Channel Manager RBAC — OTA credentials + price push çok hassas.
# Önceki durum: tüm endpoint'ler sadece get_current_user, hk dahil herkes okuyup yazabiliyordu.
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.role_permission_service import require_role as _require_role

# v66 architect (post-fix): least-privilege — front_desk OTA credentials/parity görmemeli.
# Operational (front_desk OK): durum panoları, ota rezervasyon listesi, exception kuyruğu.
# Sensitive (sadece supervisor+ admin): credentials, mappings, parity rate, performance, sync-history.
_CM_READ_OPERATIONAL = Depends(_require_role("super_admin", "admin", "supervisor", "front_desk"))
_CM_READ_SENSITIVE = Depends(_require_role("super_admin", "admin", "supervisor"))
_CM_WRITE = Depends(_require_role("super_admin", "admin"))


def _redact_connection_secrets(conn: dict) -> dict:
    """v66 architect post-fix: defense-in-depth — credentials hiçbir role'e plaintext dönmesin.
    Yalnızca son 4 karakter görünür; gerçek değer tamamen redacted."""
    if not isinstance(conn, dict):
        return conn
    for field in ("api_key", "api_secret", "api_password", "client_secret", "webhook_secret"):
        v = conn.get(field)
        if v and isinstance(v, str) and len(v) > 0:
            conn[field] = ("***" + v[-4:]) if len(v) >= 4 else "***"
    return conn


class ChannelConnectionCreate(BaseModel):
    channel_name: str
    channel_type: str = "ota"
    api_key: str | None = None
    api_secret: str | None = None
    property_id: str | None = None
    enabled: bool = True
    sync_config: dict[str, Any] | None = None


router = APIRouter(prefix="/api", tags=["Channel Manager / Operations"])


# ── Inline Models ──


class PermissionCheckRequest(BaseModel):
    permission: str


@router.get("/channel-manager/connections", dependencies=[_CM_READ_SENSITIVE])
@cached(ttl=300, key_prefix="cm_connections")  # Cache for 5 min
async def get_channel_connections(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v86 DV: channel config (hassas API anahtarları)
):
    """Get all channel connections (secrets redacted — defense-in-depth)."""
    connections = await db.channel_connections.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(100)
    connections = [_redact_connection_secrets(c) for c in connections]
    return {"connections": connections, "count": len(connections)}


@router.post("/channel-manager/connections", dependencies=[_CM_WRITE])
async def create_channel_connection(
    payload: ChannelConnectionCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Create a new channel connection"""
    connection = ChannelConnection(
        tenant_id=current_user.tenant_id,
        channel_type=payload.channel_type,
        channel_name=payload.channel_name,
        property_id=payload.property_id,
        api_endpoint=payload.api_endpoint,
        api_key=payload.api_key,
        api_secret=payload.api_secret,
        sync_rate_availability=payload.sync_rate_availability,
        sync_reservations=payload.sync_reservations,
        status=ChannelStatus.ACTIVE,
    )

    conn_dict = connection.model_dump()
    conn_dict["created_at"] = conn_dict["created_at"].isoformat()
    await db.channel_connections.insert_one(conn_dict)

    # Log connection creation in channel_sync_logs
    sync_log = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "channel": payload.channel_type,
        "sync_type": "connection",
        "status": "success",
        "duration_ms": 0,
        "records_synced": 0,
        "error_message": None,
        "initiator_type": "hotel_user",
        "initiator_name": current_user.name,
        "initiator_id": current_user.id,
        "ip_address": None,
    }
    await db.channel_sync_logs.insert_one(sync_log)

    return {"message": f"Channel {payload.channel_name} connected successfully", "connection": connection}


@router.get("/channel-manager/room-mappings", dependencies=[_CM_READ_SENSITIVE])
async def get_room_mappings(current_user: User = Depends(get_current_user)):
    mappings = await db.room_mappings.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(200)
    return {"mappings": mappings, "count": len(mappings)}


@router.post("/channel-manager/room-mappings", dependencies=[_CM_WRITE])
async def create_room_mapping(
    mapping: RoomMappingCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    room_mapping = RoomMapping(
        tenant_id=current_user.tenant_id,
        channel_id=mapping.channel_id,
        pms_room_type=mapping.pms_room_type,
        channel_room_type=mapping.channel_room_type,
        channel_room_id=mapping.channel_room_id,
        notes=mapping.notes,
    )
    payload = room_mapping.model_dump()
    payload["created_at"] = payload["created_at"].isoformat()
    await db.room_mappings.insert_one(payload)

    # Log mapping creation
    sync_log = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "channel": room_mapping.channel_id,
        "sync_type": "mapping_create",
        "status": "success",
        "duration_ms": 0,
        "records_synced": 1,
        "error_message": None,
        "initiator_type": "hotel_user",
        "initiator_name": current_user.name,
        "initiator_id": current_user.id,
        "ip_address": None,
    }
    await db.channel_sync_logs.insert_one(sync_log)

    return {"message": "Room mapping created", "mapping": room_mapping}


@router.delete("/channel-manager/room-mappings/{mapping_id}", dependencies=[_CM_WRITE])
async def delete_room_mapping(
    mapping_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    # Fetch mapping for logging context
    mapping = await db.room_mappings.find_one({"id": mapping_id, "tenant_id": current_user.tenant_id})

    result = await db.room_mappings.delete_one({"id": mapping_id, "tenant_id": current_user.tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Room mapping not found")

    # Log mapping deletion
    sync_log = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "channel": mapping.get("channel_id") if mapping else None,
        "sync_type": "mapping_delete",
        "status": "success",
        "duration_ms": 0,
        "records_synced": 0,
        "error_message": None,
        "initiator_type": "hotel_user",
        "initiator_name": current_user.name,
        "initiator_id": current_user.id,
        "ip_address": None,
    }
    await db.channel_sync_logs.insert_one(sync_log)

    return {"message": "Room mapping deleted", "mapping_id": mapping_id}


# rbac-allow: cache-rbac — OTA rezervasyonları operasyonel (FO/manager)
@router.get("/channel-manager/ota-reservations", dependencies=[_CM_READ_OPERATIONAL])
@cached(ttl=180, key_prefix="cm_ota_reservations")  # Cache for 3 min
async def get_ota_reservations(status: str | None = None, channel: ChannelType | None = None, current_user: User = Depends(get_current_user)):
    """Get OTA reservations with filters"""
    query = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status
    if channel:
        query["channel_type"] = channel

    reservations = await db.ota_reservations.find(query, {"_id": 0}).sort("received_at", -1).to_list(100)
    return {"reservations": reservations, "count": len(reservations)}


@router.post("/channel-manager/import-reservation/{ota_reservation_id}", dependencies=[_CM_WRITE])
async def import_ota_reservation(
    ota_reservation_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Import OTA reservation into PMS"""
    ota_res = await db.ota_reservations.find_one({"id": ota_reservation_id, "tenant_id": current_user.tenant_id})

    if not ota_res:
        raise HTTPException(status_code=404, detail="OTA reservation not found")

    if ota_res["status"] == "imported":
        raise HTTPException(status_code=400, detail="Reservation already imported")

    # Find or create guest (dual-read: encrypted _hash_email OR legacy plaintext)
    from security.encrypted_lookup import build_guest_pii_query

    guest = await db.guests.find_one(
        {
            "tenant_id": current_user.tenant_id,
            **build_guest_pii_query("email", ota_res["guest_email"]),
        }
    )

    if not guest:
        # Create new guest
        guest_create = GuestCreate(
            name=ota_res["guest_name"], email=ota_res.get("guest_email") or "noemail@example.com", phone=ota_res.get("guest_phone") or "N/A", id_number="OTA-" + ota_res["channel_booking_id"]
        )
        guest = Guest(tenant_id=current_user.tenant_id, **guest_create.model_dump())
        guest_dict = guest.model_dump()
        guest_dict["created_at"] = guest_dict["created_at"].isoformat()
        from security.guest_write import encrypt_guest_insert

        guest_dict = encrypt_guest_insert(guest_dict)
        await db.guests.insert_one(guest_dict)

    # Find available room of matching type
    rooms = await db.rooms.find({"tenant_id": current_user.tenant_id, "room_type": ota_res["room_type"], "status": "available"}).to_list(10)

    if not rooms:
        # Create exception
        exception = ExceptionQueue(
            tenant_id=current_user.tenant_id,
            exception_type="reservation_import_failed",
            channel_type=ota_res["channel_type"],
            entity_id=ota_reservation_id,
            error_message=f"No available rooms of type {ota_res['room_type']}",
            details={"ota_booking_id": ota_res["channel_booking_id"]},
        )
        exc_dict = exception.model_dump()
        exc_dict["created_at"] = exc_dict["created_at"].isoformat()
        await db.exception_queue.insert_one(exc_dict)

        raise HTTPException(status_code=400, detail=f"No available {ota_res['room_type']} rooms")

    room = rooms[0]

    # Create booking
    booking_create = BookingCreate(
        guest_id=guest["id"],
        room_id=room["id"],
        check_in=ota_res["check_in"],
        check_out=ota_res["check_out"],
        adults=ota_res["adults"],
        children=ota_res["children"],
        guests_count=ota_res["adults"] + ota_res["children"],
        total_amount=ota_res["total_amount"],
        channel=ota_res["channel_type"],
    )

    booking = Booking(
        tenant_id=current_user.tenant_id,
        **booking_create.model_dump(exclude={"check_in", "check_out"}),
        check_in=datetime.fromisoformat(ota_res["check_in"]),
        check_out=datetime.fromisoformat(ota_res["check_out"]),
    )

    booking_dict = booking.model_dump()
    booking_dict["check_in"] = booking_dict["check_in"].isoformat()
    booking_dict["check_out"] = booking_dict["check_out"].isoformat()
    booking_dict["created_at"] = booking_dict["created_at"].isoformat()
    from core.atomic_booking import BookingConflictError, create_booking_atomic

    try:
        await create_booking_atomic(tenant_id=current_user.tenant_id, booking_doc=booking_dict)
    except BookingConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Update OTA reservation status
    await db.ota_reservations.update_one({"id": ota_reservation_id}, {"$set": {"status": "imported", "pms_booking_id": booking.id, "processed_at": datetime.now(UTC).isoformat()}})

    # Log reservation import in channel_sync_logs
    # v109 Bug DAK round-6 (T09 P2): naive XFF allowed audit-log IP spoofing.
    # Use trusted-proxy aware client_ip() helper (rightmost edge-appended hop).
    from security.auth_throttle import client_ip as _client_ip

    ip_address = _client_ip(request)
    sync_log = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "channel": ota_res["channel_type"],
        "sync_type": "reservation_import",
        "status": "success",
        "duration_ms": 0,
        "records_synced": 1,
        "error_message": None,
        "initiator_type": "hotel_user",
        "initiator_name": current_user.name,
        "initiator_id": current_user.id,
        "ip_address": ip_address,
    }
    await db.channel_sync_logs.insert_one(sync_log)

    return {"message": "OTA reservation imported successfully", "pms_booking_id": booking.id, "guest_id": guest["id"], "room_number": room["room_number"]}


# rbac-allow: cache-rbac — exception queue operasyonel (FO/manager)
@router.get("/channel-manager/exceptions", dependencies=[_CM_READ_OPERATIONAL])
@cached(ttl=180, key_prefix="cm_exceptions")  # Cache for 3 min
async def get_exception_queue(status: str | None = None, exception_type: str | None = None, current_user: User = Depends(get_current_user)):
    """Get exception queue with filters"""
    query = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status
    if exception_type:
        query["exception_type"] = exception_type

    exceptions = await db.exception_queue.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"exceptions": exceptions, "count": len(exceptions)}


# ============= OTA OVERLAY & RATE PARITY =============


@router.get("/channel/parity/check", dependencies=[_CM_READ_SENSITIVE])
@cached(ttl=300, key_prefix="channel_parity")  # Cache for 5 min
async def check_rate_parity(
    date: str | None = None,
    room_type: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v86 DV: rate parity revenue
):
    """Check rate parity between OTA and direct rates"""
    target_date = datetime.fromisoformat(date).date() if date else datetime.now(UTC).date()

    # Get rooms
    room_query = {"tenant_id": current_user.tenant_id}
    if room_type:
        room_query["room_type"] = room_type

    rooms = await db.rooms.find(room_query, {"_id": 0}).to_list(1000)
    room_types = list({r["room_type"] for r in rooms})

    parity_results = []

    for rt in room_types:
        # Get direct rate (base_price from room)
        rt_rooms = [r for r in rooms if r["room_type"] == rt]
        if not rt_rooms:
            continue

        direct_rate = rt_rooms[0]["base_price"]

        # Get OTA rates from recent bookings
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())

        # Find bookings on this date by channel
        ota_bookings = await db.bookings.find(
            {
                "tenant_id": current_user.tenant_id,
                "room_id": {"$in": [r["id"] for r in rt_rooms]},
                "check_in": {"$gte": start_of_day.isoformat(), "$lte": end_of_day.isoformat()},
                "ota_channel": {"$ne": None},
            },
            {"_id": 0},
        ).to_list(100)

        # Group by OTA channel
        ota_rates = {}
        for booking in ota_bookings:
            if booking.get("ota_channel"):
                nights = (datetime.fromisoformat(booking["check_out"]) - datetime.fromisoformat(booking["check_in"])).days
                if nights > 0:
                    avg_rate = booking["total_amount"] / nights
                    channel = booking["ota_channel"]
                    if channel not in ota_rates:
                        ota_rates[channel] = []
                    ota_rates[channel].append(avg_rate)

        # Calculate average OTA rate per channel
        for channel, rates in ota_rates.items():
            avg_ota_rate = sum(rates) / len(rates)
            diff = direct_rate - avg_ota_rate

            if abs(diff) < 1:
                parity = ParityStatus.EQUAL
            elif diff > 0:
                parity = ParityStatus.POSITIVE  # Direct more expensive (good)
            else:
                parity = ParityStatus.NEGATIVE  # OTA more expensive (bad)

            parity_results.append(
                {
                    "date": target_date.isoformat(),
                    "room_type": rt,
                    "channel": channel,
                    "direct_rate": round(direct_rate, 2),
                    "ota_rate": round(avg_ota_rate, 2),
                    "difference": round(diff, 2),
                    "parity_status": parity,
                    "sample_size": len(rates),
                }
            )

    return {"date": target_date.isoformat(), "parity_checks": parity_results, "total_checks": len(parity_results)}


# rbac-allow: cache-rbac — channel health operasyonel cross-role
@router.get("/channel/status", dependencies=[_CM_READ_OPERATIONAL])
@cached(ttl=180, key_prefix="channel_status")  # Cache for 3 min
async def get_channel_status(current_user: User = Depends(get_current_user)):
    """Get health status of all channel connections"""
    # Get all connections
    connections = await db.channel_connections.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(100)

    # Check exception queue for issues
    recent_exceptions = await db.exception_queue.find(
        {"tenant_id": current_user.tenant_id, "status": "pending", "created_at": {"$gte": (datetime.now(UTC) - timedelta(hours=1)).isoformat()}}, {"_id": 0}
    ).to_list(100)

    channel_statuses = []

    for conn in connections:
        # Check for recent exceptions
        conn_exceptions = [e for e in recent_exceptions if e.get("channel_type") == conn.get("channel_type")]

        if len(conn_exceptions) > 10:
            health = ChannelHealth.ERROR
            message = f"{len(conn_exceptions)} pending exceptions"
        elif len(conn_exceptions) > 3:
            health = ChannelHealth.DELAYED
            message = f"{len(conn_exceptions)} pending exceptions"
        elif conn.get("status") != "active":
            health = ChannelHealth.OFFLINE
            message = "Connection inactive"
        else:
            health = ChannelHealth.HEALTHY
            message = "All systems operational"

        # Calculate delay if any
        delay_minutes = 0
        if conn_exceptions:
            oldest = min(conn_exceptions, key=lambda x: x["created_at"])
            delay_minutes = int((datetime.now(UTC) - datetime.fromisoformat(oldest["created_at"])).total_seconds() / 60)

        channel_statuses.append(
            {
                "channel_type": conn.get("channel_type"),
                "channel_name": conn.get("channel_name"),
                "health": health,
                "message": message,
                "pending_exceptions": len(conn_exceptions),
                "delay_minutes": delay_minutes,
                "last_sync": conn.get("last_sync_at", "Never"),
            }
        )

    return {
        "channels": channel_statuses,
        "total_channels": len(channel_statuses),
        "healthy_count": sum(1 for c in channel_statuses if c["health"] == ChannelHealth.HEALTHY),
        "warning_count": sum(1 for c in channel_statuses if c["health"] == ChannelHealth.DELAYED),
        "error_count": sum(1 for c in channel_statuses if c["health"] == ChannelHealth.ERROR),
    }


@router.post("/channel/insights/analyze", dependencies=[_CM_WRITE])
async def analyze_ota_insights(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    """AI-powered OTA channel analysis (Phase E preparation)"""
    # Default to last 30 days
    end = datetime.fromisoformat(end_date).date() if end_date else datetime.now(UTC).date()
    start = datetime.fromisoformat(start_date).date() if start_date else (end - timedelta(days=30))

    # Get all bookings in date range
    bookings = await db.bookings.find({"tenant_id": current_user.tenant_id, "check_in": {"$gte": start.isoformat(), "$lte": end.isoformat()}}, {"_id": 0}).to_list(10000)

    # Channel performance analysis
    channel_performance = {}
    total_revenue = 0
    total_commission_cost = 0

    for booking in bookings:
        channel = booking.get("ota_channel") or "direct"
        amount = booking.get("total_amount", 0)
        commission = booking.get("commission_pct", 0)

        if channel not in channel_performance:
            channel_performance[channel] = {"bookings": 0, "revenue": 0, "commission_cost": 0, "avg_rate": 0}

        channel_performance[channel]["bookings"] += 1
        channel_performance[channel]["revenue"] += amount

        if commission > 0:
            commission_amount = amount * (commission / 100)
            channel_performance[channel]["commission_cost"] += commission_amount
            total_commission_cost += commission_amount

        total_revenue += amount

    # Calculate averages and net revenue
    for channel, data in channel_performance.items():
        if data["bookings"] > 0:
            data["avg_rate"] = round(data["revenue"] / data["bookings"], 2)
            data["net_revenue"] = round(data["revenue"] - data["commission_cost"], 2)
            data["revenue_share_pct"] = round((data["revenue"] / total_revenue * 100) if total_revenue > 0 else 0, 2)
            data["commission_cost"] = round(data["commission_cost"], 2)

    # Sort by revenue
    sorted_channels = sorted(channel_performance.items(), key=lambda x: x[1]["revenue"], reverse=True)

    # Generate insights
    insights = []

    # Best performing channel
    if sorted_channels:
        best_channel = sorted_channels[0]
        insights.append(
            {
                "type": "top_performer",
                "channel": best_channel[0],
                "message": f"{best_channel[0]} is your top channel with ${best_channel[1]['revenue']:.2f} revenue ({best_channel[1]['bookings']} bookings)",
                "priority": "high",
            }
        )

    # High commission cost warning
    if total_commission_cost > total_revenue * 0.20:
        insights.append(
            {
                "type": "high_commission",
                "message": f"Commission costs are ${total_commission_cost:.2f} ({(total_commission_cost / total_revenue * 100):.1f}% of revenue). Consider direct booking strategies.",
                "priority": "medium",
            }
        )

    # Parity suggestions (placeholder for Phase E AI)
    insights.append({"type": "parity_suggestion", "message": "Consider rate parity monitoring to optimize OTA vs Direct pricing", "priority": "low"})

    return {
        "period": {"start_date": start.isoformat(), "end_date": end.isoformat(), "days": (end - start).days},
        "summary": {
            "total_bookings": len(bookings),
            "total_revenue": round(total_revenue, 2),
            "total_commission_cost": round(total_commission_cost, 2),
            "net_revenue": round(total_revenue - total_commission_cost, 2),
            "avg_commission_pct": round((total_commission_cost / total_revenue * 100) if total_revenue > 0 else 0, 2),
        },
        "channel_performance": dict(sorted_channels),
        "insights": insights,
        "recommendations": ["Monitor rate parity daily to prevent OTA undercutting", "Increase direct booking conversion with better incentives", "Negotiate commission rates with high-volume OTAs"],
    }


# ============= ENTERPRISE MODE FEATURES =============


@router.get("/channel-manager/rate-parity-check", dependencies=[_CM_READ_SENSITIVE])
async def check_rate_parity_detailed(date: str | None = None, room_type: str | None = None, current_user: User = Depends(get_current_user)):
    """
    Check rate parity across channels
    - Direct booking vs OTA rates
    - Identify negative disparity (OTA cheaper - BAD)
    - Alert on rate mismatches
    """
    target_date = date or datetime.now(UTC).date().isoformat()

    # Gercek kanal fiyatlarini cek; uydurma yok. Parite ODA TIPI bazinda hesaplanir
    # (oda tipleri arasi yanlis karsilastirmayi onlemek icin).
    rate_query = {"tenant_id": current_user.tenant_id, "date": target_date}
    if room_type:
        rate_query["room_type"] = room_type
    rate_rows = await db.channel_rates.find(rate_query, {"_id": 0}).to_list(2000)

    # Oda tipi -> baz fiyat (direct fallback).
    room_q = {"tenant_id": current_user.tenant_id}
    if room_type:
        room_q["room_type"] = room_type
    rooms = await db.rooms.find(room_q, {"_id": 0, "room_type": 1, "base_price": 1}).to_list(2000)
    base_price_by_type = {}
    for r in rooms:
        rt = r.get("room_type")
        if rt and rt not in base_price_by_type and isinstance(r.get("base_price"), (int, float)):
            base_price_by_type[rt] = r.get("base_price")

    # channel_rates'i oda tipine gore grupla.
    rates_by_type = {}
    for rr in rate_rows:
        if rr.get("rate") is None:
            continue
        ch = rr.get("channel")
        if not ch:
            continue
        rates_by_type.setdefault(rr.get("room_type"), {}).setdefault(ch, rr.get("rate"))

    rate_comparison = []
    parity_issues = []
    for rt, ch_rates in rates_by_type.items():
        direct_rt = ch_rates.get("direct")
        if direct_rt is None:
            direct_rt = base_price_by_type.get(rt)
        if direct_rt is not None:
            rate_comparison.append({"room_type": rt, "channel": "direct", "rate": round(direct_rt, 2)})
        for ch, rval in ch_rates.items():
            if ch == "direct":
                continue
            rate_comparison.append({"room_type": rt, "channel": ch, "rate": round(rval, 2)})
            if direct_rt is not None and direct_rt > 0 and rval < direct_rt:
                diff = rval - direct_rt
                diff_pct = diff / direct_rt * 100
                # Negatif disparite - OTA daha ucuz (KOTU)
                parity_issues.append(
                    {
                        "room_type": rt,
                        "channel": ch,
                        "status": "negative_disparity",
                        "severity": "critical",
                        "direct_rate": round(direct_rt, 2),
                        "channel_rate": round(rval, 2),
                        "difference": round(diff, 2),
                        "difference_pct": round(diff_pct, 1),
                        "message": f"{rt}: {ch} direct fiyattan %{abs(round(diff_pct, 1))} daha ucuz",
                    }
                )

    has_ota = any(any(c != "direct" for c in chs) for chs in rates_by_type.values())
    if not has_ota:
        recommendation = "Karsilastirilacak OTA fiyat kaydi yok; parite icin kanal fiyatlarini senkronize edin."
    elif parity_issues:
        recommendation = "OTA fiyatlarini pozitif disparite icin ayarlayin."
    else:
        recommendation = "Fiyat paritesi iyi."

    # Tek oda tipi sorgulandiysa direct_rate nettir; aksi halde tipler arasi belirsiz.
    top_direct = None
    if room_type:
        top_direct = rates_by_type.get(room_type, {}).get("direct")
        if top_direct is None:
            top_direct = base_price_by_type.get(room_type)

    return {
        "date": target_date,
        "room_type": room_type or "All",
        "direct_rate": round(top_direct, 2) if top_direct is not None else None,
        "rate_comparison": rate_comparison,
        "parity_status": "issues_found" if parity_issues else "good",
        "issues": parity_issues,
        "recommendation": recommendation,
    }


@router.get("/channel-manager/sync-history", dependencies=[_CM_READ_SENSITIVE])
async def get_channel_sync_history(days: int = 7, channel: str | None = None, current_user: User = Depends(get_current_user)):
    """
    Get channel sync history log
    - Successful syncs
    - Failed syncs
    - Sync duration
    """
    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=days)

    match_criteria = {"tenant_id": current_user.tenant_id, "timestamp": {"$gte": start_dt.isoformat(), "$lte": end_dt.isoformat()}}

    if channel:
        match_criteria["channel"] = channel

    sync_logs = []
    async for log in db.channel_sync_logs.find(match_criteria).sort("timestamp", -1):
        sync_logs.append(
            {
                "timestamp": log.get("timestamp"),
                "channel": log.get("channel"),
                "sync_type": log.get("sync_type"),  # rates, inventory, bookings
                "status": log.get("status"),  # success, failed
                "duration_ms": log.get("duration_ms"),
                "records_synced": log.get("records_synced"),
                "error_message": log.get("error_message"),
                "initiator_type": log.get("initiator_type"),
                "initiator_name": log.get("initiator_name"),
                "initiator_id": log.get("initiator_id"),
                "ip_address": log.get("ip_address"),
            }
        )

    # Calculate stats
    total_syncs = len(sync_logs)
    successful = sum(1 for log in sync_logs if log["status"] == "success")
    failed = total_syncs - successful

    return {
        "period_days": days,
        "start_date": start_dt.date().isoformat(),
        "end_date": end_dt.date().isoformat(),
        "channel_filter": channel,
        "summary": {"total_syncs": total_syncs, "successful": successful, "failed": failed, "success_rate": round((successful / total_syncs * 100), 1) if total_syncs > 0 else 0},
        "sync_logs": sync_logs,
    }


# ============= REVENUE MANAGEMENT ENHANCEMENTS =============


@router.get("/channels/status", dependencies=[_CM_READ_OPERATIONAL])
async def get_channel_status_v2(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get OTA channel connection status
    """
    current_user = await get_current_user(credentials)

    connections = await db.channel_connections.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(100)

    # Bugun olusturulan rezervasyonlari kanala gore say (gercek veri).
    today = datetime.now(UTC).date()
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())
    today_bookings = await db.bookings.find(
        {"tenant_id": current_user.tenant_id, "created_at": {"$gte": start_of_day.isoformat(), "$lte": end_of_day.isoformat()}}, {"_id": 0, "ota_channel": 1}
    ).to_list(10000)
    bookings_by_channel = {}
    for b in today_bookings:
        ch = b.get("ota_channel")
        if ch:
            bookings_by_channel[ch] = bookings_by_channel.get(ch, 0) + 1

    # Saglik icin son 1 saatteki bekleyen istisnalar.
    recent_exceptions = await db.exception_queue.find(
        {"tenant_id": current_user.tenant_id, "status": "pending", "created_at": {"$gte": (datetime.now(UTC) - timedelta(hours=1)).isoformat()}}, {"_id": 0}
    ).to_list(100)

    channels = []
    for conn in connections:
        ctype = conn.get("channel_type")
        conn_exceptions = [e for e in recent_exceptions if e.get("channel_type") == ctype]
        is_active = conn.get("status") == "active"
        synced = bool(conn.get("sync_rate_availability", False)) and is_active
        if (not is_active) or len(conn_exceptions) > 3:
            health = "warning"
        else:
            health = "good"
        channels.append(
            {
                "channel": conn.get("channel_name") or ctype,
                "status": "connected" if is_active else "disconnected",
                "last_sync": conn.get("last_sync_at") or conn.get("last_sync"),
                "inventory_synced": synced,
                "rates_synced": synced,
                "bookings_today": bookings_by_channel.get(ctype, 0),
                "connection_health": health,
            }
        )

    return {
        "channels": channels,
        "total_channels": len(channels),
        "connected_count": len([c for c in channels if c["status"] == "connected"]),
        "warning_count": len([c for c in channels if c["connection_health"] == "warning"]),
        "total_bookings_today": sum(c["bookings_today"] for c in channels),
    }


# 2. GET /api/channels/rate-parity - Rate parity check


@router.get("/channels/rate-parity", dependencies=[_CM_READ_SENSITIVE])
async def get_rate_parity(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Check rate parity across channels
    """
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date().isoformat()
    rooms = await db.rooms.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(2000)
    rt_price = {}
    for r in rooms:
        rt = r.get("room_type")
        if rt and rt not in rt_price and isinstance(r.get("base_price"), (int, float)):
            rt_price[rt] = r.get("base_price")

    rate_rows = await db.channel_rates.find({"tenant_id": current_user.tenant_id, "date": today}, {"_id": 0}).to_list(2000)
    rate_idx = {}
    for rr in rate_rows:
        if rr.get("rate") is not None:
            rate_idx[(rr.get("room_type"), rr.get("channel"))] = rr.get("rate")

    cols = [("booking_com", "Booking.com"), ("expedia", "Expedia"), ("agoda", "Agoda")]
    parity_data = []
    for rt, pms_rate in rt_price.items():
        row = {
            "date": today,
            "room_type": rt,
            "our_pms_rate": round(pms_rate, 2),
        }
        violating = None
        has_ota = False
        for key, label in cols:
            cr = rate_idx.get((rt, key))
            if cr is not None:
                has_ota = True
                row[key] = round(cr, 2)
                if pms_rate > 0 and cr < pms_rate:
                    violating = label
            else:
                row[key] = None
        row["parity_status"] = "violation" if violating else "good"
        row["violating_channel"] = violating
        if has_ota:
            parity_data.append(row)

    return {"parity_data": parity_data, "violations": len([p for p in parity_data if p["parity_status"] == "violation"]), "check_date": today}


# 3. GET /api/channels/inventory - Inventory distribution


@router.get("/channels/inventory", dependencies=[_CM_READ_SENSITIVE])
async def get_channel_inventory(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get inventory distribution across channels
    """
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())

    rooms = await db.rooms.find({"tenant_id": current_user.tenant_id}, {"_id": 0, "id": 1, "room_type": 1}).to_list(5000)
    room_type_by_id = {r.get("id"): (r.get("room_type") or "Unknown") for r in rooms}

    totals = {}
    for r in rooms:
        rt = r.get("room_type") or "Unknown"
        totals[rt] = totals.get(rt, 0) + 1

    # Bugun dolu odalar: aktif (iptal/checkout/no-show disi) ve tarih ortusen rezervasyonlar.
    occ_bookings = await db.bookings.find(
        {
            "tenant_id": current_user.tenant_id,
            "status": {"$nin": ["cancelled", "checked_out", "no_show"]},
            "check_in": {"$lte": end_of_day.isoformat()},
            "check_out": {"$gt": start_of_day.isoformat()},
        },
        {"_id": 0, "room_id": 1},
    ).to_list(20000)
    # Benzersiz dolu oda ID'leri (ayni odaya cakisan birden fazla rezervasyon
    # musaitligi yanlis dusurmesin diye set kullaniyoruz).
    occupied = {}
    for b in occ_bookings:
        rid = b.get("room_id")
        rt = room_type_by_id.get(rid)
        if rt and rid:
            occupied.setdefault(rt, set()).add(rid)

    inventory = []
    for rt, total in totals.items():
        avail = max(0, total - len(occupied.get(rt, set())))
        inventory.append({"date": today.isoformat(), "room_type": rt, "total_inventory": total, "available": avail, "allocations_available": False})

    return {"inventory": inventory, "total_available": sum(i["available"] for i in inventory), "allocations_available": False}


# 4. GET /api/channels/performance - Channel performance


@router.get("/channels/performance", dependencies=[_CM_READ_SENSITIVE])
async def get_channel_performance(days: int = 30, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get channel performance metrics
    """
    current_user = await get_current_user(credentials)

    end = datetime.now(UTC).date()
    start = end - timedelta(days=days)
    bookings = await db.bookings.find(
        {"tenant_id": current_user.tenant_id, "check_in": {"$gte": start.isoformat(), "$lte": end.isoformat()}, "ota_channel": {"$ne": None}},
        {"_id": 0, "ota_channel": 1, "total_amount": 1, "status": 1},
    ).to_list(20000)

    # Gelir = gerceklesen (iptal/no-show HARIC); cancellation_rate paydasi tum
    # rezervasyonlar; avg_rate gerceklesen gelir / gerceklesen rezervasyon.
    perf = {}
    total_revenue = 0.0
    total_bookings = 0
    for b in bookings:
        ch = b.get("ota_channel")
        if not ch:
            continue
        status = b.get("status")
        amount = b.get("total_amount") or 0
        if ch not in perf:
            perf[ch] = {"channel": ch, "bookings": 0, "realized_bookings": 0, "revenue": 0.0, "cancelled": 0}
        perf[ch]["bookings"] += 1
        total_bookings += 1
        if status == "cancelled":
            perf[ch]["cancelled"] += 1
        if status not in ("cancelled", "no_show"):
            perf[ch]["revenue"] += amount
            perf[ch]["realized_bookings"] += 1
            total_revenue += amount

    performance = []
    for ch, d in perf.items():
        bk = d["bookings"]
        rev = d["revenue"]
        rbk = d["realized_bookings"]
        performance.append(
            {
                "channel": ch,
                "bookings": bk,
                "revenue": round(rev, 2),
                "avg_rate": round(rev / rbk, 2) if rbk > 0 else 0,
                "cancellation_rate": round(d["cancelled"] / bk * 100, 1) if bk > 0 else 0,
                "market_share": round(rev / total_revenue * 100, 1) if total_revenue > 0 else 0,
            }
        )
    performance.sort(key=lambda x: x["revenue"], reverse=True)

    return {
        "performance": performance,
        "period_days": days,
        "total_bookings": total_bookings,
        "total_revenue": round(total_revenue, 2),
        "best_performer": performance[0]["channel"] if performance else None,
    }


# 5. POST /api/channels/push-rates - Push rates to channels


@router.post("/channels/push-rates", dependencies=[_CM_WRITE])
async def push_rates_to_channels(
    room_type: str,
    date: str,
    rate: float,
    channels: list[str],
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_channel_connectors")),  # v92 DW
):
    """
    Push rates to selected OTA channels
    """
    current_user = await get_current_user(credentials)

    # Pinned saglayici tespiti otoriterdir (yalnizca okuma; pilot_drift=0).
    try:
        from domains.channel_manager.unified_rate_manager_router import (
            _detect_active_provider,
        )

        detection = await _detect_active_provider(current_user.tenant_id, prefer=None)
    except Exception:
        detection = {"provider": None, "configuration_error": "detection_failed"}
    provider = detection.get("provider")
    configuration_error = detection.get("configuration_error")

    # Fiyat niyetini yerel olarak kaydet; uydurma 'success' URETME.
    rate_log = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "channels": channels,
        "room_type": room_type,
        "new_rate": rate,
        "date_from": date,
        "date_to": date,
        "updated_by": getattr(current_user, "name", None),
        "updated_by_id": getattr(current_user, "id", None),
        "provider": provider,
        "ari_status": "recorded_local" if provider else "not_configured",
        "configuration_error": configuration_error,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.rate_updates.insert_one(rate_log)

    if provider:
        message = "Fiyat niyeti kaydedildi. Gercek OTA dagitimi pinned saglayici uzerinden Toplu Fiyat/Envanter (Unified Rate Manager) ekranindan yapilir; bu uc dogrudan kanala gondermez."
    else:
        message = "Kanal saglayici yapilandirilmamis; fiyat gercek kanala gonderilmedi. Degisiklik yerel olarak kaydedildi."

    return {
        "message": message,
        "room_type": room_type,
        "date": date,
        "rate": rate,
        "provider": provider,
        "configuration_error": configuration_error,
        "pushed": False,
        "queued": False,
        "results": [],
    }


# ============================================================================
# CORPORATE CONTRACTS MOBILE
# ============================================================================

# 1. GET /api/corporate/contracts - Corporate contracts
