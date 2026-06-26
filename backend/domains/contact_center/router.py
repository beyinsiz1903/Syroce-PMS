"""
Domain Router: Syroce Contact Center (omnichannel) — Faz 1 (WhatsApp MVP).

Çift kapı:
1. Entitlement: ``/api/contact-center/`` yolu ROUTE_MODULE_MAP üzerinden
   ``contact_center`` modülüne bağlı (kiracı planı/abonelik kontrolü ASGI
   middleware'de — entitled değilse 403 ENTITLEMENT_DENIED).
2. RBAC: ``require_module("contact_center")`` rol allowlist'i (call_center_agent,
   front_desk/resepsiyon, supervisor, admin, super_admin). Gönderim ucu ayrıca
   ``require_op("manage_contact_center")`` ile MANAGE_CONTACT_CENTER ister.

Faz 1: gerçek WhatsApp transport'una köprülü okuma + gönderim. Tüm sorgular
kiracıya göre filtrelenir. PII (telefon/gövde/ad) YALNIZCA okuma sınırındaki
DTO'da çözülür, maskelenir ve ASLA ciphertext/_id/_hash dışarı verilmez.
Gönderim başarısızsa fake-green YOK — onur açıklamasıyla 502 döner.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.security import _is_super_admin, get_current_user
from domains.contact_center.provider import get_communication_provider
from domains.contact_center.read_models import (
    conversation_to_dto,
    message_to_dto,
)
from models.enums import MessageDirection, MessageStatus
from models.schemas import User
from modules.pms_core.role_permission_service import (
    RolePermissionService,
    require_module,
    require_op,
)
from security.field_encryption import get_field_encryption_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["contact-center-domain"])

_CHANNEL_WHATSAPP = "whatsapp"
_SESSION_WINDOW = timedelta(hours=24)


def _can_reveal_phone(user: User) -> bool:
    """Tam telefon numarasını açma yetkisi (PII minimizasyonu).

    Numara varsayılan maskelidir; tam haliyle açılması yalnızca operatör seviyesi
    ``MANAGE_CONTACT_CENTER`` iznine bağlıdır — salt-görüntüleme
    (``VIEW_CONTACT_CENTER``) tek başına YETMEZ. Böylece ileride salt-okuyan bir
    rol eklenirse misafir telefonu otomatik korunur. Super admin tam yetkilidir.
    """
    if _is_super_admin(user):
        return True
    return RolePermissionService().check_permission(
        getattr(user.role, "value", str(user.role)),
        "manage_contact_center",
        granted_permissions=getattr(user, "granted_permissions", None),
    )


class SendWhatsAppMessage(BaseModel):
    """Giden WhatsApp gönderim gövdesi (alıcı sunucuda konuşmadan çözülür)."""

    body: str | None = None
    template_name: str | None = None
    language_code: str = "tr"
    template_components: list | None = None


def _as_aware(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


async def _is_within_session_window(tenant_id: str, conversation_id: str) -> bool:
    """Son GELEN mesaj 24 saat içinde mi? (serbest-metin penceresi)."""
    doc = await db.contact_center_messages.find_one(
        {
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "direction": MessageDirection.INBOUND.value,
        },
        sort=[("created_at", -1)],
    )
    if not doc:
        return False
    last = _as_aware(doc.get("created_at"))
    if last is None:
        return False
    return (datetime.now(UTC) - last) <= _SESSION_WINDOW


@router.get("/contact-center/health")
async def contact_center_health(
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Modül + sağlayıcı sağlığı (sır/PII içermez)."""
    provider = get_communication_provider("whatsapp")
    health = await provider.check_health(db=db, tenant_id=current_user.tenant_id)
    return {
        "module": "contact_center",
        "status": "ok",
        "phase": "1",
        "provider": health,
    }


@router.get("/contact-center/conversations")
async def list_conversations(
    status: str | None = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Kiracıya ait konuşmaları listeler (allowlist DTO, telefon maskeli).

    Gerçek veriden okur; kayıt yoksa boş liste döner (fake data YOK). PII
    yalnızca okuma sınırında çözülür; ciphertext/_id/_hash dışarı verilmez.
    """
    safe_limit = max(1, min(int(limit or 50), 200))
    query: dict = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status
    cursor = (
        db.contact_center_conversations.find(query)
        .sort("last_message_at", -1)
        .limit(safe_limit)
    )
    docs = await cursor.to_list(length=safe_limit)
    svc = get_field_encryption_service()
    items = [conversation_to_dto(d, svc) for d in docs]
    return {"count": len(items), "items": items}


@router.get("/contact-center/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    msg_limit: int = 100,
    reveal_phone: bool = False,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Tek konuşma + mesajları (okuma sınırında decrypt, allowlist DTO).

    Mesaj gövdesi yalnızca burada çözülür. ``reveal_phone=true`` tam numarayı açar
    AMA yalnızca ``MANAGE_CONTACT_CENTER`` izni olan operatör için (PII minimizasyonu;
    toplu liste ucunda numara ASLA açılmaz). DB'ye yan-etki yazımı yapılmaz; PII
    açma talebi/sonucu yalnızca PII'siz (yalnız user/konuşma id'si) iz bırakır.
    """
    conv = await db.contact_center_conversations.find_one(
        {"id": conversation_id, "tenant_id": current_user.tenant_id}
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Konuşma bulunamadı")

    safe_msg_limit = max(1, min(int(msg_limit or 100), 500))
    msg_cursor = (
        db.contact_center_messages.find(
            {"tenant_id": current_user.tenant_id, "conversation_id": conversation_id}
        )
        .sort("created_at", 1)
        .limit(safe_msg_limit)
    )
    msg_docs = await msg_cursor.to_list(length=safe_msg_limit)
    svc = get_field_encryption_service()

    reveal = bool(reveal_phone) and _can_reveal_phone(current_user)
    if reveal_phone:
        # KVKK izlenebilirliği: PII açma talebi + sonucu (numara DEĞİL) loglanır.
        logger.info(
            "contact-center reveal_phone: user=%s conv=%s sonuç=%s",
            current_user.id,
            conversation_id,
            "acildi" if reveal else "reddedildi",
        )
    return {
        "conversation": conversation_to_dto(conv, svc, reveal_phone=reveal),
        "messages": [message_to_dto(m, svc) for m in msg_docs],
    }


@router.post("/contact-center/conversations/{conversation_id}/messages")
async def send_conversation_message(
    conversation_id: str,
    payload: SendWhatsAppMessage,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
    _perm=Depends(require_op("manage_contact_center")),
):
    """Konuşmaya WhatsApp yanıtı gönderir (MANAGE_CONTACT_CENTER kapılı).

    Alıcı sunucuda konuşmadan çözülür (istemci ham numara/tenant geçemez). 24
    saatlik pencere açıksa serbest metin; kapalıysa onaylı template gerekir.
    Gönderim başarısızsa kayıt FAILED olarak tutulur ve 502 döner (fake-green YOK).
    """
    tenant_id = current_user.tenant_id
    conv = await db.contact_center_conversations.find_one(
        {"id": conversation_id, "tenant_id": tenant_id}
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Konuşma bulunamadı")
    if conv.get("channel") != _CHANNEL_WHATSAPP:
        raise HTTPException(
            status_code=400, detail="Bu uç yalnızca WhatsApp konuşmaları içindir"
        )

    svc = get_field_encryption_service()
    try:
        recipient = (
            svc.decrypt_value(conv.get("caller_id_enc") or "")
            if conv.get("caller_id_enc")
            else ""
        )
    except Exception:
        # Decrypt hatası: alıcı çözülemedi → fail-closed 409 (500 sızdırma YOK),
        # PII'siz log. Henüz gönderim denenmediği için FAILED kaydı yazılmaz.
        logger.warning(
            "contact-center: alıcı numarası decrypt edilemedi conv=%s", conversation_id
        )
        recipient = ""
    if not recipient:
        raise HTTPException(status_code=409, detail="Alıcı numarası çözülemedi")

    in_session = await _is_within_session_window(tenant_id, conversation_id)
    if in_session:
        if not payload.body:
            raise HTTPException(status_code=400, detail="Mesaj gövdesi gerekli")
    else:
        if not payload.template_name:
            raise HTTPException(
                status_code=409,
                detail="24 saatlik pencere kapalı; onaylı template (HSM) gerekir",
            )

    provider = get_communication_provider("whatsapp")
    try:
        result = await provider.send_whatsapp(
            db=db,
            tenant_id=tenant_id,
            recipient=recipient,
            body=payload.body,
            in_session=in_session,
            template_name=payload.template_name,
            language_code=payload.language_code,
            template_components=payload.template_components,
        )
    except Exception as exc:
        # Beklenmeyen transport/sağlayıcı istisnası da FAILED olarak KALICILAŞTIRILIR
        # (aşağıdaki ortak yol) ki ajan arayüzünde "iletilemedi" gerçeği görünsün —
        # fake-green YOK. PII'siz log: yalnızca istisna SINIF ADI yazılır; traceback /
        # exception metni (alıcı telefonu, URL ?token=..., yanıt gövdesi sızabilir)
        # ASLA loglanmaz. Persist edilen error ve HTTP detail de generic kalır.
        logger.error(
            "contact-center: WhatsApp gönderiminde beklenmeyen hata (%s)",
            type(exc).__name__,
        )
        result = {"success": False, "error": "Gönderim sırasında beklenmeyen hata"}

    now = datetime.now(UTC)
    success = bool(result.get("success"))
    error_detail = result.get("error") or result.get("detail")
    msg_doc = {
        "id": str(uuid4()),
        "tenant_id": tenant_id,
        "conversation_id": conversation_id,
        "channel": _CHANNEL_WHATSAPP,
        "direction": MessageDirection.OUTBOUND.value,
        "status": MessageStatus.SENT.value if success else MessageStatus.FAILED.value,
        "body_enc": svc.encrypt_value(payload.body) if payload.body else None,
        "sender_agent_id": current_user.id,
        "provider_message_id": result.get("provider_message_id"),
        "media_refs": [],
        "error": None if success else (error_detail or "")[:500] or None,
        "created_at": now,
        "sent_at": now if success else None,
    }
    await db.contact_center_messages.insert_one(msg_doc)

    if success:
        await db.contact_center_conversations.update_one(
            {"id": conversation_id, "tenant_id": tenant_id},
            {"$set": {"last_message_at": now, "updated_at": now}},
        )
        return {
            "success": True,
            "message_id": msg_doc["id"],
            "provider_message_id": msg_doc["provider_message_id"],
            "status": msg_doc["status"],
        }

    # Fail-closed: sahte başarı yok — onur açıklamasıyla 502.
    raise HTTPException(
        status_code=502,
        detail=error_detail or "WhatsApp gönderimi başarısız",
    )
