"""
Misafir Oda Talepleri — Personel & Admin HTTP Uçları
====================================================
Personel iç-sohbet widget'ının "Misafir Talepleri" akışını besleyen RBAC/ACL'li
uçlar + admin'in görünür rolleri yapılandırdığı ayar uçları.

İş mantığı ``guest_requests.py``'de; misafir (public, QR token'lı) uçları
``routers/room_qr_requests.py``'de. Bu router ``router_registry.py`` üzerinden
``/api`` altına mount edilir.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.database import _raw_db as raw_db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

from domains.guest.messaging import guest_requests as gr

logger = logging.getLogger("guest_requests_router")

router = APIRouter(prefix="/api", tags=["Guest Requests"])


# ── Admin: görünürlük ayarı ────────────────────────────────────────────

class VisibleRolesUpdate(BaseModel):
    visible_roles: list[str] = Field(default_factory=list)


@router.get("/messaging/guest-requests/settings")
async def get_guest_request_settings(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_users")),  # admin/super_admin only
):
    """Yapılandırılmış görünür roller + seçilebilir rol kataloğu (admin)."""
    roles = await gr.get_visible_roles(current_user.tenant_id)
    available = [
        {"value": r, "label": gr.STAFF_ROLE_LABELS.get(r, r)}
        for r in sorted(gr.STAFF_ROLE_WHITELIST)
    ]
    return {
        "visible_roles": roles,
        "available_roles": available,
        "always_allowed": sorted(gr.ALWAYS_ALLOWED_ROLES),
    }


@router.put("/messaging/guest-requests/settings")
async def update_guest_request_settings(
    data: VisibleRolesUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_users")),  # admin/super_admin only
):
    """Görünür rolleri yapılandırır (admin). Whitelist dışı rol 422."""
    saved = await gr.set_visible_roles(current_user.tenant_id, data.visible_roles)
    return {"success": True, "visible_roles": saved}


# ── Personel: erişim + thread akışı ────────────────────────────────────

@router.get("/messaging/guest-requests/access")
async def guest_request_access(
    current_user: User = Depends(get_current_user),
):
    """İstemci sekmesini gizleyebilsin diye yetki bilgisi (403 üretmez)."""
    visible = await gr.get_visible_roles(current_user.tenant_id)
    return {"can_view": gr.can_view(current_user, visible)}


@router.get("/messaging/guest-requests/threads")
async def list_guest_request_threads(
    current_user: User = Depends(gr.require_guest_request_access),
):
    """Oda bazlı thread özetleri + okunmamış misafir mesajı sayıları."""
    threads = await gr.list_threads_for_staff(current_user.tenant_id)
    unread_map = await gr.count_unread_for_staff(
        current_user.tenant_id, current_user.id
    )
    total_unread = 0
    for t in threads:
        u = int(unread_map.get(t["room_id"], 0) or 0)
        t["unread"] = u
        total_unread += u
    return {"threads": threads, "total_unread": total_unread}


@router.get("/messaging/guest-requests/threads/{room_id}")
async def get_guest_request_thread(
    room_id: str,
    current_user: User = Depends(gr.require_guest_request_access),
):
    """Bir odanın tam mesaj geçmişi (personel: oda-scoped, tüm booking'ler)."""
    messages = await gr.get_thread_messages(
        current_user.tenant_id,
        room_id,
        viewer_user_id=current_user.id,
    )
    room_number = None
    for m in reversed(messages):
        if m.get("room_number"):
            room_number = m["room_number"]
            break
    return {"room_id": room_id, "room_number": room_number, "messages": messages}


class ReplyBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=gr.MAX_MESSAGE_LEN)


@router.post("/messaging/guest-requests/threads/{room_id}/reply")
async def reply_guest_request_thread(
    room_id: str,
    body: ReplyBody,
    current_user: User = Depends(gr.require_guest_request_access),
):
    """Personel yanıtı — misafir tarafında görünür (aktif booking'e bağlanır)."""
    text = (body.message or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Mesaj boş olamaz")

    # Yanıtı misafirin AKTİF booking'ine bağla: odadaki en son misafir
    # mesajının booking_id'sini kullan (misafir booking-scoped GET ile görür).
    last_guest = await raw_db[gr.GR_COLL].find_one(
        {
            "tenant_id": current_user.tenant_id,
            "room_id": room_id,
        },
        sort=[("created_at", -1)],
    )
    if not last_guest:
        raise HTTPException(status_code=404, detail="Bu oda için talep bulunamadı")
    booking_id = last_guest.get("booking_id")
    room_number = last_guest.get("room_number")

    doc = await gr.add_guest_message(
        tenant_id=current_user.tenant_id,
        room_id=room_id,
        room_number=room_number,
        sender_type="staff",
        body=text,
        booking_id=booking_id,
        sender_user_id=current_user.id,
        sender_name=current_user.name,
    )
    await gr.emit_guest_requests_ping(current_user.tenant_id, room_id)
    return {"success": True, "message": gr._serialize(doc, viewer_user_id=current_user.id)}


@router.post("/messaging/guest-requests/threads/{room_id}/mark-read")
async def mark_guest_request_thread_read(
    room_id: str,
    current_user: User = Depends(gr.require_guest_request_access),
):
    """Odadaki misafir mesajlarını bu personel için okundu işaretler."""
    modified = await gr.mark_thread_read(
        current_user.tenant_id, room_id, current_user.id
    )
    return {"success": True, "modified": modified}
