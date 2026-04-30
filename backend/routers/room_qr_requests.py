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
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from cache_manager import cache as _cache
from core.database import _raw_db as raw_db
from core.security import JWT_SECRET, generate_qr_code, get_current_user

logger = logging.getLogger("room_qr_requests")

# Güvenlik: HMAC için ayrı bir sır değişkeni önerilir; yoksa JWT_SECRET kullanılır.
# Üretim güvenliği için ikisi de yoksa fail-closed davranır.
_QR_SECRET = os.environ.get("ROOM_QR_SECRET") or JWT_SECRET

# IP-bazlı rate limit (Redis-backed → multi-instance dağıtık koruma)
_RL_WINDOW_SEC = 600   # 10 dakika
_RL_MAX_HITS = 20      # 10 dakikada 20 submit / IP+oda

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
        logger.warning(
            "[room_qr] complaint quota counter unavailable — mirror DENIED "
            "(fail-closed) for %s/%s", tenant_id, room_id)
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
        await raw_db[COLL].create_index(
            [("tenant_id", 1), ("created_at", -1)],
            name="rqr_tenant_created")
        await raw_db[COLL].create_index(
            [("tenant_id", 1), ("status", 1), ("created_at", -1)],
            name="rqr_tenant_status_created")
        await raw_db[COLL].create_index(
            [("tenant_id", 1), ("department", 1), ("status", 1)],
            name="rqr_tenant_dept_status")
        await raw_db[COLL].create_index(
            [("tenant_id", 1), ("room_id", 1)],
            name="rqr_tenant_room")
        _INDEXES_READY = True
    except Exception as e:
        # Atlas may reject new collections (cluster limit reached); we skip
        # silently — query still works on tenant_id full scan for empty data.
        logger.debug(f"room_qr_requests index setup skipped: {e}")

# Kategori → Departman eşlemesi (DepartmentType enum değerleriyle uyumlu)
CATEGORY_CATALOG = [
    {"id": "cleaning",     "department": "rooms",         "icon": "sparkles",  "default_priority": "normal"},
    {"id": "towels",       "department": "rooms",         "icon": "shirt",     "default_priority": "normal"},
    {"id": "amenities",    "department": "rooms",         "icon": "package",   "default_priority": "low"},
    {"id": "maintenance",  "department": "technical",     "icon": "wrench",    "default_priority": "normal"},
    {"id": "wifi",         "department": "technical",     "icon": "wifi",      "default_priority": "normal"},
    {"id": "tv",           "department": "technical",     "icon": "tv",        "default_priority": "low"},
    {"id": "ac_heating",   "department": "technical",     "icon": "thermometer","default_priority": "normal"},
    {"id": "food_order",   "department": "fnb",           "icon": "utensils",  "default_priority": "normal"},
    {"id": "drinks",       "department": "fnb",           "icon": "wine",      "default_priority": "normal"},
    {"id": "minibar",      "department": "minibar",       "icon": "beer",      "default_priority": "low"},
    {"id": "laundry",      "department": "laundry",       "icon": "shirt",     "default_priority": "normal"},
    {"id": "transport",    "department": "transportation","icon": "car",       "default_priority": "normal"},
    {"id": "reception",    "department": "other",         "icon": "bell",      "default_priority": "normal"},
    {"id": "spa",          "department": "spa",           "icon": "heart",     "default_priority": "low"},
    {"id": "complaint",    "department": "other",         "icon": "alert",     "default_priority": "high"},
    {"id": "other",        "department": "other",         "icon": "message",   "default_priority": "normal"},
]

CATEGORY_MAP = {c["id"]: c for c in CATEGORY_CATALOG}
VALID_STATUSES = {"new", "assigned", "in_progress", "completed", "cancelled"}
VALID_PRIORITIES = {"low", "normal", "high", "urgent"}

# Çoklu dil etiketleri (10 dil için başlangıç seti — eklenebilir)
CATEGORY_LABELS = {
    "cleaning":    {"tr": "Oda Temizliği",       "en": "Room Cleaning",     "de": "Zimmerreinigung",    "ru": "Уборка номера",     "ar": "تنظيف الغرفة"},
    "towels":      {"tr": "Havlu / Çarşaf",      "en": "Towels / Linens",   "de": "Handtücher",         "ru": "Полотенца",         "ar": "مناشف"},
    "amenities":   {"tr": "Amenity (Sabun vb.)", "en": "Amenities",         "de": "Pflegeprodukte",     "ru": "Косметика",         "ar": "مستلزمات"},
    "maintenance": {"tr": "Arıza / Tamir",       "en": "Maintenance",       "de": "Wartung",            "ru": "Ремонт",            "ar": "صيانة"},
    "wifi":        {"tr": "İnternet / Wi-Fi",    "en": "Internet / Wi-Fi",  "de": "WLAN",               "ru": "Wi-Fi",             "ar": "واي فاي"},
    "tv":          {"tr": "Televizyon",          "en": "Television",        "de": "Fernseher",          "ru": "Телевизор",         "ar": "تلفاز"},
    "ac_heating":  {"tr": "Klima / Isıtma",      "en": "AC / Heating",      "de": "Klima / Heizung",    "ru": "Кондиционер",       "ar": "تكييف/تدفئة"},
    "food_order":  {"tr": "Oda Servisi (Yemek)", "en": "Room Service (Food)","de": "Zimmerservice",     "ru": "Обслуживание",      "ar": "خدمة الغرف"},
    "drinks":      {"tr": "İçecek",              "en": "Drinks",            "de": "Getränke",           "ru": "Напитки",           "ar": "مشروبات"},
    "minibar":     {"tr": "Minibar",             "en": "Minibar",           "de": "Minibar",            "ru": "Минибар",           "ar": "ميني بار"},
    "laundry":     {"tr": "Çamaşır / Kuru Tem.", "en": "Laundry",           "de": "Wäscherei",          "ru": "Прачечная",         "ar": "غسيل"},
    "transport":   {"tr": "Transfer / Ulaşım",   "en": "Transport",         "de": "Transport",          "ru": "Транспорт",         "ar": "نقل"},
    "reception":   {"tr": "Resepsiyon",          "en": "Reception",         "de": "Rezeption",          "ru": "Стойка",            "ar": "استقبال"},
    "spa":         {"tr": "SPA / Wellness",      "en": "SPA / Wellness",    "de": "SPA",                "ru": "СПА",               "ar": "سبا"},
    "complaint":   {"tr": "Şikayet / Geri Bildirim","en": "Complaint / Feedback","de": "Beschwerde",      "ru": "Жалоба",            "ar": "شكوى"},
    "other":       {"tr": "Diğer",               "en": "Other",             "de": "Andere",             "ru": "Другое",            "ar": "أخرى"},
}


def _token_for(tenant_id: str, room_id: str) -> str:
    if not _QR_SECRET:
        # Üretimde sır yoksa fail-closed — güvensiz sabit fallback yok
        raise HTTPException(
            status_code=503,
            detail="QR servisi yapılandırılmamış: ROOM_QR_SECRET veya JWT_SECRET gerekir",
        )
    secret = _QR_SECRET.encode("utf-8")
    msg = f"{tenant_id}|{room_id}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()  # tam digest (64 char)


def _verify_token(tenant_id: str, room_id: str, token: str) -> bool:
    if not _QR_SECRET:
        return False
    expected = _token_for(tenant_id, room_id)
    return hmac.compare_digest(expected, token or "")


def _public_url_base(request: Request) -> str:
    env_url = os.environ.get("PUBLIC_APP_URL") or os.environ.get("REPLIT_DEV_DOMAIN")
    if env_url:
        if not env_url.startswith("http"):
            env_url = f"https://{env_url}"
        return env_url.rstrip("/")
    # İstek başlığından türet
    proto = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return f"{proto}://{host}".rstrip("/")


def _guest_url(request: Request, tenant_id: str, room_id: str) -> str:
    base = _public_url_base(request)
    token = _token_for(tenant_id, room_id)
    return f"{base}/g/room/{tenant_id}/{room_id}?t={token}"


async def _find_active_booking(tenant_id: str, room_id: str) -> dict | None:
    """Odadaki aktif rezervasyonu bulur (check-in yapmış misafir)."""
    try:
        b = await raw_db["bookings"].find_one({
            "tenant_id": tenant_id,
            "room_id": room_id,
            "status": {"$in": ["checked_in", "in_house"]},
        })
        return b
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# PUBLIC ENDPOINTS (misafir — auth yok)
# ═══════════════════════════════════════════════════════════════

@router.get("/api/public/room-qr/{tenant_id}/{room_id}")
async def public_room_info(tenant_id: str, room_id: str, t: str = Query(...)):
    """QR tarayıp formu açmak için oda & otel bilgilerini döner."""
    if not _verify_token(tenant_id, room_id, t):
        raise HTTPException(status_code=403, detail="Geçersiz QR token")

    room = await raw_db["rooms"].find_one({"id": room_id, "tenant_id": tenant_id})
    if not room:
        raise HTTPException(status_code=404, detail="Oda bulunamadı")

    tenant = await raw_db["tenants"].find_one({"id": tenant_id}) or {}
    booking = await _find_active_booking(tenant_id, room_id)
    # Misafir gizliliği — QR fiziksel olarak odadaysa "J*** D***" olarak maskelenir
    guest_name_masked = None
    if booking:
        full = booking.get("guest_name") or booking.get("primary_guest_name")
        guest_name_masked = _mask_name(full)

    return {
        "hotel_name": tenant.get("name") or tenant.get("display_name") or "Hotel",
        "hotel_logo": tenant.get("logo_url"),
        "primary_color": tenant.get("primary_color") or "#0ea5e9",
        "room_number": room.get("room_number"),
        "room_type": room.get("room_type"),
        "guest_name": guest_name_masked,
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


class PublicRequestSubmit(BaseModel):
    category: str
    description: str = Field(..., min_length=1, max_length=2000)
    priority: str = "normal"
    language: str = "tr"
    guest_name: str | None = None
    guest_phone: str | None = None


@router.post("/api/public/room-qr/{tenant_id}/{room_id}/submit")
async def public_submit_request(
    tenant_id: str,
    room_id: str,
    payload: PublicRequestSubmit,
    request: Request,
    t: str = Query(...),
):
    """Misafir talep gönderir (giriş gerekmez)."""
    if not _verify_token(tenant_id, room_id, t):
        raise HTTPException(status_code=403, detail="Geçersiz QR token")

    # Rate limit: 10 dk içinde aynı oda+IP için 20 submit (Redis-backed,
    # çoklu instance arasında paylaşımlı). IP'yi trusted-proxy ile al.
    client_ip = _client_ip(request)
    if not _rl_check(f"{room_id}:{client_ip}"):
        raise HTTPException(status_code=429, detail="Çok fazla talep — lütfen sonra deneyin")

    if payload.category not in CATEGORY_MAP:
        raise HTTPException(status_code=400, detail=f"Geçersiz kategori: {payload.category}")

    if payload.priority not in VALID_PRIORITIES:
        payload.priority = "normal"

    room = await raw_db["rooms"].find_one({"id": room_id, "tenant_id": tenant_id})
    if not room:
        raise HTTPException(status_code=404, detail="Oda bulunamadı")

    cat = CATEGORY_MAP[payload.category]
    booking = await _find_active_booking(tenant_id, room_id)
    now = datetime.now(UTC)
    title_label = CATEGORY_LABELS.get(payload.category, {}).get(payload.language, payload.category)

    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "room_id": room_id,
        "room_number": room.get("room_number"),
        "category": payload.category,
        "department": cat["department"],
        "title": f"{title_label} — Oda {room.get('room_number')}",
        "description": payload.description.strip(),
        "priority": payload.priority,
        "status": "new",
        "language": payload.language,
        "guest_name": payload.guest_name or (booking.get("guest_name") if booking else None),
        "guest_phone": payload.guest_phone or (booking.get("guest_phone") if booking else None),
        "booking_id": booking.get("id") if booking else None,
        "assigned_to": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "source": "qr",
        "status_history": [
            {"status": "new", "by": "guest", "at": now, "note": "QR üzerinden gönderildi"}
        ],
    }
    await raw_db[COLL].insert_one(doc)

    # Şikayet kategorisi → service_complaints koleksiyonuna mirror et.
    # Bu sayede misafirden gelen şikayetler "Şikayet Yönetimi" sayfasında
    # SLA, eskalasyon, tazminat ve audit history ile birlikte yönetilebilir.
    # Per-room/day kotası: aynı odadan aynı günde max N mirror; aşılırsa
    # talep kaydı korunur ama şikayet boğulmaz.
    if payload.category == "complaint":
        quota_ok, quota_count = _complaint_quota_check(tenant_id, room_id)
        if not quota_ok:
            logger.warning(
                "[room_qr] complaint mirror quota exceeded for room=%s "
                "(today=%d, limit=%d)",
                room_id, quota_count, _COMPLAINT_QUOTA_PER_ROOM_DAY,
            )
        else:
            try:
                desc = payload.description.strip()
                subject = desc[:80] + ("..." if len(desc) > 80 else "")
                severity_map = {
                    "urgent": "critical", "high": "high",
                    "normal": "medium", "low": "low",
                }
                complaint_doc = {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "source": "guest_qr",
                    "qr_request_id": doc["_id"],
                    "category": "service_recovery",
                    "severity": severity_map.get(payload.priority, "medium"),
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
                    "history": [{
                        "action": "created",
                        "actor_id": None,
                        "actor_name": doc.get("guest_name") or "Misafir",
                        "at": now.isoformat(),
                        "notes": "Misafir tarafından oda QR üzerinden iletildi",
                    }],
                }
                await raw_db["service_complaints"].insert_one(complaint_doc)
                logger.info(
                    f"[room_qr] guest complaint mirrored: {complaint_doc['id']} "
                    f"(quota_today={quota_count}/{_COMPLAINT_QUOTA_PER_ROOM_DAY})"
                )
            except Exception as exc:
                logger.warning(f"[room_qr] complaint mirror failed: {exc}")

    # WebSocket yayını (opsiyonel — varsa)
    try:
        from websocket_server import sio  # type: ignore
        await sio.emit("room_request:new", {
            "id": doc["_id"],
            "tenant_id": tenant_id,
            "room_number": doc["room_number"],
            "category": doc["category"],
            "department": doc["department"],
            "priority": doc["priority"],
        }, room=f"tenant:{tenant_id}")
    except Exception as e:
        logger.debug(f"WS emit atlandı: {e}")

    return {
        "success": True,
        "request_id": doc["_id"],
        "department": doc["department"],
        "message": "Talebiniz alındı, ilgili departmana iletildi.",
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
    items = [ _serialize(d) async for d in cursor ]
    return {"items": items, "count": len(items)}


@router.get("/api/room-requests/stats/summary")
async def stats_summary(current_user=Depends(get_current_user)):
    await _ensure_indexes()
    tenant_id = _tenant_of(current_user)
    pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {
            "_id": {"status": "$status", "department": "$department"},
            "count": {"$sum": 1},
        }},
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
    history_entry = {"at": now, "by": getattr(current_user, "email", None) or "staff"}

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

    if len(update) == 1:  # sadece updated_at
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")

    await raw_db[COLL].update_one(
        {"_id": request_id, "tenant_id": tenant_id},
        {"$set": update, "$push": {"status_history": history_entry}},
    )

    try:
        from websocket_server import sio  # type: ignore
        await sio.emit("room_request:update", {
            "id": request_id, "status": update.get("status"),
        }, room=f"tenant:{tenant_id}")
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

    url = _guest_url(request, tenant_id, room_id)
    png = generate_qr_code(url)
    return {
        "room_id": room_id,
        "room_number": room.get("room_number"),
        "url": url,
        "qr_png_base64": png,  # data:image/png;base64,...
        "token": _token_for(tenant_id, room_id),
    }


@router.get("/api/rooms/qr-codes/bulk")
async def all_room_qr_codes(
    request: Request,
    current_user=Depends(get_current_user),
):
    """Tüm odalar için QR URL listesi (toplu yazdırma için)."""
    tenant_id = _tenant_of(current_user)
    cursor = raw_db["rooms"].find(
        {"tenant_id": tenant_id, "is_active": {"$ne": False}}
    ).sort("room_number", 1)
    items = []
    async for room in cursor:
        rid = room.get("id")
        items.append({
            "room_id": rid,
            "room_number": room.get("room_number"),
            "room_type": room.get("room_type"),
            "floor": room.get("floor"),
            "url": _guest_url(request, tenant_id, rid),
        })
    return {"items": items, "count": len(items)}
