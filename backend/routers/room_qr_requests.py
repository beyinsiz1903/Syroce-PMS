"""
Oda QR Talepleri (Room QR Requests)
====================================
Her odaya özel QR kod; misafir QR'ı okutup giriş yapmadan talep iletir.
Talep otomatik olarak ilgili departmana yönlendirilir ve takip edilebilir.

Veri modeli (MongoDB `room_qr_requests` koleksiyonu):
- tenant_id, room_id, room_number
- category, department (DepartmentType), title, description
- status (new/assigned/in_progress/completed/cancelled)
- priority, guest_name, guest_phone, language, booking_id
- assigned_to, created_at, updated_at, completed_at
- status_history[]

QR token: HMAC-SHA256(tenant_id|room_id, JWT_SECRET) — DB'de ekstra state yok.
"""

import hashlib
import hmac
import ipaddress
import logging
import os
import re
import secrets
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError

from cache_manager import cache as _cache
from core.database import _raw_db as raw_db
from core.security import JWT_SECRET, generate_qr_code, get_current_user

logger = logging.getLogger("room_qr_requests")

# Güvenlik: HMAC için ayrı bir sır değişkeni önerilir; yoksa JWT_SECRET kullanılır.
# Üretim güvenliği için ikisi de yoksa fail-closed davranır.
_QR_SECRET = os.environ.get("ROOM_QR_SECRET") or JWT_SECRET

# IP-bazlı rate limit (Redis-backed → multi-instance dağıtık koruma)
_RL_WINDOW_SEC = 600  # 10 dakika
_RL_MAX_HITS = 20  # 10 dakikada 20 submit / IP+oda

# Per-room/day complaint mirror kotası (DoS / spam guard'ı için)
# Aşıldığında room_qr_requests kaydı YİNE oluşur (talep iletilir) ama
# service_complaints'a mirror yapılmaz — sahte misafir DoS'u şikayet
# yönetimini boğamasın.
_COMPLAINT_QUOTA_PER_ROOM_DAY = 10

# Trusted proxy IP listesi: TRUSTED_PROXIES env var virgülle ayrılmış
# IP veya CIDR (örn: "10.0.0.0/8,127.0.0.1"). request.client.host bu
# listede DEĞİLSE x-forwarded-for header'ına güvenilmez (spoofing'i
# engellemek için). Boşsa varsayılan loopback + private RFC1918.
_DEFAULT_TRUSTED_CIDRS = "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"


def _parse_trusted_proxies() -> list:
    raw = os.environ.get("TRUSTED_PROXIES", _DEFAULT_TRUSTED_CIDRS)
    networks = []
    for token in (raw or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            networks.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            logger.warning("[room_qr] invalid TRUSTED_PROXIES entry: %r", token)
    return networks


_TRUSTED_PROXIES = _parse_trusted_proxies()


def _is_trusted_proxy(ip_str: str) -> bool:
    if not ip_str or not _TRUSTED_PROXIES:
        return False
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in net for net in _TRUSTED_PROXIES)


def _client_ip(request: Request) -> str:
    """Misafir IP'sini döndürür. x-forwarded-for'a SADECE direct connection
    güvenilir bir proxy'den geliyorsa güvenir; aksi halde header spoof
    edilebilir. Bu fonksiyon hem rate-limit hem audit için kullanılır."""
    direct_ip = request.client.host if request.client else ""
    if _is_trusted_proxy(direct_ip):
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            # En soldaki IP gerçek client'tır (RFC 7239)
            candidate = xff.split(",")[0].strip()
            if candidate:
                return candidate
    return direct_ip or "unknown"


def _rl_check(key: str) -> bool:
    """True = izin, False = limit aşıldı.
    Redis-backed counter: tüm backend instance'ları aynı limiti paylaşır.
    Cache erişilemezse fail-open (loglanır, talep işlenir)."""
    full_key = f"qr:rl:{key}"
    count = _cache.incr_with_ttl(full_key, _RL_WINDOW_SEC)
    if count == 0:
        # Backend hata verdi (Redis down + in-memory yok) — fail-open
        logger.warning("[room_qr] rate-limit counter unavailable, allowing %s", key)
        return True
    return count <= _RL_MAX_HITS


def _complaint_quota_check(tenant_id: str, room_id: str) -> tuple:
    """Şikayet mirror kotası: gün+oda başına max N.
    Tuple: (allowed, count).
    Fail-CLOSED: Redis erişilemezse mirror'a izin verilmez (DoS bypass'ı
    önlemek için). Talep kaydı (room_qr_requests) yine oluşur — sadece
    ServiceRecovery'ye otomatik düşmez."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    full_key = f"qr:complaint_quota:{tenant_id}:{room_id}:{today}"
    # 24 saat TTL (gün sonu otomatik sıfırlanır)
    count = _cache.incr_with_ttl(full_key, 86400)
    if count == 0:
        # Cache fail → fail-CLOSED (mirror'ı engelle, warn + denied flag)
        logger.warning("[room_qr] complaint quota counter unavailable — mirror DENIED (fail-closed) for %s/%s", tenant_id, room_id)
        return False, 0
    return count <= _COMPLAINT_QUOTA_PER_ROOM_DAY, count


def _mask_name(name: str | None) -> str | None:
    """'John Doe' → 'J*** D***' (misafir gizliliği için)."""
    if not name:
        return None
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return None
    return " ".join((p[0] + "***") if len(p) >= 1 else "*" for p in parts)


router = APIRouter(tags=["Room QR Requests"])

COLL = "room_qr_requests"


_INDEXES_READY = False


async def _ensure_indexes() -> None:
    """Idempotent index creation. Cheap on subsequent calls; mongo no-ops if
    the index already exists. Indexed fields match every staff query path
    (tenant scoping + status/department filters + created_at sort)."""
    global _INDEXES_READY
    if _INDEXES_READY:
        return
    try:
        await raw_db[COLL].create_index([("tenant_id", 1), ("created_at", -1)], name="rqr_tenant_created")
        await raw_db[COLL].create_index([("tenant_id", 1), ("status", 1), ("created_at", -1)], name="rqr_tenant_status_created")
        await raw_db[COLL].create_index([("tenant_id", 1), ("department", 1), ("status", 1)], name="rqr_tenant_dept_status")
        await raw_db[COLL].create_index([("tenant_id", 1), ("room_id", 1)], name="rqr_tenant_room")

        # Guest sessions indexes
        await raw_db["room_guest_sessions"].create_index("token_hash", unique=True, name="rgs_token_hash")
        await raw_db["room_guest_sessions"].create_index("expires_at", expireAfterSeconds=0, name="rgs_expires_at")
        await raw_db["room_guest_sessions"].create_index([("tenant_id", 1), ("property_id", 1), ("room_id", 1), ("booking_id", 1)], name="rgs_lookup")
        await raw_db["room_guest_sessions"].create_index("revoked_at", name="rgs_revoked_at")

        _INDEXES_READY = True
    except Exception as e:
        # Atlas may reject new collections (cluster limit reached); we skip
        # silently — query still works on tenant_id full scan for empty data.
        logger.debug(f"room_qr_requests index setup skipped: {e}")

    # Guest Service Catalogue Indexes
    try:
        await raw_db["guest_service_catalogue_settings"].create_index(
            [("tenant_id", 1), ("property_id", 1)],
            unique=True,
            name="gsc_settings_lookup"
        )
        await raw_db["guest_service_departments"].create_index(
            [("tenant_id", 1), ("property_id", 1), ("department_code", 1)],
            unique=True,
            name="gsc_dept_unique"
        )
        await raw_db["guest_service_departments"].create_index(
            [("tenant_id", 1), ("property_id", 1), ("enabled", 1), ("display_order", 1)],
            name="gsc_dept_order"
        )
        await raw_db["guest_service_items"].create_index(
            [("tenant_id", 1), ("property_id", 1), ("service_code", 1)],
            unique=True,
            name="gsc_item_unique"
        )
        await raw_db["guest_service_items"].create_index(
            [("tenant_id", 1), ("property_id", 1), ("department_code", 1), ("enabled", 1), ("display_order", 1)],
            name="gsc_item_order"
        )
        await raw_db["guest_service_submissions"].create_index(
            [("tenant_id", 1), ("property_id", 1), ("booking_id", 1), ("idempotency_key", 1)],
            unique=True,
            name="gsc_ledger_unique"
        )
        await raw_db["guest_service_submissions"].create_index(
            [("tenant_id", 1), ("submission_reference", 1)],
            unique=True,
            name="gsc_ledger_reference_unique"
        )
        await raw_db["qr_requests"].create_index(
            [("tenant_id", 1), ("submission_group_id", 1), ("service_code", 1)],
            unique=True,
            partialFilterExpression={"submission_group_id": {"$exists": True}, "service_code": {"$exists": True}},
            name="gsc_request_group_service_unique"
        )
        await raw_db["qr_requests"].create_index(
            [("tenant_id", 1), ("request_reference", 1)],
            unique=True,
            partialFilterExpression={"request_reference": {"$exists": True}},
            name="gsc_request_reference_unique"
        )

    except Exception as e:
        logger.warning(f"[room_qr] Failed to create catalogue indexes: group=catalogue_indexes error_class={e.__class__.__name__}")



from domains.guest.qr_constants import CATEGORY_CATALOG, CATEGORY_LABELS, CATEGORY_MAP, VALID_PRIORITIES

VALID_STATUSES = {"new", "assigned", "in_progress", "completed", "cancelled"}


# ── Per-tenant QR secret rotation (backward-compatible) ──────────────
# Un-rotated tenants carry NO salt → token derivation is byte-identical to
# the original `HMAC(tenant_id|room_id)` scheme (zero migration, no churn on
# already-printed QR codes). After an operator rotates, a per-tenant salt is
# mixed into the HMAC so every previously issued token fails `_verify_token`.
_QR_SALT_COLL = "room_qr_secret_versions"
_QR_SALT_CACHE_PREFIX = "room_qr_salt"
_QR_SALT_CACHE_TTL = 300  # saniye — public scan hot-path'ini tek-RTT tutar


async def _get_qr_salt(tenant_id: str) -> str | None:
    """Tenant'ın aktif QR HMAC tuzunu döndürür; None → legacy (rotate edilmemiş).

    Negatif sonuç (tuz yok) de cache'lenir (sentinel "") → her public taramada
    DB lookup yapılmaz. Rotation cache'i hemen günceller, eski tokenlar düşer.
    """
    try:
        doc = await raw_db[_QR_SALT_COLL].find_one({"tenant_id": tenant_id})
        salt = (doc or {}).get("salt") or ""
    except Exception:
        salt = ""
    return salt or None


def _token_for(tenant_id: str, room_id: str, salt: str | None = None) -> str:
    if not _QR_SECRET:
        # Üretimde sır yoksa fail-closed — güvensiz sabit fallback yok
        raise HTTPException(
            status_code=503,
            detail="QR servisi yapılandırılmamış: ROOM_QR_SECRET veya JWT_SECRET gerekir",
        )
    secret = _QR_SECRET.encode("utf-8")
    # salt yoksa legacy mesaj formatı korunur (byte-identik token).
    raw = f"{tenant_id}|{room_id}" if not salt else f"{tenant_id}|{room_id}|{salt}"
    return hmac.new(secret, raw.encode(), hashlib.sha256).hexdigest()  # tam digest (64 char)


def _verify_token(tenant_id: str, room_id: str, token: str, salt: str | None = None) -> bool:
    if not _QR_SECRET:
        return False
    expected = _token_for(tenant_id, room_id, salt)
    return hmac.compare_digest(expected, token or "")


def _public_url_base(request: Request) -> str:
    env_url = os.environ.get("PUBLIC_APP_URL") or os.environ.get("CLOUD_DEV_DOMAIN")
    if env_url:
        if not env_url.startswith("http"):
            env_url = f"https://{env_url}"
        return env_url.rstrip("/")
    # İstek başlığından türet
    proto = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return f"{proto}://{host}".rstrip("/")


# Otel adindan URL-guvenli slug uretimi (YALNIZCA dekoratif — QR token
# tenant_id|room_id|salt uzerinde dogrulanir; slug dogrulamaya GIRMEZ).
# Turkce karakterler ASCII'ye indirgenir; slug bossa slug'siz URL'ye dusulur.
_TR_SLUG_MAP = str.maketrans(
    {
        "s": "s",
        "S": "s",
        "c": "c",
        "C": "c",
        "g": "g",
        "G": "g",
        "i": "i",
        "I": "i",
        "o": "o",
        "O": "o",
        "u": "u",
        "U": "u",
        "\u015f": "s",
        "\u015e": "s",
        "\u00e7": "c",
        "\u00c7": "c",
        "\u011f": "g",
        "\u011e": "g",
        "\u0131": "i",
        "\u0130": "i",
        "\u00f6": "o",
        "\u00d6": "o",
        "\u00fc": "u",
        "\u00dc": "u",
    }
)


def _slugify_hotel(name: str | None) -> str:
    if not name:
        return ""
    s = name.translate(_TR_SLUG_MAP)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:60]


async def _hotel_slug(tenant_id: str) -> str:
    """Tenant'in otel adindan dekoratif slug (QR URL'sinde marka gorunurlugu)."""
    try:
        tenant = await raw_db["tenants"].find_one({"id": tenant_id}, {"_id": 0, "name": 1, "display_name": 1}) or {}
    except Exception:
        return ""
    return _slugify_hotel(tenant.get("name") or tenant.get("display_name"))


def _guest_url_with_salt(
    request: Request,
    tenant_id: str,
    room_id: str,
    salt: str | None,
    slug: str | None = None,
) -> str:
    base = _public_url_base(request)
    token = _token_for(tenant_id, room_id, salt)
    # Slug yalnizca dekoratif segment; dogrulama tenant_id/room_id ile yapilir.
    # Bossa geriye donuk uyumlu (slug'siz) URL → eski QR'lar bozulmaz.
    if slug:
        return f"{base}/g/{slug}/room/{tenant_id}/{room_id}?t={token}"
    return f"{base}/g/room/{tenant_id}/{room_id}?t={token}"


async def _guest_url(request: Request, tenant_id: str, room_id: str) -> str:
    salt = await _get_qr_salt(tenant_id)
    slug = await _hotel_slug(tenant_id)
    return _guest_url_with_salt(request, tenant_id, room_id, salt, slug)


async def _find_active_booking(tenant_id: str, room_id: str) -> dict | None:
    """Odadaki aktif rezervasyonu bulur (check-in yapmış misafir)."""
    try:
        b = await raw_db["bookings"].find_one(
            {
                "tenant_id": tenant_id,
                "room_id": room_id,
                "status": {"$in": ["checked_in", "in_house"]},
            }
        )
        return b
    except Exception:
        return None


def _resolve_property_id(tenant_id: str, room: dict, booking: dict) -> str | None:
    """Resolve the property scope for canonical and legacy PMS records.

    Older single-property tenants may have no ``property_id`` on rooms and
    bookings. The tenant id is the canonical fallback used elsewhere in the
    PMS for those records. An explicit room/booking mismatch still fails
    closed. The caller has already matched both records by tenant + room id,
    so accepting one populated side does not widen the room boundary.
    """
    room_property_id = room.get("property_id")
    booking_property_id = booking.get("property_id")

    if room_property_id and booking_property_id and room_property_id != booking_property_id:
        return None

    return room_property_id or booking_property_id or tenant_id



# ═══════════════════════════════════════════════════════════════
# GUEST SESSION MANAGEMENT (Phase 1 Security Hardening)
# ═══════════════════════════════════════════════════════════════

async def _verify_guest_session(tenant_id: str, room_id: str, session_token: str | None) -> tuple[dict, dict]:
    if not session_token:
        raise HTTPException(status_code=401, detail="Yetkisiz: Misafir oturumu eksik")

    token_hash = hashlib.sha256(session_token.encode()).hexdigest()

    # Verify room is still active to resolve property_id safely
    room = await raw_db["rooms"].find_one({"id": room_id, "tenant_id": tenant_id})
    if not room or room.get("is_active") is False:
        raise HTTPException(status_code=410, detail="Oda kullanımda değil")

    # Verify booking is still active
    booking = await _find_active_booking(tenant_id, room_id)
    if not booking:
        raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

    property_id = _resolve_property_id(tenant_id, room, booking)
    if not property_id:
        raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

    booking = {**booking, "property_id": property_id}

    # Check session exists with all strict mandatory fields
    session = await raw_db["room_guest_sessions"].find_one({
        "tenant_id": tenant_id,
        "property_id": property_id,
        "room_id": room_id,
        "booking_id": booking["id"],
        "token_hash": token_hash,
    })

    if not session:
        raise HTTPException(status_code=401, detail="Yetkisiz: Geçersiz oturum")

    # Require mandatory fields exist
    if "expires_at" not in session or not session["expires_at"]:
        raise HTTPException(status_code=401, detail="Yetkisiz: Geçersiz oturum")

    now = datetime.now(UTC)
    if session["expires_at"].tzinfo is None:
        session["expires_at"] = session["expires_at"].replace(tzinfo=UTC)

    if session["expires_at"] < now:
        raise HTTPException(status_code=401, detail="Yetkisiz: Oturum süresi dolmuş")
    if session.get("revoked_at") is not None:
        raise HTTPException(status_code=401, detail="Yetkisiz: Oturum iptal edilmiş")

    return booking, session

@router.post("/api/public/room-qr/{tenant_id}/{room_id}/session")
async def public_create_guest_session(
    tenant_id: str,
    room_id: str,
    request: Request,
    t: str = Query(...)
):
    """Static QR okutulduktan sonra aktif rezervasyona bağlı kısa ömürlü session üretir."""
    client_ip = _client_ip(request)
    if not _rl_check(f"{tenant_id}:{room_id}:{client_ip}:session"):
        raise HTTPException(status_code=429, detail="Çok fazla deneme — lütfen sonra deneyin")

    salt = await _get_qr_salt(tenant_id)
    if not _verify_token(tenant_id, room_id, t, salt):
        raise HTTPException(status_code=403, detail="Geçersiz QR token")

    room = await raw_db["rooms"].find_one({"id": room_id, "tenant_id": tenant_id})
    if not room or room.get("is_active") is False:
        raise HTTPException(status_code=410, detail="Oda kullanımda değil")

    booking = await _find_active_booking(tenant_id, room_id)
    if not booking:
        # Do not leak occupancy. Just return generic 403.
        raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

    property_id = _resolve_property_id(tenant_id, room, booking)
    if not property_id:
        raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    now = datetime.now(UTC)

    expires_at = now + timedelta(hours=24)
    departure_date = booking.get("departure_date") or booking.get("check_out")
    if departure_date:
        try:
            is_date_only = False
            if isinstance(departure_date, str):
                departure_date_str = departure_date.strip()
                import re
                if re.match(r"^\d{4}-\d{2}-\d{2}$", departure_date_str):
                    is_date_only = True

                if is_date_only:
                    import zoneinfo
                    from datetime import date
                    y, m, d = map(int, departure_date_str.split("-"))
                    dep_date = date(y, m, d)

                    prop = await raw_db["properties"].find_one({"id": property_id, "tenant_id": tenant_id}) or {}
                    checkout_time_str = prop.get("checkout_time", "12:00")
                    prop_tz_str = prop.get("timezone", "UTC")
                    try:
                        tz = zoneinfo.ZoneInfo(prop_tz_str)
                    except Exception:
                        tz = UTC

                    try:
                        hh, mm = map(int, checkout_time_str.split(":"))
                    except Exception:
                        hh, mm = 12, 0

                    dep = datetime(dep_date.year, dep_date.month, dep_date.day, hh, mm, 0, tzinfo=tz).astimezone(UTC)
                else:
                    dep = datetime.fromisoformat(departure_date_str.replace("Z", "+00:00"))
                    if dep.tzinfo is None:
                        dep = dep.replace(tzinfo=UTC)
            else:
                dep = departure_date
                if dep.tzinfo is None:
                    dep = dep.replace(tzinfo=UTC)

            expires_at = min(expires_at, dep)
        except Exception:
            # If checkout/departure exists but cannot be safely parsed, fail closed
            raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")
    else:
        # Policy: If no checkout datetime exists on the active booking, safely fallback to now + 24h
        pass

    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "property_id": property_id,
        "room_id": room_id,
        "booking_id": booking["id"],
        "token_hash": token_hash,
        "created_at": now,
        "expires_at": expires_at,
        "revoked_at": None
    }
    await raw_db["room_guest_sessions"].insert_one(doc)

    return {
        "session_token": raw_token,
        "expires_at": expires_at.isoformat()
    }

# ═══════════════════════════════════════════════════════════════
# PUBLIC ENDPOINTS (misafir — auth yok)
# ═══════════════════════════════════════════════════════════════


@router.get("/api/public/room-qr/{tenant_id}/{room_id}")
async def public_room_info(tenant_id: str, room_id: str, t: str = Query(...)):
    """QR tarayıp formu açmak için oda & otel bilgilerini döner."""
    salt = await _get_qr_salt(tenant_id)
    if not _verify_token(tenant_id, room_id, t, salt):
        raise HTTPException(status_code=403, detail="Geçersiz QR token")

    room = await raw_db["rooms"].find_one({"id": room_id, "tenant_id": tenant_id})
    if not room or room.get("is_active") is False:
        raise HTTPException(status_code=410, detail="Oda kullanımda değil")

    tenant = await raw_db["tenants"].find_one({"id": tenant_id}) or {}

    return {
        "hotel_name": tenant.get("name") or tenant.get("display_name") or "Hotel",
        "hotel_logo": tenant.get("logo_url"),
        "primary_color": tenant.get("primary_color") or "#0ea5e9",
        "room_number": room.get("room_number"),
        "room_type": room.get("room_type"),
        "categories": [
            {
                "id": c["id"],
                "department": c["department"],
                "icon": c["icon"],
                "labels": CATEGORY_LABELS.get(c["id"], {"en": c["id"]}),
                "default_priority": c["default_priority"],
            }
            for c in CATEGORY_CATALOG
        ],
    }


from models.schemas.qr_catalogue_submission import LegacyRequestSubmit, StructuredRequestSubmit


@router.post("/api/public/room-qr/{tenant_id}/{room_id}/submit")
async def public_submit_request(
    tenant_id: str,
    room_id: str,
    payload: dict,
    request: Request,
    x_guest_session: str = Header(None)
):
    """Misafir talep gönderir (aktif rezervasyon gerektirir)."""
    client_ip = _client_ip(request)
    if not _rl_check(f"{tenant_id}:{room_id}:{client_ip}:submit"):
        raise HTTPException(status_code=429, detail="Çok fazla talep — lütfen sonra deneyin")
    booking, guest_session = await _verify_guest_session(tenant_id, room_id, x_guest_session)
    room = await raw_db["rooms"].find_one({"id": room_id, "tenant_id": tenant_id})
    if not room or room.get("is_active") is False:
        raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

    property_id = _resolve_property_id(tenant_id, room, booking)
    session_prop = guest_session.get("property_id")

    if not property_id or not session_prop:
        raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

    if property_id != session_prop:
        raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

    booking = {**booking, "property_id": property_id}

    room_number = room.get("room_number")

    if "items" in payload:
        try:
            struct_payload = StructuredRequestSubmit.model_validate(payload)
        except ValidationError:
            raise HTTPException(status_code=422, detail="Geçersiz girdi")

        from domains.guest.qr_submission_service import handle_structured_submission

        guest_name = payload.get("guest_name") or booking.get("guest_name") or booking.get("primary_guest_name")
        guest_phone = payload.get("guest_phone") or booking.get("guest_phone")

        res = await handle_structured_submission(
            tenant_id=tenant_id,
            property_id=booking.get("property_id"),
            room_id=room_id,
            booking_id=booking["id"],
            session_id=guest_session["id"],
            room_number=room_number,
            payload=struct_payload,
            guest_name=guest_name,
            guest_phone=guest_phone
        )

        docs_to_emit = res.pop("docs_to_emit", [])

        for doc in docs_to_emit:
            if doc["category"] == "complaint":
                quota_ok, quota_count = _complaint_quota_check(tenant_id, room_id)
                if not quota_ok:
                    logger.warning("[room_qr] complaint mirror quota exceeded for room=%s", room_id)
                else:
                    try:
                        desc = doc["description"].strip()
                        subject = desc[:80] + ("..." if len(desc) > 80 else "")
                        severity_map = {"urgent": "critical", "high": "high", "normal": "medium", "low": "low"}
                        complaint_doc = {
                            "id": str(uuid.uuid4()),
                            "tenant_id": tenant_id,
                            "source": "guest_qr",
                            "qr_request_id": doc["_id"],
                            "category": "service_recovery",
                            "severity": severity_map.get(doc["priority"], "medium"),
                            "subject": subject,
                            "description": desc,
                            "guest_name": doc.get("guest_name"),
                            "guest_phone": doc.get("guest_phone"),
                            "room_id": room_id,
                            "room_number": doc.get("room_number"),
                            "booking_id": doc.get("booking_id"),
                            "assigned_department": "front_office",
                            "status": "open",
                            "created_by": None,
                            "created_at": doc["created_at"].isoformat() if isinstance(doc["created_at"], datetime) else doc["created_at"],
                            "updated_at": doc["updated_at"].isoformat() if isinstance(doc["updated_at"], datetime) else doc["updated_at"],
                            "history": [{
                                "action": "created",
                                "actor_id": None,
                                "actor_name": doc.get("guest_name") or "Misafir",
                                "at": doc["created_at"].isoformat() if isinstance(doc["created_at"], datetime) else doc["created_at"],
                                "notes": "Misafir tarafından oda QR üzerinden iletildi (Structured)"
                            }]
                        }
                        await raw_db["service_complaints"].insert_one(complaint_doc)
                    except Exception as exc:
                        logger.warning(f"[room_qr] complaint mirror failed: {exc}")

            try:
                from domains.guest.messaging import guest_requests as _gr
                await _gr.add_guest_message(
                    tenant_id=tenant_id, room_id=room_id, property_id=booking.get("property_id"),
                    room_number=doc.get("room_number"), sender_type="guest", body=doc["description"],
                    booking_id=doc.get("booking_id"), sender_name=doc.get("guest_name") or "Misafir",
                    request_id=doc["_id"], category=doc["category"], department=doc["department"],
                    priority=doc["priority"], guest_session_id=guest_session["id"]
                )
                cat_label_tr = CATEGORY_LABELS.get(doc["category"], {}).get("tr", doc["category"])
                await _gr.notify_department(
                    tenant_id=tenant_id, room_number=doc.get("room_number"),
                    qr_department=doc["department"], category_label=cat_label_tr
                )
                await _gr.emit_guest_requests_ping(tenant_id, room_id)
            except Exception as exc:
                logger.warning(f"[room_qr] guest-requests chat entegrasyonu atlandı: {exc}")

            try:
                from core.ws_rooms import tenant_broadcast_room
                from websocket_server import sio  # type: ignore
                await sio.emit(
                    "room_request:new",
                    {
                        "id": doc["_id"],
                        "tenant_id": tenant_id,
                        "room_number": doc.get("room_number"),
                        "category": doc["category"],
                        "department": doc["department"],
                        "priority": doc["priority"],
                    },
                    room=tenant_broadcast_room(tenant_id),
                )
            except Exception as e:
                logger.debug(f"WS emit atlandı: {e}")

        return res

    else:
        try:
            legacy_payload = LegacyRequestSubmit.model_validate(payload)
        except ValidationError:
            raise HTTPException(status_code=422, detail="Geçersiz girdi")

        payload_obj = legacy_payload

        if payload_obj.category not in CATEGORY_MAP:
            raise HTTPException(status_code=400, detail=f"Geçersiz kategori: {payload_obj.category}")

        if payload_obj.priority not in VALID_PRIORITIES:
            payload_obj.priority = "normal"

        cat = CATEGORY_MAP[payload_obj.category]
        now = datetime.now(UTC)
        title_label = CATEGORY_LABELS.get(payload_obj.category, {}).get(payload_obj.language, payload_obj.category)

        doc = {
            "_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "room_id": room_id,
            "room_number": room.get("room_number"),
            "category": payload_obj.category,
            "department": cat["department"],
            "title": f"{title_label} — Oda {room.get('room_number')}",
            "description": payload_obj.description.strip(),
            "priority": payload_obj.priority,
            "status": "new",
            "language": payload_obj.language,
            "guest_name": payload_obj.guest_name or booking.get("guest_name") or booking.get("primary_guest_name"),
            "guest_phone": payload_obj.guest_phone or booking.get("guest_phone"),
            "booking_id": booking["id"],
            "guest_session_id": guest_session["id"],
            "assigned_to": None,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "source": "qr",
            "status_history": [{"status": "new", "by": "guest", "at": now, "note": "QR üzerinden gönderildi"}],
        }
        await raw_db[COLL].insert_one(doc)

        if payload_obj.category == "complaint":
            quota_ok, quota_count = _complaint_quota_check(tenant_id, room_id)
            if not quota_ok:
                logger.warning(
                    "[room_qr] complaint mirror quota exceeded for room=%s (today=%d, limit=%d)",
                    room_id,
                    quota_count,
                    _COMPLAINT_QUOTA_PER_ROOM_DAY,
                )
            else:
                try:
                    desc = payload_obj.description.strip()
                    subject = desc[:80] + ("..." if len(desc) > 80 else "")
                    severity_map = {
                        "urgent": "critical",
                        "high": "high",
                        "normal": "medium",
                        "low": "low",
                    }
                    complaint_doc = {
                        "id": str(uuid.uuid4()),
                        "tenant_id": tenant_id,
                        "source": "guest_qr",
                        "qr_request_id": doc["_id"],
                        "category": "service_recovery",
                        "severity": severity_map.get(payload_obj.priority, "medium"),
                        "subject": subject,
                        "description": desc,
                        "guest_name": doc.get("guest_name"),
                        "guest_phone": doc.get("guest_phone"),
                        "room_id": room_id,
                        "room_number": doc.get("room_number"),
                        "booking_id": doc.get("booking_id"),
                        "assigned_department": "front_office",
                        "status": "open",
                        "created_by": None,
                        "created_at": now.isoformat(),
                        "updated_at": now.isoformat(),
                        "history": [
                            {
                                "action": "created",
                                "actor_id": None,
                                "actor_name": doc.get("guest_name") or "Misafir",
                                "at": now.isoformat(),
                                "notes": "Misafir tarafından oda QR üzerinden iletildi",
                            }
                        ],
                    }
                    await raw_db["service_complaints"].insert_one(complaint_doc)
                    logger.info(f"[room_qr] guest complaint mirrored: {complaint_doc['id']} (quota_today={quota_count}/{_COMPLAINT_QUOTA_PER_ROOM_DAY})")
                except Exception as exc:
                    logger.warning(f"[room_qr] complaint mirror failed: {exc}")

        try:
            from domains.guest.messaging import guest_requests as _gr
            await _gr.add_guest_message(
                tenant_id=tenant_id,
                room_id=room_id,
                property_id=booking["property_id"],
                room_number=doc.get("room_number"),
                sender_type="guest",
                body=doc["description"],
                booking_id=doc.get("booking_id"),
                sender_name=doc.get("guest_name") or "Misafir",
                request_id=doc["_id"],
                category=payload_obj.category,
                department=doc["department"],
                priority=doc["priority"],
                guest_session_id=guest_session["id"],
            )
            cat_label_tr = CATEGORY_LABELS.get(payload_obj.category, {}).get("tr", payload_obj.category)
            await _gr.notify_department(
                tenant_id=tenant_id,
                room_number=doc.get("room_number"),
                qr_department=doc["department"],
                category_label=cat_label_tr,
            )
            await _gr.emit_guest_requests_ping(tenant_id, room_id)
        except Exception as exc:
            logger.warning("[room_qr] guest-requests chat entegrasyonu atlandı: %s", exc)

        try:
            from core.ws_rooms import tenant_broadcast_room
            from websocket_server import sio  # type: ignore

            await sio.emit(
                "room_request:new",
                {
                    "id": doc["_id"],
                    "tenant_id": tenant_id,
                    "room_number": doc["room_number"],
                    "category": doc["category"],
                    "department": doc["department"],
                    "priority": doc["priority"],
                },
                room=tenant_broadcast_room(tenant_id),
            )
        except Exception as e:
            logger.debug(f"WS emit atlandı: {e}")

        return {
            "success": True,
            "request_id": doc["_id"],
            "department": doc["department"],
            "message": "Talebiniz alındı, ilgili departmana iletildi.",
        }

def _utc_now():
    from datetime import UTC, datetime
    return datetime.now(UTC)

@router.get("/api/public/room-qr/{tenant_id}/{room_id}/catalogue")
async def public_get_catalogue(
    tenant_id: str,
    room_id: str,
    lang: str = Query("en"),
    x_guest_session: str = Header(None)
):
    """Misafir için dinamik QR hizmet kataloğunu döndürür."""



    try:
        booking, guest_session = await _verify_guest_session(tenant_id, room_id, x_guest_session)
        property_id = booking.get("property_id")
        if not property_id:
            raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

        session_prop = guest_session.get("property_id")
        if session_prop and session_prop != property_id:
            raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

    except HTTPException:
        raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")
    from domains.guest.qr_catalogue_service import fetch_catalogue_data, is_service_available, process_lang, resolve_catalogue_mode

    mode = await resolve_catalogue_mode(tenant_id, property_id)
    if mode == "disabled":
        raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

    prop = await raw_db["properties"].find_one({"id": property_id, "tenant_id": tenant_id}) or {}
    prop_tz = prop.get("timezone", "UTC")
    prop_lang = prop.get("default_language", "en")

    depts_out, services_out = await fetch_catalogue_data(tenant_id, property_id, mode)

    if not depts_out and not services_out:
         raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

    def local_process_lang(labels: dict | None) -> str:
        return process_lang(labels, lang, prop_lang)

    def local_process_lang_dict(data: dict | None) -> str | None:
        if not data:
            return None
        return local_process_lang(data)

    enabled_dept_codes = set()
    initial_depts = []

    for d in depts_out:
        if not d.get("enabled", True):
            continue
        dept_code = d.get("department_code")
        if not dept_code:
            continue
        initial_depts.append({
            "department_code": dept_code,
            "display_order": d.get("display_order", 0),
            "label": local_process_lang(d.get("labels")),
            "icon": d.get("icon")
        })
        enabled_dept_codes.add(dept_code)

    formatted_services = []
    used_dept_codes = set()

    for s in services_out:
        if not s.get("enabled", True):
            continue
        dept_code = s.get("department_code")
        if dept_code not in enabled_dept_codes:
            continue

        if not is_service_available(s.get("service_hours"), prop_tz):
            continue

        config = s.get("input_config", {})
        if s.get("input_type") in ("single_choice", "multi_choice"):
            opts = config.get("options", [])
            mapped_opts = []
            for opt in opts:
                mapped_opts.append({
                    "code": opt.get("code"),
                    "label": local_process_lang(opt.get("labels"))
                })
            config["options"] = mapped_opts

        formatted_services.append({
            "service_code": s.get("service_code"),
            "department_code": dept_code,
            "label": local_process_lang(s.get("labels")),
            "description": local_process_lang_dict(s.get("description")),
            "icon": s.get("icon"),
            "input_type": s.get("input_type"),
            "input_config": config,
            "auto_priority": s.get("auto_priority", "normal"),
            "estimated_minutes": s.get("estimated_minutes", 0),
            "is_chargeable": s.get("is_chargeable", False),
            "charge_warning": local_process_lang_dict(s.get("charge_warning"))
        })
        used_dept_codes.add(dept_code)

    formatted_depts = []
    for d in initial_depts:
        if d["department_code"] in used_dept_codes:
            d.pop("display_order", None)
            formatted_depts.append(d)

    if not formatted_depts and not formatted_services:
        raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

    return {
        "catalogue_version": 1,
        "departments": formatted_depts,
        "services": formatted_services,
        "server_timestamp": _utc_now().isoformat()
    }



# ═══════════════════════════════════════════════════════════════
# GUEST THREAD ENDPOINTS (public, QR token'lı — iki yönlü sohbet)
# ═══════════════════════════════════════════════════════════════


class GuestThreadMessage(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)


def _guest_facing_messages(messages: list[dict]) -> list[dict]:
    """Misafire dönmeden önce personel kimliğini maskele.

    Personel mesajlarında gerçek personel adı yerine jenerik "Otel Ekibi"
    gösterilir (anonim misafire personel adını sızdırma). Okuma-takip alanı
    (read) zaten viewer_user_id=None ile serileştirmede yok.
    """
    out = []
    for m in messages:
        mm = dict(m)
        if mm.get("sender_type") == "staff":
            mm["sender_name"] = "Otel Ekibi"
        out.append(mm)
    return out


@router.get("/api/public/room-qr/{tenant_id}/{room_id}/thread")
async def public_get_thread(
    tenant_id: str,
    room_id: str,
    x_guest_session: str = Header(None)
):
    """Misafir kendi mesaj thread'ini görür."""
    booking, guest_session = await _verify_guest_session(tenant_id, room_id, x_guest_session)

    from domains.guest.messaging import guest_requests as _gr

    # Strict property and booking scoped query for guest isolation
    messages = await _gr.public_get_guest_thread(
        tenant_id=tenant_id,
        property_id=booking["property_id"],
        room_id=room_id,
        booking_id=booking["id"]
    )
    return {"messages": _guest_facing_messages(messages)}


@router.post("/api/public/room-qr/{tenant_id}/{room_id}/thread/message")
async def public_post_thread_message(
    tenant_id: str,
    room_id: str,
    payload: GuestThreadMessage,
    request: Request,
    t: str = Query(...),
):
    """Misafir mevcut thread'ine yanıt yazar (iki yönlü)."""
    # Rate limit BEFORE token verify (submit ile aynı DoS-sentinel deseni).
    client_ip = _client_ip(request)
    if not _rl_check(f"{tenant_id}:{room_id}:{client_ip}"):
        raise HTTPException(status_code=429, detail="Çok fazla mesaj — lütfen sonra deneyin")

    salt = await _get_qr_salt(tenant_id)
    if not _verify_token(tenant_id, room_id, t, salt):
        raise HTTPException(status_code=403, detail="Geçersiz QR token")

    text = (payload.body or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Mesaj boş olamaz")

    room = await raw_db["rooms"].find_one({"id": room_id, "tenant_id": tenant_id})
    if not room:
        raise HTTPException(status_code=404, detail="Oda bulunamadı")

    from domains.guest.messaging import guest_requests as _gr

    booking = await _find_active_booking(tenant_id, room_id)
    if not booking:
        raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

    property_id = _resolve_property_id(tenant_id, room, booking)
    if not property_id:
        raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

    booking = {**booking, "property_id": property_id}
    booking_id = booking.get("id") if booking else None
    sender_name = (booking.get("guest_name") if booking else None) or "Misafir"

    doc = await _gr.add_guest_message(
        tenant_id=tenant_id,
        room_id=room_id,
        property_id=booking["property_id"],
        room_number=room.get("room_number"),
        sender_type="guest",
        body=text,
        booking_id=booking_id,
        sender_name=sender_name,
    )
    await _gr.emit_guest_requests_ping(tenant_id, room_id)
    return {
        "success": True,
        "message": {
            "id": doc["id"],
            "sender_type": "guest",
            "body": text,
            "created_at": doc["created_at"].astimezone(UTC).isoformat(),
        },
    }


# ═══════════════════════════════════════════════════════════════
# STAFF ENDPOINTS (auth'lu)
# ═══════════════════════════════════════════════════════════════


def _tenant_of(user) -> str:
    tid = getattr(user, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=400, detail="Tenant bulunamadı")
    return tid


def _serialize(doc: dict) -> dict:
    if not doc:
        return doc
    d = dict(doc)
    d["id"] = d.pop("_id", None)
    for k in ("created_at", "updated_at", "completed_at"):
        if isinstance(d.get(k), datetime):
            d[k] = d[k].isoformat()
    hist = d.get("status_history") or []
    for h in hist:
        if isinstance(h.get("at"), datetime):
            h["at"] = h["at"].isoformat()
    return d


@router.get("/api/room-requests")
async def list_requests(
    status: str | None = None,
    department: str | None = None,
    room_id: str | None = None,
    limit: int = 200,
    current_user=Depends(get_current_user),
):
    await _ensure_indexes()
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id}
    if status:
        if status == "open":
            q["status"] = {"$in": ["new", "assigned", "in_progress"]}
        else:
            q["status"] = status
    if department:
        q["department"] = department
    if room_id:
        q["room_id"] = room_id

    cursor = raw_db[COLL].find(q).sort("created_at", -1).limit(min(limit, 500))
    items = [_serialize(d) async for d in cursor]
    return {"items": items, "count": len(items)}


@router.get("/api/room-requests/stats/summary")
async def stats_summary(current_user=Depends(get_current_user)):
    await _ensure_indexes()
    tenant_id = _tenant_of(current_user)
    pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {
            "$group": {
                "_id": {"status": "$status", "department": "$department"},
                "count": {"$sum": 1},
            }
        },
    ]
    by_status: dict = {}
    by_department: dict = {}
    total = 0
    async for row in raw_db[COLL].aggregate(pipeline):
        s = row["_id"]["status"]
        d = row["_id"]["department"]
        c = row["count"]
        by_status[s] = by_status.get(s, 0) + c
        by_department.setdefault(d, {"total": 0, "open": 0})
        by_department[d]["total"] += c
        if s in ("new", "assigned", "in_progress"):
            by_department[d]["open"] += c
        total += c
    return {
        "total": total,
        "by_status": by_status,
        "by_department": by_department,
        "open": sum(by_status.get(s, 0) for s in ("new", "assigned", "in_progress")),
    }


@router.get("/api/room-requests/{request_id}")
async def get_request(request_id: str, current_user=Depends(get_current_user)):
    tenant_id = _tenant_of(current_user)
    d = await raw_db[COLL].find_one({"_id": request_id, "tenant_id": tenant_id})
    if not d:
        raise HTTPException(status_code=404, detail="Talep bulunamadı")
    return _serialize(d)


class RequestUpdate(BaseModel):
    status: str | None = None
    assigned_to: str | None = None
    priority: str | None = None
    department: str | None = None
    note: str | None = None


@router.patch("/api/room-requests/{request_id}")
async def update_request(
    request_id: str,
    payload: RequestUpdate,
    current_user=Depends(get_current_user),
):
    tenant_id = _tenant_of(current_user)
    doc = await raw_db[COLL].find_one({"_id": request_id, "tenant_id": tenant_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Talep bulunamadı")

    now = datetime.now(UTC)
    update: dict = {"updated_at": now}
    staff_name = getattr(current_user, "name", None) or getattr(current_user, "email", None) or "staff"
    history_entry = {"at": now, "by": staff_name}

    if payload.status is not None:
        if payload.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Geçersiz durum: {payload.status}")
        update["status"] = payload.status
        history_entry["status"] = payload.status
        if payload.status == "completed":
            update["completed_at"] = now
    if payload.assigned_to is not None:
        update["assigned_to"] = payload.assigned_to or None
        history_entry["assigned_to"] = payload.assigned_to
        if doc.get("status") == "new" and "status" not in update:
            update["status"] = "assigned"
            history_entry["status"] = "assigned"
    if payload.priority is not None:
        if payload.priority not in VALID_PRIORITIES:
            raise HTTPException(status_code=400, detail="Geçersiz öncelik")
        update["priority"] = payload.priority
    if payload.department is not None:
        update["department"] = payload.department
    if payload.note:
        history_entry["note"] = payload.note

    if len(update) == 1 and not payload.note:  # sadece updated_at ve note yoksa
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")

    await raw_db[COLL].update_one(
        {"_id": request_id, "tenant_id": tenant_id},
        {"$set": update, "$push": {"status_history": history_entry}},
    )

    if payload.note:
        try:
            from domains.guest.messaging import guest_requests as _gr
            property_id = doc.get("property_id")
            if not property_id:
                room = await raw_db["rooms"].find_one({"id": doc["room_id"], "tenant_id": tenant_id})
                property_id = room.get("property_id") if room else None

            if not property_id:
                raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

            await _gr.add_guest_message(
                tenant_id=tenant_id,
                property_id=property_id,
                room_id=doc["room_id"],
                room_number=doc.get("room_number"),
                sender_type="staff",
                body=payload.note,
                booking_id=doc.get("booking_id"),
                sender_name=staff_name,
            )
            await _gr.emit_guest_requests_ping(tenant_id, doc["room_id"])
        except Exception as e:
            logger.warning(f"[room_qr] Error sending note to guest thread: {e}")

    try:
        from core.ws_rooms import tenant_broadcast_room
        from websocket_server import sio  # type: ignore

        # Task #367: same tenant broadcast room as the room_request:new emit.
        await sio.emit(
            "room_request:update",
            {
                "id": request_id,
                "status": update.get("status"),
            },
            room=tenant_broadcast_room(tenant_id),
        )
    except Exception:
        pass

    updated = await raw_db[COLL].find_one({"_id": request_id, "tenant_id": tenant_id})
    return _serialize(updated)


# ═══════════════════════════════════════════════════════════════
# QR KOD ÜRETİMİ (staff)
# ═══════════════════════════════════════════════════════════════


@router.get("/api/rooms/{room_id}/qr-code")
async def room_qr_code(
    room_id: str,
    request: Request,
    current_user=Depends(get_current_user),
):
    """Oda için QR kod (URL + PNG base64)."""
    tenant_id = _tenant_of(current_user)
    room = await raw_db["rooms"].find_one({"id": room_id, "tenant_id": tenant_id})
    if not room:
        raise HTTPException(status_code=404, detail="Oda bulunamadı")

    salt = await _get_qr_salt(tenant_id)
    slug = await _hotel_slug(tenant_id)
    url = _guest_url_with_salt(request, tenant_id, room_id, salt, slug)
    png = generate_qr_code(url)
    return {
        "tenant_id": tenant_id,  # kanonik internal tenant kimliği — public URL için kullan
        "room_id": room_id,
        "room_number": room.get("room_number"),
        "url": url,
        "qr_png_base64": png,  # data:image/png;base64,...
        "token": _token_for(tenant_id, room_id, salt),
    }


@router.get("/api/rooms/qr-codes/bulk")
async def all_room_qr_codes(
    request: Request,
    current_user=Depends(get_current_user),
):
    """Tüm odalar için QR URL listesi (toplu yazdırma için).

    v95 — Projection (sadece gerekli alanlar) + tek to_list batch fetch.
    """
    tenant_id = _tenant_of(current_user)
    rooms = (
        await raw_db["rooms"]
        .find(
            {"tenant_id": tenant_id, "is_active": {"$ne": False}},
            {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "floor": 1},
        )
        .sort("room_number", 1)
        .to_list(2000)
    )
    salt = await _get_qr_salt(tenant_id)
    slug = await _hotel_slug(tenant_id)
    items = [
        {
            "room_id": room.get("id"),
            "room_number": room.get("room_number"),
            "room_type": room.get("room_type"),
            "floor": room.get("floor"),
            "url": _guest_url_with_salt(request, tenant_id, room.get("id"), salt, slug),
        }
        for room in rooms
    ]
    return {"items": items, "count": len(items)}


@router.post("/api/rooms/qr/rotate-secret")
async def rotate_room_qr_secret(
    current_user=Depends(get_current_user),
):
    """Bu tenant'ın oda-QR HMAC tuzunu döndürür (KVKK/güvenlik rotasyonu).

    Tenant-scoped: yalnız çağıranın tenant sırrı döner. Rotasyon sonrası bu
    tenant'a ait daha önce üretilmiş/yazdırılmış tüm QR tokenları
    `_verify_token` HMAC mismatch ile reddedilir; personel QR endpoint'inden
    yeniden basılmalıdır. Tuz değeri ASLA yanıtta dönmez (server-side sır).
    """
    tenant_id = _tenant_of(current_user)
    new_salt = secrets.token_hex(32)
    now = datetime.now(UTC).isoformat()
    existing = await raw_db[_QR_SALT_COLL].find_one({"tenant_id": tenant_id})
    version = int((existing or {}).get("version") or 0) + 1
    await raw_db[_QR_SALT_COLL].update_one(
        {"tenant_id": tenant_id},
        {
            "$set": {
                "tenant_id": tenant_id,
                "salt": new_salt,
                "version": version,
                "rotated_at": now,
                "rotated_by": getattr(current_user, "id", None),
            }
        },
        upsert=True,
    )
    return {"tenant_id": tenant_id, "version": version, "rotated_at": now, "rotated": True}
