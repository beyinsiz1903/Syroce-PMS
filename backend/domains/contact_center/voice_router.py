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
import re
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from core.database import db
from core.security import _is_super_admin, get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_module, require_op
from security.field_encryption import get_field_encryption_service

from domains.contact_center.read_models import call_to_dto
from domains.contact_center.voice_config import get_twilio_voice_config
from domains.contact_center.voice_ingest import (
    record_inbound_call,
    record_outbound_call,
    update_call_status,
)
from domains.contact_center.voice_provider import TwilioVoiceProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["contact-center-voice"])
public_router = APIRouter(prefix="/api/voice", tags=["contact-center-voice-webhook"])

_XML = "application/xml"


def _public_url(request: Request) -> str:
    """Twilio imzasının doğrulanacağı dış URL'i kurar (proxy-güvenli).

    Twilio, yapılandırdığı tam webhook URL'ine (sorgu dizesi dâhil) imza atar;
    Replit/ters-proxy ardında ``request.url`` iç şemayı taşıyabilir, bu yüzden varsa
    ``PUBLIC_APP_URL`` esas alınır. Sorgu dizesi (örn. giden çağrı callback'lerindeki
    imzalı ``tenant_id``) imza doğrulaması için KORUNMALI.
    """
    base = os.getenv("PUBLIC_APP_URL", "").strip().rstrip("/")
    query = request.url.query
    suffix = f"?{query}" if query else ""
    if base:
        return f"{base}{request.url.path}{suffix}"
    return str(request.url)


def _callback_urls(tenant_id: str | None = None) -> tuple[str | None, str | None]:
    """Kayıt + durum callback URL'lerini kurar (``PUBLIC_APP_URL`` yoksa None).

    Giden çağrıda ``To``/``From`` kiracıya eşlenemez (numara değil client kimliği);
    bu yüzden ``tenant_id`` imzalı bir sorgu parametresi olarak eklenir. Twilio tüm
    URL'i (sorgu dâhil) imzalar → ``tenant_id`` istemci tarafından sahtelenemez.
    """
    base = os.getenv("PUBLIC_APP_URL", "").strip().rstrip("/")
    if not base:
        return None, None
    suffix = ""
    if tenant_id:
        from urllib.parse import urlencode

        suffix = f"?{urlencode({'tenant_id': tenant_id})}"
    return (
        f"{base}/api/voice/recording{suffix}",
        f"{base}/api/voice/status{suffix}",
    )


async def _resolve_tenant_id(request: Request, to_number: str) -> str | None:
    """Callback'lerde kiracıyı çözer: imzalı ``tenant_id`` sorgusu → numara eşlemesi.

    Giden çağrı callback'leri ``?tenant_id=`` taşır (imza ile korunur). Gelen çağrı
    callback'lerinde sorgu yoktur → ``To`` numarasından sunucu-tarafı eşleme yapılır.
    """
    qp = request.query_params.get("tenant_id")
    if qp:
        return qp
    cfg = await _resolve_tenant_for_number(to_number)
    if cfg and cfg.get("tenant_id"):
        return cfg["tenant_id"]
    return None


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


# ── Numara → otel/ajan eşleme yönetimi (operatör admin ekranı) ─────────
#
# ``contact_center_voice_numbers`` gelen çağrının doğru kiracıya yönlenmesini
# sağlayan eşlemedir: ``{to_number, tenant_id, agent_identity}``. Bu uçlar elle
# DB seed yerine yetkili operatöre güvenli CRUD verir.
#
# Tenant izolasyonu (mutlak): tenant_id ASLA istemci gövdesinden körü körüne
# alınmaz. super_admin merkezi operatördür → bir numarayı herhangi bir otele
# atayabilir (gövdedeki ``tenant_id`` yalnızca super_admin için geçerli, ve
# hedef otelin varlığı doğrulanır). Diğer roller her zaman kendi
# ``current_user.tenant_id`` kapsamına sabitlenir. ``ux_cc_voice_number`` index'i
# ``to_number`` üzerinde GLOBAL unique olduğundan bir numara tek otele aittir;
# çakışma 409 (başka otel bilgisi sızdırılmadan) döner.

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")
_VOICE_NUMBERS = "contact_center_voice_numbers"


class VoiceNumberCreate(BaseModel):
    to_number: str
    agent_identity: str | None = None
    label: str | None = None
    tenant_id: str | None = None  # yalnızca super_admin için etkilidir


class VoiceNumberUpdate(BaseModel):
    to_number: str | None = None
    agent_identity: str | None = None
    label: str | None = None


def _normalize_number(raw: str | None) -> str:
    """Boşluk/tire temizler; E.164 doğrular. Geçersizse 422."""
    n = (raw or "").strip().replace(" ", "").replace("-", "")
    if not _E164_RE.match(n):
        raise HTTPException(
            status_code=422,
            detail="Numara E.164 formatında olmalı (örn. +905321234567)",
        )
    return n


def _validate_agent_identity(agent_identity: str | None, tenant_id: str) -> str | None:
    """Ajan kimliği opsiyonel; varsa kiracı-kapsamlı olmalı (``<tenant_id>:...``).

    Token kimliği formatı ``<tenant_id>:<user_id>`` ile birebir uyumlu — başka
    kiracının ajanına çağrı yönlendirmeyi engeller.
    """
    if agent_identity is None:
        return None
    ai = agent_identity.strip()
    if not ai:
        return None
    if not ai.startswith(f"{tenant_id}:"):
        raise HTTPException(
            status_code=422,
            detail="Ajan kimliği ilgili otel kapsamında olmalı (<tenant_id>:<kullanıcı>)",
        )
    return ai


async def _resolve_target_tenant(current_user: User, body_tenant_id: str | None) -> str:
    """Hedef kiracıyı belirler. super_admin gövdeden seçebilir (varlık doğrulanır);
    diğer roller her zaman kendi kiracısına sabitlenir."""
    if _is_super_admin(current_user) and body_tenant_id:
        exists = await db.tenants.find_one({"id": body_tenant_id}, {"_id": 0, "id": 1})
        if not exists:
            raise HTTPException(status_code=404, detail="Otel (tenant) bulunamadı")
        return body_tenant_id
    return current_user.tenant_id


def _scope_filter(current_user: User, number_id: str) -> dict:
    """Kayıt eşleme filtresi. super_admin tüm kiracılarda işlem yapabilir; diğer
    roller yalnızca kendi kiracısının kaydına dokunabilir (IDOR engeli)."""
    if _is_super_admin(current_user):
        return {"id": number_id}
    return {"id": number_id, "tenant_id": current_user.tenant_id}


def _voice_number_dto(doc: dict) -> dict:
    """Allowlist DTO — ``_id`` veya beklenmeyen alan sızdırmaz. to_number otelin
    KENDİ hattıdır (misafir PII değil) → yetkili admine gösterilir."""
    return {
        "id": doc.get("id"),
        "tenant_id": doc.get("tenant_id"),
        "to_number": doc.get("to_number"),
        "agent_identity": doc.get("agent_identity"),
        "label": doc.get("label"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


@router.get("/contact-center/voice/numbers")
async def list_voice_numbers(
    tenant_id: str | None = None,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
    _perm=Depends(require_op("manage_contact_center")),
):
    """Numara→otel/ajan eşlemelerini listeler (allowlist DTO).

    super_admin tüm eşlemeleri görür (``?tenant_id`` ile süzebilir); diğer roller
    yalnızca kendi otelinin eşlemelerini görür. Gerçek veriden okur; kayıt yoksa
    boş liste (fake data YOK).
    """
    if _is_super_admin(current_user):
        query = {"tenant_id": tenant_id} if tenant_id else {}
    else:
        query = {"tenant_id": current_user.tenant_id}
    cursor = db[_VOICE_NUMBERS].find(query, {"_id": 0}).sort("to_number", 1).limit(500)
    docs = await cursor.to_list(length=500)
    items = [_voice_number_dto(d) for d in docs]
    return {"count": len(items), "items": items}


@router.post("/contact-center/voice/numbers", status_code=201)
async def create_voice_number(
    payload: VoiceNumberCreate,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
    _perm=Depends(require_op("manage_contact_center")),
):
    """Yeni numara→otel/ajan eşlemesi oluşturur.

    Çakışma: ``to_number`` global unique → numara başka bir eşlemede varsa 409
    (başka otel bilgisi sızdırılmaz). tenant_id istemciden körü körüne alınmaz.
    """
    target_tenant = await _resolve_target_tenant(current_user, payload.tenant_id)
    to_number = _normalize_number(payload.to_number)
    agent_identity = _validate_agent_identity(payload.agent_identity, target_tenant)
    now = datetime.now(UTC)
    doc = {
        "id": str(uuid4()),
        "tenant_id": target_tenant,
        "to_number": to_number,
        "agent_identity": agent_identity,
        "label": (payload.label or "").strip() or None,
        "created_at": now,
        "updated_at": now,
        "created_by": current_user.id,
    }
    try:
        await db[_VOICE_NUMBERS].insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="Bu numara zaten bir eşlemede kullanılıyor",
        )
    return _voice_number_dto(doc)


@router.put("/contact-center/voice/numbers/{number_id}")
async def update_voice_number(
    number_id: str,
    payload: VoiceNumberUpdate,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
    _perm=Depends(require_op("manage_contact_center")),
):
    """Mevcut eşlemeyi günceller (kapsam-filtreli). Bulunamazsa 404; ``to_number``
    çakışırsa 409."""
    scope = _scope_filter(current_user, number_id)
    existing = await db[_VOICE_NUMBERS].find_one(scope, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Eşleme bulunamadı")
    target_tenant = existing["tenant_id"]
    updates: dict = {"updated_at": datetime.now(UTC)}
    if payload.to_number is not None:
        updates["to_number"] = _normalize_number(payload.to_number)
    if payload.agent_identity is not None:
        updates["agent_identity"] = _validate_agent_identity(
            payload.agent_identity, target_tenant
        )
    if payload.label is not None:
        updates["label"] = payload.label.strip() or None
    # Kapsam filtresi yazma ve okuma adımlarında da korunur (defense-in-depth;
    # pre-check'e bağımlı kalmaz → cross-tenant yazma/okuma imkânsız).
    try:
        await db[_VOICE_NUMBERS].update_one(scope, {"$set": updates})
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="Bu numara zaten bir eşlemede kullanılıyor",
        )
    doc = await db[_VOICE_NUMBERS].find_one(scope, {"_id": 0})
    return _voice_number_dto(doc or {})


@router.delete("/contact-center/voice/numbers/{number_id}", status_code=204)
async def delete_voice_number(
    number_id: str,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
    _perm=Depends(require_op("manage_contact_center")),
):
    """Eşlemeyi siler (kapsam-filtreli). Bulunamazsa 404."""
    result = await db[_VOICE_NUMBERS].delete_one(_scope_filter(current_user, number_id))
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Eşleme bulunamadı")
    return Response(status_code=204)


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


async def _resolve_number_for_tenant(tenant_id: str) -> dict | None:
    """Kiracının giden çağrı caller ID (Twilio numarası) eşlemesini döner.

    Giden çağrıda caller ID istemciden ALINMAZ — kiracının operatörce seedlenmiş
    ``contact_center_voice_numbers`` satırından (``to_number``) türetilir. Yoksa None
    (fail-closed: numara olmadan giden çağrı başlatılmaz).
    """
    if not tenant_id:
        return None
    return await db.contact_center_voice_numbers.find_one(
        {"tenant_id": tenant_id}, {"_id": 0}
    )


def _parse_client_identity(value: str) -> str | None:
    """Twilio ``From``/``Caller`` (``client:<tenant_id>:<user_id>``) → tenant_id.

    Kimlik access token'da SUNUCU tarafından basıldığı ve Twilio isteği imzaladığı
    için buradan türetilen ``tenant_id`` GÜVENİLİRDİR (istemci sahteleyemez). Beklenen
    biçim dışındaysa None (fail-closed).
    """
    if not value:
        return None
    raw = value.strip()
    if raw.startswith("client:"):
        raw = raw[len("client:"):]
    parts = raw.split(":", 1)
    tenant_id = parts[0].strip() if parts else ""
    return tenant_id or None


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

    rec_cb, status_cb = _callback_urls(tenant_id)
    twiml = provider.build_inbound_twiml(
        agent_identity=agent_identity,
        recording_status_callback=rec_cb,
        dial_status_callback=status_cb,
    )
    return Response(content=twiml, media_type=_XML)


@public_router.post("/outbound")
async def voice_outbound(request: Request):
    """Giden çağrı (click-to-dial): TwiML App voiceUrl.

    Ajan softphone'dan ``Device.connect({ params: { To } })`` çağırınca Twilio buraya
    POST eder. Akış: imza doğrula → ``From``/``Caller`` client kimliğinden kiracıyı
    SUNUCU-tarafı türet (istemci tenant geçemez) → kiracının Twilio numarasını caller
    ID olarak çöz → giden çağrıyı idempotent kaydet → hedefi arayan TwiML döndür.

    Fail-closed: imza geçersizse 403; kimlik/numara/caller ID eksikse kibar sesli
    fallback (giden çağrı başlatılmaz). PII (hedef numara) ASLA loglanmaz.
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
    to_number = params.get("To", "")
    # Kiracı YALNIZCA sunucu-basılı client kimliğinden gelir (istemci geçemez).
    tenant_id = _parse_client_identity(
        params.get("From", "") or params.get("Caller", "")
    )
    if not tenant_id:
        return Response(
            content=provider.say_fallback("Çağrı başlatılamadı."),
            media_type=_XML,
        )

    number_cfg = await _resolve_number_for_tenant(tenant_id)
    caller_id = (number_cfg or {}).get("to_number")
    sanitized = provider.sanitize_dial_number(to_number)
    if not caller_id or not sanitized:
        return Response(
            content=provider.say_fallback(
                "Çağrı başlatılamadı. Lütfen numarayı kontrol edin."
            ),
            media_type=_XML,
        )

    await record_outbound_call(
        db,
        tenant_id=tenant_id,
        provider_call_sid=call_sid,
        to_phone=sanitized,
    )

    rec_cb, status_cb = _callback_urls(tenant_id)
    twiml = provider.build_outbound_twiml(
        to_number=sanitized,
        caller_id=caller_id,
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

    call_sid = params.get("CallSid", "")
    tenant_id = await _resolve_tenant_id(request, params.get("To", ""))
    if tenant_id and call_sid:
        duration = params.get("CallDuration") or params.get("DialCallDuration")
        try:
            duration_i = int(duration) if duration else None
        except (TypeError, ValueError):
            duration_i = None
        await update_call_status(
            db,
            tenant_id=tenant_id,
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

    tenant_id = await _resolve_tenant_id(request, params.get("To", ""))
    call_sid = params.get("CallSid", "")
    recording_url = params.get("RecordingUrl", "")
    if tenant_id and call_sid and recording_url:
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
