"""
Channel Connections Overview Router
====================================
Tüm kanal sağlayıcılarının (HotelRunner, Exely) bağlantı durumunu
tek bir endpoint'ten döndürür. Yeni otel onboarding akışı için.
"""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from core.database import db
from core.security import get_current_user
from models.schemas import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/channel-manager/connections",
    tags=["Channel Connections"],
)


@router.get("/overview")
async def get_connections_overview(current_user: User = Depends(get_current_user)):
    """Tüm kanal sağlayıcılarının bağlantı durumunu döndürür."""
    tid = current_user.tenant_id

    # HotelRunner status
    hr_conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": tid},
        {"_id": 0, "token": 0, "credentials_ref": 0},
    )
    hr_mappings = await db.hotelrunner_room_mappings.count_documents({"tenant_id": tid})

    hr_status = {
        "provider": "hotelrunner",
        "display_name": "HotelRunner",
        "connected": bool(hr_conn and hr_conn.get("is_active")),
        "property_name": hr_conn.get("property_name", "") if hr_conn else "",
        "hr_id": hr_conn.get("hr_id", "") if hr_conn else "",
        "environment": hr_conn.get("environment", "") if hr_conn else "",
        "channels": hr_conn.get("channels", []) if hr_conn else [],
        "connected_at": hr_conn.get("connected_at") if hr_conn else None,
        "last_sync_at": hr_conn.get("last_sync_at") if hr_conn else None,
        "auto_sync_reservations": hr_conn.get("auto_sync_reservations", False) if hr_conn else False,
        "room_mappings_count": hr_mappings,
    }

    # Exely status
    exely_conn = await db.exely_connections.find_one(
        {"tenant_id": tid},
        {"_id": 0, "password": 0, "username": 0, "credentials_ref": 0},
    )
    exely_mappings = await db.exely_room_mappings.count_documents({"tenant_id": tid})

    exely_status = {
        "provider": "exely",
        "display_name": "Exely",
        "connected": bool(exely_conn and exely_conn.get("is_active")),
        "property_name": exely_conn.get("property_name", "") if exely_conn else "",
        "hotel_code": exely_conn.get("hotel_code", "") if exely_conn else "",
        "mode": exely_conn.get("mode", "") if exely_conn else "",
        "currency": exely_conn.get("currency", "TRY") if exely_conn else "TRY",
        "room_types": exely_conn.get("room_types", []) if exely_conn else [],
        "rate_plans": exely_conn.get("rate_plans", []) if exely_conn else [],
        "connected_at": exely_conn.get("connected_at") if exely_conn else None,
        "last_sync_at": exely_conn.get("last_sync_at") if exely_conn else None,
        "auto_sync_reservations": exely_conn.get("auto_sync_reservations", False) if exely_conn else False,
        "room_mappings_count": exely_mappings,
    }

    # PMS room types (for reference)
    pms_rooms = await db.rooms.find(
        {"tenant_id": tid},
        {"_id": 0, "room_type": 1},
    ).to_list(500)
    pms_room_types = sorted({r.get("room_type", "") for r in pms_rooms if r.get("room_type")})

    return {
        "tenant_id": tid,
        "providers": [hr_status, exely_status],
        "pms_room_types": pms_room_types,
        "checked_at": datetime.now(UTC).isoformat(),
    }
