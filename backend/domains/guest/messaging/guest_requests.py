"""
Misafir Oda Talepleri — Sohbet Entegrasyonu (Guest Room Requests → Internal Chat)
=================================================================================
Misafirin oda QR'ı ile ilettiği talepler, personelin iç-sohbet widget'ında
oda numarasına göre gruplanmış "Misafir Talepleri" akışı olarak görünür ve
iki yönlü mesajlaşmayı (misafir <-> personel) taşır.

Bu modül paylaşılan iş mantığını barındırır; HTTP route'ları iki yerde:
  - personel uçları   → ``guest_requests_router.py`` (RBAC + ACL'li)
  - misafir uçları     → ``routers/room_qr_requests.py`` (QR token'lı, public)

Tasarım kuralları (architect onaylı):
  - Tüm DB erişimi ``_raw_db`` + AÇIK ``tenant_id`` ile (tenant izolasyonu).
  - Misafir tarafı thread BOOKING-SCOPED: oda QR token'ı kalıcıdır; eski
    misafirin mesajları yeni misafire SIZMAMALI. Booking yoksa kısa zaman
    penceresi (24s) uygulanır.
  - Departman bildirimi (internal_messages) yalnızca oda no + kategori taşır;
    misafir adı/telefon/açıklama (PII) ASLA websocket'e veya departman
    mesajına konmaz — PII sadece ACL-kısıtlı ``guest_room_messages`` ve
    booking-scoped misafir GET'inde döner.
  - QR departmanı -> iç-sohbet departmanı AÇIK eşlenir; ``to_department``
    asla None değildir (front-office catch-all = Reception).
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException

from core.database import _raw_db as raw_db
from core.security import get_current_user
from models.schemas import User

logger = logging.getLogger("guest_requests")

# Koleksiyon: misafir<->personel mesaj thread'i (oda bazlı, booking referanslı)
GR_COLL = "guest_room_messages"

# Görünürlük ayarı hotel_settings dokümanında tutulur (tenant başına tek doc)
SETTINGS_COLL = "hotel_settings"
VISIBLE_ROLES_FIELD = "guest_request_visible_roles"

# Varsayılan: Yönetici + Resepsiyon (Misafir İlişkileri). super_admin/admin
# her zaman yetkilidir (aşağıdaki can_view daima izin verir), ayarda olsun
# olmasın.
DEFAULT_VISIBLE_ROLES: list[str] = ["admin", "front_desk"]

# super_admin/admin görünürlük ayarından BAĞIMSIZ daima yetkilidir.
ALWAYS_ALLOWED_ROLES: frozenset[str] = frozenset({"super_admin", "admin"})

# Admin'in görünürlük ayarında seçebileceği geçerli personel rolleri.
# super_admin (daima yetkili), guest ve agency_* (dış taraf) hariç tutulur.
STAFF_ROLE_WHITELIST: frozenset[str] = frozenset({
    "admin",
    "supervisor",
    "front_desk",
    "housekeeping",
    "sales",
    "finance",
    "procurement",
    "staff",
})

# Ayar ekranında gösterilecek rol etiketleri (TR).
STAFF_ROLE_LABELS: dict[str, str] = {
    "admin": "Yönetici",
    "supervisor": "Süpervizör",
    "front_desk": "Resepsiyon (Misafir İlişkileri)",
    "housekeeping": "Kat Hizmetleri",
    "sales": "Satış",
    "finance": "Finans",
    "procurement": "Satınalma",
    "staff": "Personel",
}

# QR departmanı (CATEGORY_CATALOG.department) -> iç-sohbet departmanı
# (_ROLE_DEPARTMENT_MAPPING değerleri: Reception/Housekeeping/Maintenance/...).
# Front-office catch-all = Reception; eşlenmeyen her şey buraya düşer, böylece
# ``to_department`` ASLA None olmaz.
_INTERNAL_DEPT_FALLBACK = "Reception"
QR_DEPT_TO_INTERNAL: dict[str, str] = {
    "rooms": "Housekeeping",
    "minibar": "Housekeeping",
    "laundry": "Housekeeping",
    "technical": "Maintenance",
    "fnb": "Reception",
    "spa": "Reception",
    "transportation": "Reception",
    "other": "Reception",
}

# Misafir tarafı booking yoksa thread penceresi (saat).
GUEST_THREAD_FALLBACK_WINDOW_HOURS = 24

# Mesaj gövdesi azami uzunluğu (DoS / spam guard).
MAX_MESSAGE_LEN = 2000


def internal_dept_for_qr_department(qr_department: str | None) -> str:
    """QR departmanını iç-sohbet departmanına çevirir. Asla None döndürmez."""
    if not qr_department:
        return _INTERNAL_DEPT_FALLBACK
    return QR_DEPT_TO_INTERNAL.get(str(qr_department), _INTERNAL_DEPT_FALLBACK)


def _role_value(user: Any) -> str | None:
    role = getattr(user, "role", None)
    if role is None:
        return None
    return str(getattr(role, "value", role))


def can_view(user: Any, visible_roles: list[str]) -> bool:
    """Kullanıcı misafir-talepleri akışını görebilir mi?

    super_admin/admin daima görür (ayardan bağımsız). Diğer roller yalnızca
    admin'in seçtiği ``visible_roles`` listesindeyse görür.
    """
    role = _role_value(user)
    if role is None:
        return False
    if role in ALWAYS_ALLOWED_ROLES:
        return True
    return role in set(visible_roles or [])


async def get_visible_roles(tenant_id: str) -> list[str]:
    """Tenant için yapılandırılmış görünür rolleri döndürür (yoksa varsayılan)."""
    if not tenant_id:
        return list(DEFAULT_VISIBLE_ROLES)
    doc = await raw_db[SETTINGS_COLL].find_one(
        {"tenant_id": tenant_id},
        {VISIBLE_ROLES_FIELD: 1},
    )
    if not doc or VISIBLE_ROLES_FIELD not in doc:
        return list(DEFAULT_VISIBLE_ROLES)
    roles = doc.get(VISIBLE_ROLES_FIELD)
    if not isinstance(roles, list):
        return list(DEFAULT_VISIBLE_ROLES)
    # Yalnızca geçerli personel rollerini geri ver (eski/çöp değerleri ele).
    return [r for r in roles if r in STAFF_ROLE_WHITELIST]


async def set_visible_roles(tenant_id: str, roles: list[str]) -> list[str]:
    """Görünür rolleri yapılandırır. Whitelist dışı rol 422 ile reddedilir."""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id gerekli")
    cleaned: list[str] = []
    for r in roles or []:
        rv = str(r)
        if rv not in STAFF_ROLE_WHITELIST:
            raise HTTPException(
                status_code=422,
                detail=f"Geçersiz rol: {rv}",
            )
        if rv not in cleaned:
            cleaned.append(rv)
    await raw_db[SETTINGS_COLL].update_one(
        {"tenant_id": tenant_id},
        {"$set": {
            VISIBLE_ROLES_FIELD: cleaned,
            "tenant_id": tenant_id,
        }},
        upsert=True,
    )
    return cleaned


async def require_guest_request_access(
    current_user: User = Depends(get_current_user),
) -> User:
    """Misafir-talepleri akışına erişimi olan personeli doğrulayan dependency.

    super_admin/admin daima geçer; diğer roller yalnızca admin'in
    yapılandırdığı görünür rollerdeyse. Aksi halde 403 (server-side enforce).
    """
    visible = await get_visible_roles(current_user.tenant_id)
    if not can_view(current_user, visible):
        raise HTTPException(
            status_code=403,
            detail="Misafir taleplerini görüntüleme yetkiniz yok.",
        )
    return current_user


def _serialize(msg: dict, *, viewer_user_id: str | None = None) -> dict:
    """Mongo dokümanını API gövdesine çevirir (_id düşer, tarih isoformat)."""
    created = msg.get("created_at")
    if isinstance(created, datetime):
        created_out = created.astimezone(UTC).isoformat()
    else:
        created_out = created
    read_by = msg.get("read_by") or []
    out = {
        "id": msg.get("id"),
        "room_id": msg.get("room_id"),
        "room_number": msg.get("room_number"),
        "booking_id": msg.get("booking_id"),
        "sender_type": msg.get("sender_type"),
        "sender_name": msg.get("sender_name"),
        "body": msg.get("body"),
        "category": msg.get("category"),
        "department": msg.get("department"),
        "priority": msg.get("priority"),
        "request_id": msg.get("request_id"),
        "created_at": created_out,
    }
    if viewer_user_id is not None:
        # Personel tarafı: misafir mesajını ben okudum mu?
        out["read"] = (
            msg.get("sender_type") == "staff"
            or viewer_user_id in read_by
        )
    return out


async def add_guest_message(
    *,
    tenant_id: str,
    room_id: str,
    room_number: str | None,
    sender_type: str,
    body: str,
    booking_id: str | None = None,
    sender_user_id: str | None = None,
    sender_name: str | None = None,
    request_id: str | None = None,
    category: str | None = None,
    department: str | None = None,
    priority: str | None = None,
) -> dict:
    """guest_room_messages koleksiyonuna tek mesaj ekler ve dokümanı döndürür."""
    now = datetime.now(UTC)
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "room_id": room_id,
        "room_number": room_number,
        "booking_id": booking_id,
        "sender_type": sender_type,
        "sender_user_id": sender_user_id,
        "sender_name": sender_name,
        "body": body,
        "request_id": request_id,
        "category": category,
        "department": department,
        "priority": priority,
        "created_at": now,
        "read_by": [],
    }
    await raw_db[GR_COLL].insert_one(doc)
    return doc


async def list_threads_for_staff(tenant_id: str, *, limit: int = 100) -> list[dict]:
    """Oda bazlı thread özetleri: son mesaj + okunmamış misafir mesajı sayısı.

    En son etkinliğe göre sıralı. PII (misafir mesaj gövdesi) yalnızca ACL'li
    personel ulaşacağı için döner (router require_guest_request_access ile gate'li).
    """
    pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$sort": {"created_at": 1}},
        {"$group": {
            "_id": "$room_id",
            "room_number": {"$last": "$room_number"},
            "last_body": {"$last": "$body"},
            "last_sender_type": {"$last": "$sender_type"},
            "last_created_at": {"$last": "$created_at"},
            "last_category": {"$last": "$category"},
            "total": {"$sum": 1},
        }},
        {"$sort": {"last_created_at": -1}},
        {"$limit": int(limit)},
    ]
    rooms: list[dict] = []
    async for row in raw_db[GR_COLL].aggregate(pipeline):
        last_created = row.get("last_created_at")
        if isinstance(last_created, datetime):
            last_created = last_created.astimezone(UTC).isoformat()
        rooms.append({
            "room_id": row.get("_id"),
            "room_number": row.get("room_number"),
            "last_body": row.get("last_body"),
            "last_sender_type": row.get("last_sender_type"),
            "last_category": row.get("last_category"),
            "last_created_at": last_created,
            "total": row.get("total", 0),
        })
    return rooms


async def count_unread_for_staff(tenant_id: str, user_id: str) -> dict[str, int]:
    """Oda başına okunmamış misafir mesajı sayısı (staff için)."""
    pipeline = [
        {"$match": {
            "tenant_id": tenant_id,
            "sender_type": "guest",
            "read_by": {"$ne": user_id},
        }},
        {"$group": {"_id": "$room_id", "unread": {"$sum": 1}}},
    ]
    out: dict[str, int] = {}
    async for row in raw_db[GR_COLL].aggregate(pipeline):
        out[row.get("_id")] = row.get("unread", 0)
    return out


async def get_thread_messages(
    tenant_id: str,
    room_id: str,
    *,
    booking_id: str | None = None,
    null_booking_only: bool = False,
    since: datetime | None = None,
    limit: int = 300,
    viewer_user_id: str | None = None,
) -> list[dict]:
    """Bir odanın mesaj thread'i (kronolojik).

    ``booking_id`` verilirse BOOKING-SCOPED filtreler (misafir tarafı: eski
    misafirin mesajını gizler). ``null_booking_only`` verilirse yalnızca
    booking'siz mesajlar (misafir tarafı, aktif booking yoksa: önceki bir
    booking'e bağlı mesajlar gizlenir). ``since`` verilirse zaman penceresi
    uygular (booking yoksa misafir tarafı 24s fallback).
    """
    query: dict[str, Any] = {"tenant_id": tenant_id, "room_id": room_id}
    if booking_id is not None:
        query["booking_id"] = booking_id
    elif null_booking_only:
        query["booking_id"] = None
    if since is not None:
        query["created_at"] = {"$gte": since}
    msgs: list[dict] = []
    cursor = raw_db[GR_COLL].find(query).sort("created_at", 1).limit(int(limit))
    async for msg in cursor:
        msgs.append(_serialize(msg, viewer_user_id=viewer_user_id))
    return msgs


async def mark_thread_read(tenant_id: str, room_id: str, user_id: str) -> int:
    """Odadaki tüm misafir mesajlarını bu personel için okundu işaretler."""
    res = await raw_db[GR_COLL].update_many(
        {
            "tenant_id": tenant_id,
            "room_id": room_id,
            "sender_type": "guest",
            "read_by": {"$ne": user_id},
        },
        {"$addToSet": {"read_by": user_id}},
    )
    return int(getattr(res, "modified_count", 0) or 0)


async def emit_guest_requests_ping(tenant_id: str, room_id: str | None = None) -> None:
    """PII-içermeyen içeriksiz websocket ping'i (yetkili istemci REST'ten çeker).

    Tenant broadcast room'una gönderilir (authenticated socket'ler bu odaya
    bağlı). Best-effort: hata yutulur (mesaj zaten DB'de kalıcı).
    """
    try:
        from core.ws_rooms import tenant_broadcast_room
        from websocket_server import sio  # type: ignore

        await sio.emit(
            "guest_requests:updated",
            {
                "tenant_id": tenant_id,
                "room_id": room_id,
                "ts": datetime.now(UTC).isoformat(),
            },
            room=tenant_broadcast_room(tenant_id),
        )
    except Exception as e:  # pragma: no cover - best effort
        logger.debug("guest_requests ping atlandı: %s", e)


async def notify_department(
    *,
    tenant_id: str,
    room_number: str | None,
    qr_department: str | None,
    category_label: str | None,
) -> None:
    """İlgili iç-sohbet departmanına PII-içermeyen bildirim mesajı atar.

    Gövde yalnızca oda no + kategori taşır (misafir adı/telefon/açıklama YOK).
    ``to_department`` asla None değildir (catch-all = Reception).
    """
    dept = internal_dept_for_qr_department(qr_department)
    oda = room_number or "?"
    kat = category_label or "Talep"
    body = f"Yeni misafir talebi — Oda {oda} · {kat}"
    payload = {
        "id": str(uuid.uuid4()),
        "from_user_id": None,
        "from_user_name": "Misafir Talepleri",
        "from_department": "Guest Requests",
        "to_user_id": None,
        "to_user_name": None,
        "to_department": dept,
        "message": body,
        "priority": "normal",
        "message_type": "guest_request",
        "read": False,
        "created_at": datetime.now(UTC).isoformat(),
        "time_ago": "0s ago",
    }
    try:
        from websocket_server import broadcast_internal_message

        await broadcast_internal_message(
            tenant_id,
            payload,
            to_department=dept,
        )
    except Exception as e:  # pragma: no cover - best effort
        logger.debug("departman bildirimi (ws) atlandı: %s", e)
