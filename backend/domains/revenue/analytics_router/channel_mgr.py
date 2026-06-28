"""
channel_mgr

Auto-split sub-router (shared imports/classes inlined).
"""

"""
Domain Router: Analytics

Extracted from legacy_routes.py — GM Dashboard, pickup analysis, anomaly detection, revenue analytics.
"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from core.database import db
from core.security import _is_super_admin, get_current_user, security
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.role_permission_service import require_role as _require_role

# v67 Bug DD: frontdesk/* endpoint'lerinde RBAC eksikti — HK kullanıcı guest PII (search-bookings),
# müsaitlik (available-rooms), oda atama (assign-room) erişebiliyordu. Front office personeline kısıtla.
_FD_READ = Depends(_require_role("super_admin", "admin", "supervisor", "front_desk"))
_FD_WRITE = Depends(_require_role("super_admin", "admin", "front_desk"))

# --------------------------------------------------------------------------
# GM Dashboard - Pickup Analysis & Anomaly Detection
# --------------------------------------------------------------------------


# rbac-allow: cache-rbac — FO booking search operasyonel

# rbac-allow: cache-rbac — FO available rooms operasyonel


_SYSTEM_HEALTH_CACHE: dict = {"ts": 0.0, "payload": None}
_SYSTEM_HEALTH_TTL = 5.0  # seconds

router = APIRouter(prefix="/api", tags=["analytics"])


# ── GET /channel-manager/overview ──
@router.get("/channel-manager/overview")
async def get_channel_manager_overview(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Channel manager overview — gercek bagli kanallar + bugunun rezervasyonlari.

    Veri kaynaklari:
    - channel_connections: tenant'in gercek kanal baglantilari (durum, son senkron)
    - bookings: bugun check-in olan rezervasyonlar, kaynaga (source) gore toplanir
    Bagli kanal yoksa fail-closed (data_available=False) doner; uydurma kanal uretmez.
    """
    current_user = await get_current_user(credentials)

    connections = await db.channel_connections.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(100)

    if not connections:
        return {
            "channels": {},
            "summary": {
                "total_channels": 0,
                "connected_channels": 0,
                "total_bookings_today": 0,
                "total_revenue_today": 0.0,
            },
            "data_available": False,
            "message": "Bagli kanal bulunmuyor. Kanal yoneticisi yapilandirilmamis.",
        }

    today_str = datetime.now(UTC).date().isoformat()

    # Bugunun rezervasyonlarini kaynaga gore topla (gercek veri)
    bookings_by_source: dict = {}
    async for b in db.bookings.find(
        {
            "tenant_id": current_user.tenant_id,
            "check_in": {"$gte": today_str, "$lte": today_str},
        }
    ):
        src = b.get("source") or "direct"
        key = str(src).lower().replace(" ", "_")
        agg = bookings_by_source.setdefault(key, {"bookings": 0, "revenue": 0.0})
        agg["bookings"] += 1
        agg["revenue"] += b.get("total_amount", 0) or 0

    channels: dict = {}
    for conn in connections:
        name = conn.get("name") or conn.get("channel_type") or conn.get("provider") or "unknown"
        key = str(conn.get("channel_type") or conn.get("provider") or name).lower().replace(" ", "_")
        today_agg = bookings_by_source.get(key, {"bookings": 0, "revenue": 0.0})
        channels[key] = {
            "name": name,
            "status": conn.get("status", "unknown"),
            "last_sync": conn.get("last_sync") or conn.get("last_sync_at") or conn.get("updated_at"),
            "bookings_today": today_agg["bookings"],
            "revenue_today": round(today_agg["revenue"], 2),
            "commission_rate": conn.get("commission_rate"),
        }

    total_bookings = sum(ch["bookings_today"] for ch in channels.values())
    total_revenue = sum(ch["revenue_today"] for ch in channels.values())

    return {
        "channels": channels,
        "summary": {
            "total_channels": len(channels),
            "connected_channels": sum(1 for ch in channels.values() if ch["status"] in ("connected", "active")),
            "total_bookings_today": total_bookings,
            "total_revenue_today": round(total_revenue, 2),
        },
        "data_available": True,
    }


# ── GET /channel-manager/rate-comparison ──
@router.get("/channel-manager/rate-comparison")
async def get_channel_rate_comparison(date: str | None = None, room_type: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Compare rates across all channels.

    Gercek kanal-bazli rate-shopping (rakip fiyat) kaynagi entegre degil.
    Uydurma fiyat uretmek yerine fail-closed (data_available=False) doner.
    """
    await get_current_user(credentials)

    if not date:
        date = datetime.now(UTC).date().isoformat()

    return {
        "date": date,
        "room_type": room_type or "Standard",
        "channels": {},
        "your_rate": None,
        "competitor_avg": None,
        "recommendation": None,
        "suggested_rate": None,
        "data_available": False,
        "message": "Kanal bazli fiyat karsilastirma (rate-shopping) verisi mevcut degil.",
    }


# ── GET /channel-manager/revenue-by-channel ──
@router.get("/channel-manager/revenue-by-channel")
async def get_revenue_by_channel(start_date: str | None = None, end_date: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get revenue breakdown by channel"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC)
    if not start_date:
        start_date = (today - timedelta(days=30)).date().isoformat()
    if not end_date:
        end_date = today.date().isoformat()

    # Aggregate actual bookings by source
    channel_revenue = {}

    async for booking in db.bookings.find({"tenant_id": current_user.tenant_id, "check_in": {"$gte": start_date, "$lte": end_date}}):
        source = booking.get("source", "Direct")
        amount = booking.get("total_amount", 0)

        if source not in channel_revenue:
            channel_revenue[source] = {"revenue": 0, "bookings": 0, "avg_value": 0}

        channel_revenue[source]["revenue"] += amount
        channel_revenue[source]["bookings"] += 1

    # Calculate averages
    for channel in channel_revenue:
        if channel_revenue[channel]["bookings"] > 0:
            channel_revenue[channel]["avg_value"] = round(channel_revenue[channel]["revenue"] / channel_revenue[channel]["bookings"], 2)
        channel_revenue[channel]["revenue"] = round(channel_revenue[channel]["revenue"], 2)

    total_revenue = sum(ch["revenue"] for ch in channel_revenue.values())

    return {"channels": channel_revenue, "total_revenue": round(total_revenue, 2), "period": {"start": start_date, "end": end_date}}


# ── POST /channel-manager/push-availability ──
@router.post("/channel-manager/push-availability")
async def push_channel_availability(
    check_in: str,
    check_out: str,
    room_type: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_channel_connectors")),  # v92 DW
):
    """Musaitlik dagitim durumu (legacy). Bu uc UYDURMA push URETMEZ.

    Gercek musaitlik/ARI push'u pinned saglayici (Exely|HotelRunner) uzerinden
    Unified Rate Manager (Toplu Fiyat/Envanter) ekraninda yapilir. Bu uc
    yalnizca pinned-provider yapilandirma durumunu durustce raporlar (yalnizca
    okuma; pilot_drift=0); sahte channel_sync_logs satiri YAZMAZ.
    """
    current_user = await get_current_user(credentials)

    # Pinned-provider tespiti OTORITERDIR; istemci girdisi ezemez (yalnizca okuma).
    try:
        from services.cm_provider import _detect_active_provider

        detection = await _detect_active_provider(current_user.tenant_id, prefer=None)
    except Exception:
        detection = {"provider": None, "configuration_error": "detection_failed"}
    provider = detection.get("provider")

    if not provider:
        return {
            "message": "Kanal saglayici yapilandirilmamis; musaitlik gercek kanala gonderilmedi.",
            "data_available": False,
            "pushed": False,
            "provider": None,
            "configuration_error": detection.get("configuration_error"),
        }

    return {
        "message": "Musaitlik dagitimi bu ekrandan yapilmaz. Gercek push icin Toplu Fiyat/Envanter (Rate Manager) ekranini kullanin.",
        "data_available": True,
        "pushed": False,
        "provider": provider,
    }


# ── POST /channel-manager/update-rates ──
@router.post("/channel-manager/update-rates")
async def update_channel_rates(
    rate_update: dict,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_channel_connectors")),  # v89 DW
):
    """Fiyat degisikligini yerel olarak KAYDET ve pinned-provider durumunu raporla.

    Bu legacy form FE'den yalnizca PMS oda tipi adi + kanal kutucuklari gonderir;
    saglayici-native oda/plan kodlarini TASIMAZ. Bu nedenle gercek OTA dagitimi
    Unified Rate Manager (Toplu Fiyat/Envanter) ekraninda, pinned saglayici
    (Exely|HotelRunner) uzerinden yapilir. Bu uc UYDURMA 'success' URETMEZ:
    fiyat niyetini rate_updates'e kaydeder, pinned saglayiciyi gercek tespit
    eder (yalnizca okuma; pilot_drift=0) ve durumu durustce dondurur. Sahte
    channel_sync_logs satiri YAZILMAZ (gercek bir kanal senkronu olmadi).
    """
    current_user = await get_current_user(credentials)

    # Only admins and revenue managers can update rates (super_admin always allowed)
    if not _is_super_admin(current_user) and current_user.role not in ["admin", "revenue_manager", "gm"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Girdi dogrulama (fail-closed; uydurma basari yok).
    room_type = rate_update.get("room_type")
    date_from = rate_update.get("date_from")
    date_to = rate_update.get("date_to")
    new_rate = rate_update.get("new_rate")
    valid_rate = isinstance(new_rate, (int, float)) and not isinstance(new_rate, bool)
    if not room_type or not date_from or not date_to or not valid_rate:
        return {
            "message": "Eksik/gecersiz alan: oda tipi, tarih araligi ve gecerli bir fiyat gereklidir.",
            "data_available": False,
            "queued": False,
            "pushed": False,
            "channels_updated": 0,
        }

    # Determine initiator info
    # v109 Bug DAK round-6 (T09 P2): naive XFF allowed audit-log IP spoofing.
    # Use the trusted-proxy aware client_ip() helper (rightmost edge hop only).
    from security.auth_throttle import client_ip as _client_ip

    ip_address = _client_ip(request)
    initiator_type = "pms_staff" if getattr(current_user, "is_staff", False) else "hotel_user"

    # Pinned-provider tespiti OTORITERDIR; istemci girdisi ezemez (yalnizca okuma).
    try:
        from services.cm_provider import _detect_active_provider

        detection = await _detect_active_provider(current_user.tenant_id, prefer=None)
    except Exception:
        detection = {"provider": None, "configuration_error": "detection_failed"}
    provider = detection.get("provider")
    configuration_error = detection.get("configuration_error")
    ari_status = "recorded_local" if provider else "not_configured"

    # Fiyat niyetini yerel audit olarak kaydet (gercek kayit; uydurma push YOK).
    rate_log = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "channels": rate_update.get("channels", []),
        "room_type": room_type,
        "new_rate": new_rate,
        "date_from": date_from,
        "date_to": date_to,
        "updated_by": current_user.name,
        "updated_by_id": current_user.id,
        "initiator_type": initiator_type,
        "ip_address": ip_address,
        "provider": provider,
        "ari_status": ari_status,
        "configuration_error": configuration_error,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.rate_updates.insert_one(rate_log)

    if not provider:
        return {
            "message": "Kanal saglayici yapilandirilmamis; fiyat gercek kanala gonderilmedi. Degisiklik yerel olarak kaydedildi.",
            "data_available": False,
            "queued": False,
            "pushed": False,
            "provider": None,
            "configuration_error": configuration_error,
            "channels_updated": 0,
            "log_id": rate_log["id"],
        }

    return {
        "message": "Fiyat degisikligi yerel olarak kaydedildi. Gercek OTA dagitimi icin Toplu Fiyat/Envanter (Rate Manager) ekranini kullanin.",
        "data_available": True,
        "queued": False,
        "pushed": False,
        "provider": provider,
        "channels_updated": 0,
        "log_id": rate_log["id"],
    }
