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

    # HotelRunner status — iki koleksiyondan da okuyup tek doğruluk
    # kaynağı oluştur. Önceki davranış: yalnızca eksik (`not hr_conn`)
    # durumda provider_connections'a düşüyordu; ancak legacy doküman
    # var olup `is_active` eksik/false olsa bile scheduler
    # provider_connections veya secrets manager'daki token'la başarıyla
    # çekim yapabiliyordu — bu durumda UI yanlış "Bağlı Değil"
    # gösteriyordu. Çözüm: legacy doc'u yükle, eksik alanları
    # provider_connections ile zenginleştir, `is_active`'i her iki
    # kaynaktan birinde aktif ise true kabul et.
    hr_conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": tid},
        {"_id": 0, "token": 0, "credentials_ref": 0},
    )
    prov_hr = await db.provider_connections.find_one(
        {"tenant_id": tid, "provider": "hotelrunner", "status": "active"},
        {"_id": 0},
    )
    if prov_hr:
        creds = prov_hr.get("credentials", {})
        if not hr_conn:
            hr_conn = {
                "is_active": True,
                "property_name": prov_hr.get("display_name", "HotelRunner"),
                "hr_id": creds.get("hr_id", ""),
                "environment": "sandbox",
                "channels": [],
                "connected_at": prov_hr.get("created_at"),
                "last_sync_at": None,
                "auto_sync_reservations": prov_hr.get(
                    "sync_reservations", False),
            }
        else:
            # Legacy doc var ama is_active eksik/false → provider_connections
            # aktifse "bağlı" kabul et; eksik metadata'yı zenginleştir.
            hr_conn["is_active"] = True
            if not hr_conn.get("hr_id") and creds.get("hr_id"):
                hr_conn["hr_id"] = creds["hr_id"]
            if not hr_conn.get("property_name"):
                hr_conn["property_name"] = prov_hr.get(
                    "display_name", "HotelRunner")
    hr_mappings = await db.hotelrunner_room_mappings.count_documents({"tenant_id": tid})
    if hr_mappings == 0:
        hr_mappings = await db.cm_mappings.count_documents(
            {"tenant_id": tid, "entity_type": "room_type",
             "connector_id": {"$regex": "hr"}, "status": "active"}
        )

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

    # Exely status — aynı çift-kaynak okuma + zenginleştirme deseni.
    exely_conn = await db.exely_connections.find_one(
        {"tenant_id": tid},
        {"_id": 0, "password": 0, "username": 0, "credentials_ref": 0},
    )
    prov_ex = await db.provider_connections.find_one(
        {"tenant_id": tid, "provider": "exely", "status": "active"},
        {"_id": 0},
    )
    if prov_ex:
        ex_creds = prov_ex.get("credentials", {})
        if not exely_conn:
            exely_conn = {
                "is_active": True,
                "property_name": prov_ex.get("display_name", "Exely"),
                "hotel_code": ex_creds.get("hotel_code", ""),
                "mode": "soap",
                "currency": "TRY",
                "room_types": [],
                "rate_plans": [],
                "connected_at": prov_ex.get("created_at"),
                "last_sync_at": None,
                "auto_sync_reservations": prov_ex.get(
                    "sync_reservations", False),
            }
        else:
            exely_conn["is_active"] = True
            if not exely_conn.get("hotel_code") and ex_creds.get("hotel_code"):
                exely_conn["hotel_code"] = ex_creds["hotel_code"]
            if not exely_conn.get("property_name"):
                exely_conn["property_name"] = prov_ex.get(
                    "display_name", "Exely")
    exely_mappings = await db.exely_room_mappings.count_documents({"tenant_id": tid})
    if exely_mappings == 0:
        exely_mappings = await db.cm_mappings.count_documents(
            {"tenant_id": tid, "entity_type": "room_type",
             "connector_id": {"$regex": "ex"}, "status": "active"}
        )

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
