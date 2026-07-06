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
from core.secrets.config import get_secrets_config
from core.security import _is_super_admin, get_current_user
from domains.contact_center.read_models import call_to_dto
from domains.contact_center.voice_config import (
    get_recording_storage_config,
    get_twilio_voice_config,
)
from domains.contact_center.voice_ingest import (
    record_inbound_call,
    record_outbound_call,
    update_call_status,
)
from domains.contact_center.voice_provider import TwilioVoiceProvider
from models.schemas import User
from modules.pms_core.role_permission_service import require_module, require_op
from security.field_encryption import get_field_encryption_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["contact-center-voice"])
public_router = APIRouter(prefix="/api/voice", tags=["contact-center-voice-webhook"])

_XML = "application/xml"


def _public_url(request: Request) -> str:
    """Twilio imzasının doğrulanacağı dış URL'i kurar (proxy-güvenli).

    Twilio, yapılandırdığı tam webhook URL'ine (sorgu dizesi dâhil) imza atar;
    DigitalOcean/ters-proxy ardında ``request.url`` iç şemayı taşıyabilir, bu yüzden varsa
    ``PUBLIC_APP_URL`` esas alınır. Sorgu dizesi (örn. giden çağrı callback'lerindeki
    imzalı ``tenant_id``) imza doğrulaması için KORUNMALI.
    """
    base = os.getenv("PUBLIC_APP_URL", "").strip().rstrip("/")
    query = request.scope.get("query_string", b"").decode("utf-8")
    suffix = f"?{query}" if query else ""

    # Ham path'i koru
    path = request.scope.get("raw_path", request.url.path.encode("utf-8")).decode("utf-8")
    if not path.startswith("/"):
        path = request.url.path

    is_prod = (
        os.getenv("ENV", "").lower() == "production"
        or os.getenv("ENVIRONMENT", "").lower() == "production"
        or os.getenv("APP_ENV", "").lower() == "production"
    )

    if base:
        if not base.startswith("http://") and not base.startswith("https://"):
            base = f"https://{base}"
        return f"{base}{path}{suffix}"

    # Fallback to headers
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    host = request.headers.get("x-forwarded-host", "").split(",")[0].strip() or request.headers.get("host", "").split(",")[0].strip()

    if proto and host:
        return f"{proto}://{host}{path}{suffix}"

    if is_prod:
        logger.error("[CC-VOICE] PRODUCTION ORTAMINDA PUBLIC_APP_URL VE PROXY BASLIKLARI EKSİK! İmza doğrulaması başarısız olacak.")
        return f"https://missing-public-app-url-in-production{path}{suffix}"

    # Non-production fallback (development/test)
    fallback_proto = proto or request.url.scheme
    fallback_host = host or request.url.netloc
    return f"{fallback_proto}://{fallback_host}{path}{suffix}"



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
        from datetime import UTC, datetime

        from core.ws_rooms import tenant_broadcast_room
        from websocket_server import sio  # type: ignore

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
    tenant_part = current_user.tenant_id.replace("-", "_")
    user_part = current_user.id.replace("-", "_")
    identity = f"{tenant_part}__{user_part}"
    provider = TwilioVoiceProvider()
    result = provider.generate_access_token(identity=identity)
    if not result.get("success"):
        return Response(
            content=__import__("json").dumps({"status": result.get("status"), "detail": result.get("detail")}),
            media_type="application/json",
            status_code=503,
        )
    return {
        "status": "ok",
        "token": result["token"],
        "identity": result["identity"],
        "ttl": result["ttl"],
    }


@router.get("/contact-center/voice/readiness")
async def voice_readiness(current_user: User = Depends(get_current_user)):
    """Salt-okunur sesli-softphone hazırlık teşhisi (YALNIZCA super_admin).

    Operatör DO/DigitalOcean secret'larını girdikten sonra "sistem uyandı mı, neyi
    eksik" sorusunu tek bakışta görür. YALNIZCA varlık (bool) bilgisi döner;
    secret değeri, kısmî değeri, uzunluğu veya maskeli hâli ASLA dönmez/loglanmaz.
    Üretim env'i geneldir (kiracıya değil) → super_admin kapısı; bir kiracının
    modülü kapalı olsa bile merkezi operatör canlı hazırlığı kontrol edebilir.

    ``ready`` çekirdek sesli akış içindir (Twilio kimlik + imza + SDK +
    PUBLIC_APP_URL). Kayıt deposu ayrı raporlanır (``recording_storage.ready``);
    eksikliği aramayı engellemez, yalnızca kayıt boru hattını fail-closed yapar.
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="forbidden")
    tw = get_twilio_voice_config()
    storage = get_recording_storage_config()
    public_app_url_set = bool(os.getenv("PUBLIC_APP_URL", "").strip())
    try:
        import twilio  # noqa: F401

        twilio_sdk_installed = True
    except ImportError:
        twilio_sdk_installed = False
    try:
        import boto3  # noqa: F401

        s3_sdk_installed = True
    except ImportError:
        s3_sdk_installed = False
    twilio_ready = tw.has_credentials and tw.can_validate_signatures and twilio_sdk_installed
    recording_ready = storage.is_configured and s3_sdk_installed
    return {
        "ready": bool(twilio_ready and public_app_url_set),
        "public_app_url_set": public_app_url_set,
        "twilio": {
            "has_credentials": tw.has_credentials,
            "can_validate_signatures": tw.can_validate_signatures,
            "sdk_installed": twilio_sdk_installed,
            "ready": twilio_ready,
        },
        "recording_storage": {
            "is_configured": storage.is_configured,
            "sdk_installed": s3_sdk_installed,
            "ready": recording_ready,
        },
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
    cursor = db.contact_center_calls.find({"tenant_id": current_user.tenant_id}).sort("started_at", -1).limit(safe_limit)
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


class CallTransfer(BaseModel):
    target: str


@router.post("/contact-center/voice/live/{call_sid}/transfer")
async def transfer_live_call(
    call_sid: str,
    payload: CallTransfer,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
    _perm=Depends(require_op("manage_contact_center")),
):
    """Aktif bir çağrıyı başka bir hedefe yönlendirir (Twilio REST API)."""
    cfg = get_twilio_voice_config()
    if not cfg.can_validate_signatures:
        raise HTTPException(status_code=503, detail="Twilio yapılandırılmadı.")
    try:
        from twilio.rest import Client

        client = Client(cfg.account_sid, cfg.auth_token)
        if payload.target.startswith("client:"):
            client_id = payload.target.replace("client:", "")
            twiml = f"<Response><Dial><Client>{client_id}</Client></Dial></Response>"
        else:
            twiml = f"<Response><Dial>{payload.target}</Dial></Response>"

        client.calls(call_sid).update(twiml=twiml)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"[CC-VOICE] Aktarma başarısız: {e}")
        raise HTTPException(status_code=500, detail="Çağrı aktarılamadı.")


class CallWhatsApp(BaseModel):
    phone: str
    template_name: str
    language_code: str = "tr"


@router.post("/contact-center/voice/live/{call_sid}/whatsapp")
async def send_whatsapp_during_call(
    call_sid: str,
    payload: CallWhatsApp,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
    _perm=Depends(require_op("manage_contact_center")),
):
    """Çağrı esnasında müşteriye tek tıkla şablon gönderir (Cross-Channel)."""
    from domains.contact_center.provider import get_communication_provider

    provider = get_communication_provider("whatsapp")
    if not provider:
        raise HTTPException(status_code=503, detail="WhatsApp sağlayıcısı bulunamadı.")

    # Provider üzerinden doğrudan şablon gönderimi (Geçmişe/Conversation'a bağlamak Opsiyonel)
    res = await provider.send_whatsapp(
        db=db,
        tenant_id=current_user.tenant_id,
        recipient=payload.phone,
        in_session=False,
        template_name=payload.template_name,
        language_code=payload.language_code,
    )
    if not res.get("success"):
        raise HTTPException(status_code=502, detail="WhatsApp gönderimi başarısız.")
    return {"status": "ok"}


class CallUpdate(BaseModel):
    notes: str | None = None
    disposition: str | None = None


@router.patch("/contact-center/calls/{call_id}")
async def update_call(
    call_id: str,
    payload: CallUpdate,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Çağrı kaydına not veya disposition ekler."""
    doc = await db.contact_center_calls.find_one({"id": call_id, "tenant_id": current_user.tenant_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Çağrı bulunamadı")

    updates = {}
    if payload.notes is not None:
        updates["notes"] = payload.notes
    if payload.disposition is not None:
        updates["disposition"] = payload.disposition

    if not updates:
        return {"status": "ok"}

    await db.contact_center_calls.update_one({"id": call_id}, {"$set": updates})
    return {"status": "ok"}


@router.get("/contact-center/calls/{call_id}/recording")
async def get_call_recording(
    call_id: str,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Şifreli çağrı kaydını (at-read) çözer ve ses dosyası olarak döner."""
    doc = await db.contact_center_calls.find_one({"id": call_id, "tenant_id": current_user.tenant_id})
    if not doc or not doc.get("recording_ref"):
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")

    from domains.contact_center.recording_storage import load_recording_bytes

    audio_bytes = load_recording_bytes(doc["recording_ref"], tenant_id=current_user.tenant_id, call_id=call_id)
    if not audio_bytes:
        raise HTTPException(status_code=404, detail="Kayıt dosyası okunamadı veya şifre çözme hatası")

    # Twilio mp3/wav kaydeder, biz varsayılan olarak audio/mpeg veya wav dönebiliriz.
    return Response(content=audio_bytes, media_type="audio/mpeg")


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
    """Ajan kimliği opsiyonel; varsa kiracı-kapsamlı olmalı (``<tenant_id>:...`` veya ``<tenant_id_with_underscores>_...``)."""
    if agent_identity is None:
        return None
    ai = agent_identity.strip()
    if not ai:
        return None
    tenant_part = tenant_id.replace("-", "_")
    is_legacy = ai.startswith(f"{tenant_id}:")
    is_safe = ai.startswith(f"{tenant_part}_")
    if not is_legacy and not is_safe:
        raise HTTPException(
            status_code=422,
            detail="Ajan kimliği ilgili otel kapsamında olmalı (<tenant_id>_<kullanıcı>)",
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
        updates["agent_identity"] = _validate_agent_identity(payload.agent_identity, target_tenant)
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
    return await db.contact_center_voice_numbers.find_one({"to_number": to_number}, {"_id": 0})


async def _resolve_number_for_tenant(tenant_id: str, user_id: str | None = None) -> dict | None:
    """Kiracının giden çağrı caller ID (Twilio numarası) eşlemesini döner.

    Öncelikle ajana özel aktif eşlemeyi arar. Bulunamazsa otelin varsayılan (ajan kimliği boş)
    aktif eşlemesine fallback yapar. is_active=False olanlar dikkate alınmaz.
    """
    if not tenant_id:
        return None

    if user_id:
        legacy_agent_identity = f"{tenant_id}:{user_id}"
        safe_agent_identity = f"{tenant_id.replace('-', '_')}__{user_id.replace('-', '_')}"
        fallback_agent_identity = f"{tenant_id.replace('-', '_')}_{user_id.replace('-', '_')}"
        mapping = await db.contact_center_voice_numbers.find_one(
            {
                "tenant_id": tenant_id,
                "agent_identity": {"$in": [legacy_agent_identity, safe_agent_identity, fallback_agent_identity]},
                "is_active": {"$ne": False},
            },
            {"_id": 0},
        )
        if mapping:
            return mapping

    # Varsayılan otel yönlendirmesine fallback (agent_identity boş, null veya yok)
    return await db.contact_center_voice_numbers.find_one(
        {
            "tenant_id": tenant_id,
            "$or": [
                {"agent_identity": {"$in": ["", None]}},
                {"agent_identity": {"$exists": False}},
            ],
            "is_active": {"$ne": False},
        },
        {"_id": 0},
    )


def _reconstruct_uuid(s: str) -> str:
    if len(s) == 36 and s[8] == "_" and s[13] == "_" and s[18] == "_" and s[23] == "_":
        return f"{s[:8]}-{s[9:13]}-{s[14:18]}-{s[19:23]}-{s[24:]}"
    return s


def _parse_client_identity(value: str) -> tuple[str | None, str | None]:
    """Twilio ``From``/``Caller`` → (tenant_id, user_id).

    Hem geleneksel iki nokta formatını (client:tenant_id:user_id) hem de safe alt çizgi
    formatını (client:tenant_id_user_id, hyphens replaced with underscores) destekler.
    """
    if not value:
        return None, None
    raw = value.strip()
    if raw.startswith("client:"):
        raw = raw[len("client:") :]

    if raw.count("__") > 1 or raw.count(":") > 1:
        return None, None

    # 1. Geleneksel iki noktalı format
    if ":" in raw:
        parts = raw.split(":", 1)
        tenant_id = parts[0].strip() if parts else None
        user_id = parts[1].strip() if len(parts) > 1 else None
        return tenant_id or None, user_id or None

    # 2. Çift alt çizgili format (en güvenli, sıfır çakışma)
    if "__" in raw:
        parts = raw.split("__", 1)
        tenant_id = _reconstruct_uuid(parts[0].strip())
        user_id = _reconstruct_uuid(parts[1].strip())
        return tenant_id or None, user_id or None

    # 3. Güvenli tek alt çizgili format (kullanıcı kimliği son 36 karakterdir ve UUID formatındadır)
    if len(raw) >= 37:
        user_part = raw[-36:]
        sep = raw[-37]
        if sep == "_" and user_part[8] == "_" and user_part[13] == "_" and user_part[18] == "_" and user_part[23] == "_":
            tenant_part = raw[:-37]
            tenant_id = _reconstruct_uuid(tenant_part)
            user_id = _reconstruct_uuid(user_part)
            return tenant_id or None, user_id or None

    # 4. Genel tek alt çizgili format (test ortamları veya UUID olmayan basit kimlikler için)
    if "_" in raw:
        parts = raw.rsplit("_", 1)
        return parts[0].strip() or None, parts[1].strip() or None

    return None, None


@public_router.get("/debug-config")
async def voice_debug_config(current_user: User = Depends(get_current_user)):
    """Non-sensitive status of Twilio configuration and environment variables."""
    if get_secrets_config().is_production:
        raise HTTPException(status_code=404, detail="Not Found")
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        from core.security import JWT_EXPIRATION_MINUTES as resolved_jwt_min

        cfg = get_twilio_voice_config()
        return {
            "has_account_sid": bool(cfg.account_sid),
            "has_auth_token": bool(cfg.auth_token),
            "has_api_key": bool(cfg.api_key_sid),
            "has_api_secret": bool(cfg.api_key_secret),
            "has_twiml_app_sid": bool(cfg.twiml_app_sid),
            "bypass_signature": os.getenv("BYPASS_TWILIO_SIGNATURE"),
            "testing": os.getenv("TESTING"),
            "public_app_url": os.getenv("PUBLIC_APP_URL"),
            "env_jwt_minutes": os.getenv("JWT_EXPIRATION_MINUTES"),
            "env_jwt_hours": os.getenv("JWT_EXPIRATION_HOURS"),
            "resolved_jwt_expiration_minutes": resolved_jwt_min,
        }
    except Exception as e:
        import traceback

        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }


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
            content=provider.say_fallback("Şu anda çağrınızı yanıtlayamıyoruz. Lütfen daha sonra arayın."),
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
        request=request,
    ):
        return Response(
            content=provider.say_fallback("Çağrı doğrulanamadı."),
            media_type=_XML,
            status_code=403,
        )

    call_sid = params.get("CallSid", "")
    to_number = params.get("To", "")
    # Kiracı YALNIZCA sunucu-basılı client kimliğinden gelir (istemci geçemez).
    from_val = params.get("From", "") or params.get("Caller", "")
    tenant_id, user_id = _parse_client_identity(from_val)

    tenant_resolved = bool(tenant_id)
    agent_identity_present = bool(user_id)
    agent_mapping_found = False
    tenant_default_mapping_found = False

    if not tenant_id:
        logger.warning(f"[CC-VOICE-DIAG] Outbound failed: tenant_resolved=False agent_identity_present={agent_identity_present}")
        return Response(
            content=provider.say_fallback("Çağrı başlatılamadı."),
            media_type=_XML,
        )

    # Önce ajana özel aktif eşlemeyi arayalım, yoksa varsayılana fallback yapalım
    number_cfg = None
    if user_id:
        legacy_agent_identity = f"{tenant_id}:{user_id}"
        safe_agent_identity = f"{tenant_id.replace('-', '_')}__{user_id.replace('-', '_')}"
        fallback_agent_identity = f"{tenant_id.replace('-', '_')}_{user_id.replace('-', '_')}"
        number_cfg = await db.contact_center_voice_numbers.find_one(
            {
                "tenant_id": tenant_id,
                "agent_identity": {"$in": [legacy_agent_identity, safe_agent_identity, fallback_agent_identity]},
                "is_active": {"$ne": False},
            },
            {"_id": 0},
        )
        if number_cfg:
            agent_mapping_found = True

    if not number_cfg:
        number_cfg = await db.contact_center_voice_numbers.find_one(
            {
                "tenant_id": tenant_id,
                "$or": [
                    {"agent_identity": {"$in": ["", None]}},
                    {"agent_identity": {"$exists": False}},
                ],
                "is_active": {"$ne": False},
            },
            {"_id": 0},
        )
        if number_cfg:
            tenant_default_mapping_found = True

    caller_id = (number_cfg or {}).get("to_number")
    sanitized = provider.sanitize_dial_number(to_number)

    logger.info(
        f"[CC-VOICE-DIAG] Outbound attempt: "
        f"CallSid={call_sid} "
        f"tenant_resolved={tenant_resolved} "
        f"agent_identity_present={agent_identity_present} "
        f"agent_mapping_found={agent_mapping_found} "
        f"tenant_default_mapping_found={tenant_default_mapping_found} "
        f"selected_caller_id_last4={caller_id[-4:] if (caller_id and len(caller_id) >= 4) else 'None'}"
    )

    if not caller_id or not sanitized:
        logger.warning(
            f"[CC-VOICE-DIAG] Outbound failed: "
            f"tenant_resolved={tenant_resolved} "
            f"agent_identity_present={agent_identity_present} "
            f"agent_mapping_found={agent_mapping_found} "
            f"tenant_default_mapping_found={tenant_default_mapping_found} "
            f"selected_caller_id_present={bool(caller_id)} "
            f"sanitized_present={bool(sanitized)}"
        )
        return Response(
            content=provider.say_fallback("Çağrı başlatılamadı. Lütfen numarayı kontrol edin."),
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
        request=request,
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
        request=request,
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

            process_call_recording_task.delay(tenant_id, call_sid, recording_url, duration)
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
