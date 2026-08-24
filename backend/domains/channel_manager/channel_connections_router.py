"""
Channel Connections Overview Router
====================================
Tüm kanal sağlayıcılarının (HotelRunner, Exely) bağlantı durumunu
tek bir endpoint'ten döndürür. Yeni otel onboarding akışı için.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from core.database import db
from core.security import get_current_user
from models.schemas import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/channel-manager/connections",
    tags=["Channel Connections"],
)


_HOTELRUNNER_ACTIVE_STATES = {"active", "activated", "enabled", "live"}


def normalize_active_hotelrunner_channels(
    channels: Any,
    *,
    assume_connected: bool = False,
) -> list[dict[str, str]]:
    """Return only channels that HotelRunner explicitly marks as active.

    ``GET /infos/channels`` is HotelRunner's complete sales-channel catalogue;
    it must never be presented as the hotel's active-channel list. The
    dedicated ``GET /infos/connected_channels`` endpoint is authoritative
    even though HotelRunner's documented response omits a status field. Set
    ``assume_connected`` only for records returned by that endpoint.
    """
    if not isinstance(channels, list):
        return []

    active_channels: list[dict[str, str]] = []
    seen: set[str] = set()
    for channel in channels:
        if not isinstance(channel, dict):
            # Historical connection documents stored catalogue names as plain
            # strings. Their active state is unknowable, so fail closed.
            continue

        raw = channel.get("raw") if isinstance(channel.get("raw"), dict) else {}
        status = str(channel.get("status") or channel.get("state") or raw.get("status") or raw.get("state") or "").strip().lower()
        explicitly_active = any(
            value is True
            for value in (
                channel.get("active"),
                channel.get("is_active"),
                channel.get("enabled"),
                raw.get("active"),
                raw.get("is_active"),
                raw.get("enabled"),
            )
        )
        if status not in _HOTELRUNNER_ACTIVE_STATES and not explicitly_active and not (assume_connected and not status):
            continue

        code = str(channel.get("code") or raw.get("code") or "").strip()
        name = str(channel.get("name") or raw.get("name") or code).strip()
        key = (code or name).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        active_channels.append(
            {
                "code": code,
                "name": name,
                "status": status or "active",
            }
        )

    return active_channels


async def _load_active_hotelrunner_channels(
    tenant_id: str,
    connection: dict[str, Any] | None,
) -> tuple[list[dict[str, str]], bool, str | None]:
    """Refresh active channels via provider GET, with a safe local fallback.

    A failed refresh may use the last successfully verified active list, but it
    deliberately never falls back to the legacy ``channels`` catalogue.
    """
    if not connection or not connection.get("is_active"):
        return [], False, None

    try:
        from domains.channel_manager.providers.hotelrunner.factory import get_provider

        provider, _ = await get_provider(tenant_id)
        result = await provider.get_connected_channels()
        if not result.get("success"):
            raise RuntimeError(result.get("error") or "connected channel refresh failed")

        data = result.get("data") or {}
        active_channels = normalize_active_hotelrunner_channels(
            data.get("connected_channels", data.get("channels", [])),
            assume_connected=True,
        )
        refreshed_at = datetime.now(UTC).isoformat()
        await db.hotelrunner_connections.update_one(
            {"tenant_id": tenant_id},
            {
                "$set": {
                    "connected_channels": active_channels,
                    "connected_channels_refreshed_at": refreshed_at,
                }
            },
        )
        return active_channels, False, refreshed_at
    except Exception as exc:
        logger.warning(
            "HotelRunner active-channel refresh failed tenant=%s error=%s",
            tenant_id[:8],
            type(exc).__name__,
        )
        cached = normalize_active_hotelrunner_channels(connection.get("connected_channels", []))
        return cached, True, connection.get("connected_channels_refreshed_at")


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
        {
            "_id": 0,
            "credentials.hr_id": 1,
            "hr_id": 1,
            "property_id": 1,
            "display_name": 1,
            "created_at": 1,
            "sync_reservations": 1,
        },
    )
    if prov_hr:
        creds = prov_hr.get("credentials", {})
        provider_hr_id = prov_hr.get("hr_id") or creds.get("hr_id", "")
        if not hr_conn:
            hr_conn = {
                "is_active": True,
                "property_name": prov_hr.get("display_name", "HotelRunner"),
                "hr_id": provider_hr_id,
                "environment": "sandbox",
                "channels": [],
                "connected_at": prov_hr.get("created_at"),
                "last_sync_at": None,
                "auto_sync_reservations": prov_hr.get("sync_reservations", False),
            }
        else:
            # Legacy doc var ama is_active eksik/false → provider_connections
            # aktifse "bağlı" kabul et; eksik metadata'yı zenginleştir.
            hr_conn["is_active"] = True
            if not hr_conn.get("hr_id") and provider_hr_id:
                hr_conn["hr_id"] = provider_hr_id
            if not hr_conn.get("property_name"):
                hr_conn["property_name"] = prov_hr.get("display_name", "HotelRunner")
    hr_active_channels, hr_channels_stale, hr_channels_refreshed_at = await _load_active_hotelrunner_channels(
        tid,
        hr_conn,
    )
    hr_mappings = await db.hotelrunner_room_mappings.count_documents({"tenant_id": tid})
    if hr_mappings == 0:
        hr_mappings = await db.cm_mappings.count_documents({"tenant_id": tid, "entity_type": "room_type", "connector_id": {"$regex": "hr"}, "status": "active"})

    hr_status = {
        "provider": "hotelrunner",
        "display_name": "HotelRunner",
        "connected": bool(hr_conn and hr_conn.get("is_active")),
        "property_name": hr_conn.get("property_name", "") if hr_conn else "",
        "hr_id": hr_conn.get("hr_id", "") if hr_conn else "",
        "environment": hr_conn.get("environment", "") if hr_conn else "",
        # Only provider-verified active channels. ``hr_conn.channels`` is the
        # complete HotelRunner catalogue retained for legacy compatibility.
        "channels": hr_active_channels,
        "channels_stale": hr_channels_stale,
        "channels_refreshed_at": hr_channels_refreshed_at,
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
                "auto_sync_reservations": prov_ex.get("sync_reservations", False),
            }
        else:
            exely_conn["is_active"] = True
            if not exely_conn.get("hotel_code") and ex_creds.get("hotel_code"):
                exely_conn["hotel_code"] = ex_creds["hotel_code"]
            if not exely_conn.get("property_name"):
                exely_conn["property_name"] = prov_ex.get("display_name", "Exely")
    exely_mappings = await db.exely_room_mappings.count_documents({"tenant_id": tid})
    if exely_mappings == 0:
        exely_mappings = await db.cm_mappings.count_documents({"tenant_id": tid, "entity_type": "room_type", "connector_id": {"$regex": "ex"}, "status": "active"})

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
