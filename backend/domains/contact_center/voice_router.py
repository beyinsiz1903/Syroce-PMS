"""Contact Center — Faz 2 sesli softphone yönlendiricileri.

İki ayrı router:
- ``router`` (``/api/contact-center/voice/...`` + ``/api/contact-center/calls``):
  KİMLİK-DOĞRULAMALI + RBAC + entitlement kapılı (operatör/ajan uçları).
- ``public_router`` (``/api/voice/...``): Twilio webhook'ları. Auth YOK; gerçeklik
  ``X-Twilio-Signature`` ile doğrulanır (fail-closed). Bu prefix bilinçli olarak
  entitlement ROUTE_MODULE_MAP dışındadır (WhatsApp webhook deseni gibi) — aksi
  halde kimliksiz Twilio çağrısı 403 alırdı.

Doktrin: PII (telefon) ASLA loglanmaz/yayınlanmaz; recording_ref (nesne anahtarı)
ASLA istemciye dönmez (yalnızca ``has_recording`` bool). Yapılandırma yoksa uçlar
fail-closed ``not_configured`` döner; sahte token/yeşil YOK.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, Request, Response

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_module, require_op
from security.field_encryption import get_field_encryption_service

from domains.contact_center.read_models import call_to_dto
from domains.contact_center.voice_config import get_twilio_voice_config
from domains.contact_center.voice_ingest import (
    record_inbound_call,
    update_call_status,
)
from domains.contact_center.voice_provider import TwilioVoiceProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["contact-center-voice"])
public_router = APIRouter(prefix="/api/voice", tags=["contact-center-voice-webhook"])

_XML = "application/xml"


def _public_url(request: Request) -> str:
    """Twilio imzasının doğrulanacağı dış URL'i kurar (proxy-güvenli).

    Twilio, yapılandırdığı tam webhook URL'ine imza atar; Replit/ters-proxy ardında
    ``request.url`` iç şemayı taşıyabilir, bu yüzden varsa ``PUBLIC_APP_URL`` esas alınır.
    """
    base = os.getenv("PUBLIC_APP_URL", "").strip().rstrip("/")
    if base:
        return f"{base}{request.url.path}"
    return str(request.url)


async def _notify_incoming_call(tenant_id: str, call_id: str) -> None:
    """Kiracı broadcast room'una PII'siz 'gelen çağrı' ping'i (best-effort).

    Telefon/numara/sır ASLA yayınlanmaz — istemci yetkili REST ucundan çeker.
    """
    try:
        from core.ws_rooms import tenant_broadcast_room
        from websocket_server import sio  # type: ignore
        from datetime import UTC, datetime

        await sio.emit(
            "contact_center:incoming_call",
            {
                "tenant_id": tenant_id,
                "call_id": call_id,
                "ts": datetime.now(UTC).isoformat(),
            },
            room=tenant_broadcast_room(tenant_id),
        )
    except Exception as e:  # pragma: no cover - best effort
        logger.debug("[CC-VOICE] incoming_call ping atlandı: %s", e)


# ── Kimlik-doğrulamalı uçlar ───────────────────────────────────────────


@router.post("/contact-center/voice/token")
async def issue_voice_token(
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
    _perm=Depends(require_op("manage_contact_center")),
):
    """WebRTC softphone için kısa-ömürlü Twilio AccessToken üretir.

    Kimlik kiracı-kapsamlıdır (``<tenant_id>:<user_id>``) → gelen çağrı yalnızca doğru
    kiracının ajanına yönlenebilir. Twilio yapılandırılmadıysa fail-closed
    ``not_configured`` döner (sahte token YOK). Token ASLA loglanmaz.
    """
    identity = f"{current_user.tenant_id}:{current_user.id}"
    provider = TwilioVoiceProvider()
    result = provider.generate_access_token(identity=identity)
    if not result.get("success"):
        return Response(
            content=__import__("json").dumps(
                {"status": result.get("status"), "detail": result.get("detail")}
            ),
            media_type="application/json",
            status_code=503,
        )
    return {
        "status": "ok",
        "token": result["token"],
        "identity": result["identity"],
        "ttl": result["ttl"],
    }


@router.get("/contact-center/calls")
async def list_calls(
    limit: int = 50,
    reveal_phone: bool = False,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Kiracıya ait sesli çağrı kayıtlarını listeler (allowlist DTO).

    Gerçek veriden okur; kayıt yoksa boş liste (fake data YOK). Telefon varsayılan
    maskelidir; ``reveal_phone=true`` tam numarayı yalnızca ``MANAGE_CONTACT_CENTER``
    için açar. recording_ref ASLA dönmez (yalnızca ``has_recording``).
    """
    from domains.contact_center.router import _can_reveal_phone

    safe_limit = max(1, min(int(limit or 50), 200))
    cursor = (
        db.contact_center_calls.find({"tenant_id": current_user.tenant_id})
        .sort("started_at", -1)
        .limit(safe_limit)
    )
    docs = await cursor.to_list(length=safe_limit)
    svc = get_field_encryption_service()
    reveal = bool(reveal_phone) and _can_reveal_phone(current_user)
    if reveal_phone:
        logger.info(
            "contact-center calls reveal_phone: user=%s sonuç=%s",
            current_user.id,
            "acildi" if reveal else "reddedildi",
        )
    items = [call_to_dto(d, svc, reveal_phone=reveal) for d in docs]
    return {"count": len(items), "items": items}


# ── Public Twilio webhook'ları (imza doğrulamalı, auth yok) ────────────


async def _resolve_tenant_for_number(to_number: str) -> dict | None:
    """Çağrılan numaradan kiracıyı sunucu-tarafı eşler (istemci tenant geçemez).

    ``contact_center_voice_numbers`` koleksiyonu operatör tarafından seedlenir:
    ``{to_number, tenant_id, agent_identity}``. Bulunamazsa None (fail-closed).
    """
    if not to_number:
        return None
    return await db.contact_center_voice_numbers.find_one(
        {"to_number": to_number}, {"_id": 0}
    )


@public_router.post("/inbound")
async def voice_inbound(request: Request):
    """Gelen çağrı: imza doğrula → kiracı eşle → çağrı kaydı → TwiML.

    Fail-closed: imza geçersizse 403 + sesli mesaj; kiracı eşlenemezse kibar
    fallback. PII (numara) ASLA loglanmaz.
    """
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    provider = TwilioVoiceProvider()
    if not provider.validate_signature(
        url=_public_url(request),
        params=params,
        signature=request.headers.get("X-Twilio-Signature", ""),
    ):
        return Response(
            content=provider.say_fallback("Çağrı doğrulanamadı."),
            media_type=_XML,
            status_code=403,
        )

    call_sid = params.get("CallSid", "")
    from_phone = params.get("From", "")
    to_number = params.get("To", "")
    cfg = await _resolve_tenant_for_number(to_number)
    if not cfg or not cfg.get("tenant_id"):
        return Response(
            content=provider.say_fallback(
                "Şu anda çağrınızı yanıtlayamıyoruz. Lütfen daha sonra arayın."
            ),
            media_type=_XML,
        )

    tenant_id = cfg["tenant_id"]
    agent_identity = cfg.get("agent_identity")
    call_id = await record_inbound_call(
        db,
        tenant_id=tenant_id,
        provider_call_sid=call_sid,
        from_phone=from_phone,
    )
    if call_id:
        await _notify_incoming_call(tenant_id, call_id)

    base = os.getenv("PUBLIC_APP_URL", "").strip().rstrip("/")
    rec_cb = f"{base}/api/voice/recording" if base else None
    status_cb = f"{base}/api/voice/status" if base else None
    twiml = provider.build_inbound_twiml(
        agent_identity=agent_identity,
        recording_status_callback=rec_cb,
        dial_status_callback=status_cb,
    )
    return Response(content=twiml, media_type=_XML)


@public_router.post("/status")
async def voice_status(request: Request):
    """Twilio call-status callback'i: imza doğrula → durum makinesi.

    Her zaman boş 204 döner (Twilio için yeterli). PII loglanmaz.
    """
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    provider = TwilioVoiceProvider()
    if not provider.validate_signature(
        url=_public_url(request),
        params=params,
        signature=request.headers.get("X-Twilio-Signature", ""),
    ):
        return Response(status_code=403)

    to_number = params.get("To", "")
    call_sid = params.get("CallSid", "")
    cfg = await _resolve_tenant_for_number(to_number)
    if cfg and cfg.get("tenant_id") and call_sid:
        duration = params.get("CallDuration") or params.get("DialCallDuration")
        try:
            duration_i = int(duration) if duration else None
        except (TypeError, ValueError):
            duration_i = None
        await update_call_status(
            db,
            tenant_id=cfg["tenant_id"],
            provider_call_sid=call_sid,
            twilio_status=params.get("CallStatus") or params.get("DialCallStatus") or "",
            duration_seconds=duration_i,
        )
    return Response(status_code=204)


@public_router.post("/recording")
async def voice_recording(request: Request):
    """Twilio recording-status callback'i: imza doğrula → kayıt boru hattını tetikle.

    Boru hattı (indir→şifrele→nesne deposuna yükle→recording_ref bağla) Celery'ye
    devredilir; broker yoksa inline işlenir. Depo/Twilio yapılandırılmadıysa fail-closed
    (kayıt saklanmaz). İmzalı URL ASLA persist edilmez/loglanmaz.
    """
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    provider = TwilioVoiceProvider()
    if not provider.validate_signature(
        url=_public_url(request),
        params=params,
        signature=request.headers.get("X-Twilio-Signature", ""),
    ):
        return Response(status_code=403)

    cfg = await _resolve_tenant_for_number(params.get("To", ""))
    call_sid = params.get("CallSid", "")
    recording_url = params.get("RecordingUrl", "")
    if cfg and cfg.get("tenant_id") and call_sid and recording_url:
        tenant_id = cfg["tenant_id"]
        try:
            duration = int(params.get("RecordingDuration") or 0)
        except (TypeError, ValueError):
            duration = 0
        enqueued = False
        try:
            from celery_tasks import process_call_recording_task

            process_call_recording_task.delay(
                tenant_id, call_sid, recording_url, duration
            )
            enqueued = True
        except Exception:
            logger.debug("[CC-VOICE] celery enqueue başarısız; inline işlenecek")
        if not enqueued:
            from domains.contact_center.recording_pipeline import (
                process_call_recording,
            )

            await process_call_recording(
                db,
                tenant_id=tenant_id,
                provider_call_sid=call_sid,
                recording_url=recording_url,
                duration_seconds=duration,
            )
    return Response(status_code=204)
