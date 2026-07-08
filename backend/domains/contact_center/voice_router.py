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

import asyncio
import logging
import os
import re
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
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
    page: int = 1,
    limit: int = 50,
    reveal_phone: bool = False,
    agent_id: str | None = None,
    direction: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Kiracıya ait sesli çağrı kayıtlarını listeler (allowlist DTO) ve filtreleme/arama desteği sunar."""
    from domains.contact_center.router import _can_reveal_phone

    safe_limit = max(1, min(int(limit or 50), 200))
    safe_page = max(1, int(page or 1))
    skip = (safe_page - 1) * safe_limit

    query = {"tenant_id": current_user.tenant_id}

    if agent_id:
        query["agent_id"] = agent_id
    if direction:
        query["direction"] = direction
    if status:
        query["status"] = status

    if date_from or date_to:
        started_filter = {}
        if date_from:
            try:
                started_filter["$gte"] = datetime.fromisoformat(date_from.replace("Z", "+00:00")).astimezone(UTC)
            except ValueError:
                raise HTTPException(400, "Geçersiz date_from formatı. ISO formatı gereklidir.")
        if date_to:
            try:
                started_filter["$lte"] = datetime.fromisoformat(date_to.replace("Z", "+00:00")).astimezone(UTC)
            except ValueError:
                raise HTTPException(400, "Geçersiz date_to formatı. ISO formatı gereklidir.")
        query["started_at"] = started_filter

    svc = get_field_encryption_service()
    if search:
        search_stripped = search.strip()
        if search_stripped:
            search_hash = svc.compute_search_hash(search_stripped)
            query["caller_id_hash"] = search_hash

    total_count = await db.contact_center_calls.count_documents(query)

    cursor = db.contact_center_calls.find(query).sort("started_at", -1).skip(skip).limit(safe_limit)
    docs = await cursor.to_list(length=safe_limit)

    reveal = bool(reveal_phone) and _can_reveal_phone(current_user)
    if reveal_phone:
        logger.info(
            "contact-center calls reveal_phone: user=%s sonuç=%s",
            current_user.id,
            "acildi" if reveal else "reddedildi",
        )
    items = [call_to_dto(d, svc, reveal_phone=reveal) for d in docs]
    return {
        "count": len(items),
        "total": total_count,
        "page": safe_page,
        "limit": safe_limit,
        "items": items,
    }


@router.get("/contact-center/analytics/summary")
async def get_analytics_summary(
    date_from: str | None = None,
    date_to: str | None = None,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Çağrı merkezi performans özet istatistiklerini ve saatlik hacim grafiğini hesaplar."""
    # Resolve hotel/tenant timezone
    tz_doc = await db.tenant_settings.find_one({"tenant_id": current_user.tenant_id}, {"_id": 0, "timezone": 1}) or {}
    tz_name = tz_doc.get("timezone") or "Europe/Istanbul"
    import zoneinfo
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = zoneinfo.ZoneInfo("Europe/Istanbul")

    now_tz = datetime.now(tz)
    # Start of today (local time)
    today_start = datetime(now_tz.year, now_tz.month, now_tz.day, tzinfo=tz)
    # End of today
    from datetime import timedelta
    today_end = today_start + timedelta(days=1)

    query = {"tenant_id": current_user.tenant_id}

    if date_from or date_to:
        started_filter = {}
        if date_from:
            try:
                started_filter["$gte"] = datetime.fromisoformat(date_from.replace("Z", "+00:00")).astimezone(UTC)
            except ValueError:
                raise HTTPException(400, "Geçersiz date_from formatı. ISO formatı gereklidir.")
        if date_to:
            try:
                started_filter["$lte"] = datetime.fromisoformat(date_to.replace("Z", "+00:00")).astimezone(UTC)
            except ValueError:
                raise HTTPException(400, "Geçersiz date_to formatı. ISO formatı gereklidir.")
        query["started_at"] = started_filter
    else:
        # Default: today in local hotel timezone (converted to UTC for querying database)
        query["started_at"] = {"$gte": today_start.astimezone(UTC), "$lt": today_end.astimezone(UTC)}

    cursor = db.contact_center_calls.find(query)
    calls = await cursor.to_list(length=10000)

    # Deduplicate parent/child legs to count related legs as one business call
    business_calls = {}
    for c in calls:
        parent_sid = c.get("parent_call_sid") or c.get("provider_call_sid")
        if not parent_sid:
            continue
        if parent_sid not in business_calls:
            business_calls[parent_sid] = []
        business_calls[parent_sid].append(c)

    deduped_calls = []
    for parent_sid, legs in business_calls.items():
        representative = None
        for leg in legs:
            if leg.get("status") in {"answered", "completed"}:
                representative = leg
                break
        if not representative:
            for leg in legs:
                if leg.get("provider_call_sid") == parent_sid:
                    representative = leg
                    break
        if not representative:
            representative = legs[0]
        deduped_calls.append(representative)

    total_calls = len(deduped_calls)
    inbound_calls = sum(1 for c in deduped_calls if c.get("direction") == "inbound")
    outbound_calls = sum(1 for c in deduped_calls if c.get("direction") == "outbound")

    answered_calls = sum(1 for c in deduped_calls if c.get("status") in {"answered", "completed"})
    missed_calls = sum(1 for c in deduped_calls if c.get("status") == "missed")
    failed_calls = sum(1 for c in deduped_calls if c.get("status") == "failed")

    # SLA and Durations
    total_duration = 0
    total_wait_time = 0
    sla_met_count = 0
    answered_with_wait = 0

    for c in deduped_calls:
        dur = c.get("duration_seconds") or 0
        if not dur and c.get("answered_at") and c.get("ended_at"):
            dur = int((c["ended_at"] - c["answered_at"]).total_seconds())
        total_duration += max(0, dur)

        if c.get("answered_at") and c.get("started_at"):
            wait = (c["answered_at"] - c["started_at"]).total_seconds()
            total_wait_time += max(0.0, wait)
            answered_with_wait += 1
            if wait <= 20.0:
                sla_met_count += 1

    avg_duration = int(total_duration / answered_calls) if answered_calls > 0 else 0
    avg_wait = round(total_wait_time / answered_with_wait, 1) if answered_with_wait > 0 else 0.0
    sla_rate = round((sla_met_count / answered_with_wait) * 100, 1) if answered_with_wait > 0 else 100.0
    abandon_rate = round((missed_calls / inbound_calls) * 100, 1) if (inbound_calls > 0) else 0.0

    # Group hourly for local timezone chart
    hourly_stats = {i: {"total": 0, "answered": 0, "missed": 0} for i in range(24)}
    for c in calls:
        if c.get("started_at"):
            started_local = c["started_at"].astimezone(tz)
            hour = started_local.hour
            if hour in hourly_stats:
                hourly_stats[hour]["total"] += 1
                if c.get("status") in {"answered", "completed"}:
                    hourly_stats[hour]["answered"] += 1
                elif c.get("status") == "missed":
                    hourly_stats[hour]["missed"] += 1

    chart_data = [{"hour": f"{h:02d}:00", **hourly_stats[h]} for h in range(24)]

    return {
        "summary": {
            "total_calls": total_calls,
            "inbound_calls": inbound_calls,
            "outbound_calls": outbound_calls,
            "answered_calls": answered_calls,
            "missed_calls": missed_calls,
            "failed_calls": failed_calls,
            "avg_duration_seconds": avg_duration,
            "avg_wait_seconds": avg_wait,
            "sla_rate": sla_rate,
            "abandon_rate": abandon_rate,
        },
        "chart": chart_data,
        "timezone": tz_name,
    }


@router.get("/contact-center/calls/{call_id}/guest-360")
async def get_call_guest_360(
    call_id: str,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    call_doc = await db.contact_center_calls.find_one({
        "id": call_id,
        "tenant_id": current_user.tenant_id
    })
    if not call_doc:
        call_doc = await db.contact_center_calls.find_one({
            "provider_call_sid": call_id,
            "tenant_id": current_user.tenant_id
        })
    if not call_doc:
        raise HTTPException(status_code=404, detail="Çağrı bulunamadı.")

    svc = get_field_encryption_service()
    def _dec(service, enc_val):
        if not enc_val:
            return None
        try:
            return service.decrypt_value(enc_val)
        except Exception:
            return None

    phone = _dec(svc, call_doc.get("caller_id_enc"))
    if not phone:
        return {
            "guest": None,
            "bookings": [],
            "call_history_count": 0
        }

    from security.encrypted_lookup import build_guest_pii_query, decrypt_guest_doc
    cursor = db.guests.find({
        "tenant_id": current_user.tenant_id,
        **build_guest_pii_query("phone", phone)
    })
    guest_docs = await cursor.to_list(length=10)

    guest_info = None
    bookings_info = []
    if guest_docs:
        if len(guest_docs) > 1:
            guest_info = {
                "id": "masked",
                "name": "Gizli Misafir (Çoklu Eşleşme)",
                "vip": False,
                "email": "masked@masked.com",
                "phone": phone[:3] + "*****" + phone[-4:] if len(phone) >= 7 else "*****",
            }
        else:
            guest_doc = decrypt_guest_doc(guest_docs[0])
            guest_info = {
                "id": guest_doc.get("id"),
                "name": guest_doc.get("name") or f"{guest_doc.get('first_name', '')} {guest_doc.get('last_name', '')}".strip(),
                "vip": guest_doc.get("vip", False),
                "email": guest_doc.get("email"),
                "phone": phone,
            }

            bookings_cursor = db.bookings.find({
                "tenant_id": current_user.tenant_id,
                "guest_id": guest_doc["id"]
            }).sort("check_in", -1)
            bookings = await bookings_cursor.to_list(length=10)
            for b in bookings:
                bookings_info.append({
                    "id": b.get("id"),
                    "status": b.get("status"),
                    "check_in": b.get("check_in"),
                    "check_out": b.get("check_out"),
                    "room_id": b.get("room_id"),
                    "total_price": b.get("total_price"),
                })

    call_history_count = await db.contact_center_calls.count_documents({
        "tenant_id": current_user.tenant_id,
        "caller_id_hash": call_doc.get("caller_id_hash")
    })

    return {
        "guest": guest_info or {
            "name": "Bilinmeyen Misafir",
            "vip": False,
            "phone": phone,
            "email": None,
        },
        "bookings": bookings_info,
        "call_history_count": call_history_count
    }


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
    from models.enums import CallStatus
    # Verify call SID ownership and active status
    call = await db.contact_center_calls.find_one({
        "tenant_id": current_user.tenant_id,
        "caller_id_enc": {"$exists": True, "$ne": None},
        "$or": [
            {"provider_call_sid": call_sid},
            {"parent_call_sid": call_sid}
        ],
        "status": {"$in": [CallStatus.RINGING.value, CallStatus.ANSWERED.value]},
    })
    if not call:
        call = await db.contact_center_calls.find_one({
            "tenant_id": current_user.tenant_id,
            "$or": [
                {"provider_call_sid": call_sid},
                {"parent_call_sid": call_sid}
            ],
            "status": {"$in": [CallStatus.RINGING.value, CallStatus.ANSWERED.value]},
        })
    if not call:
        raise HTTPException(status_code=404, detail="Aktif çağrı bulunamadı.")

    # Target format validation: E.164 or agent identity format
    target = payload.target.strip()
    is_valid = False
    if target.startswith("client:"):
        client_id = target[7:]
        is_valid = bool(re.match(r"^[a-zA-Z0-9_]+__[a-zA-Z0-9_]+$", client_id))
    else:
        is_valid = bool(re.match(r"^\+?[1-9]\d{1,14}$", target))

    if not is_valid:
        raise HTTPException(status_code=400, detail="Geçersiz aktarım hedefi.")

    cfg = get_twilio_voice_config()
    if not cfg.can_validate_signatures:
        raise HTTPException(status_code=503, detail="Twilio yapılandırılmadı.")
    try:
        from twilio.rest import Client
        from twilio.twiml.voice_response import VoiceResponse

        client = Client(cfg.account_sid, cfg.auth_token)

        response = VoiceResponse()
        dial = response.dial()
        if target.startswith("client:"):
            dial.client(target[7:])
        else:
            dial.number(target)
        twiml = str(response)

        client.calls(call_sid).update(twiml=twiml)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"[CC-VOICE] Aktarma başarısız: {e}")
        raise HTTPException(status_code=500, detail="Çağrı aktarılamadı.")


class CallWhatsApp(BaseModel):
    phone: str | None = None
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
    # Verify call SID ownership and active status
    call = await db.contact_center_calls.find_one({
        "tenant_id": current_user.tenant_id,
        "caller_id_enc": {"$exists": True, "$ne": None},
        "$or": [
            {"provider_call_sid": call_sid},
            {"parent_call_sid": call_sid}
        ]
    })
    if not call:
        call = await db.contact_center_calls.find_one({
            "tenant_id": current_user.tenant_id,
            "$or": [
                {"provider_call_sid": call_sid},
                {"parent_call_sid": call_sid}
            ]
        })
    if not call:
        raise HTTPException(status_code=404, detail="Çağrı bulunamadı.")

    # Resolve recipient phone number securely on the server
    svc = get_field_encryption_service()
    recipient = svc.decrypt_value(call["caller_id_enc"]) if call.get("caller_id_enc") else None
    if not recipient:
        raise HTTPException(status_code=400, detail="Arayan numarası çözülemedi.")

    # Allowlist validation
    ALLOWED_TEMPLATES = {
        "hello_world",
        "reservation_confirmation",
        "checkin_welcome",
        "checkout_thank_you"
    }
    if payload.template_name not in ALLOWED_TEMPLATES:
        raise HTTPException(status_code=400, detail="Geçersiz şablon ismi.")

    from domains.contact_center.provider import get_communication_provider

    provider = get_communication_provider("whatsapp")
    if not provider:
        raise HTTPException(status_code=503, detail="WhatsApp sağlayıcısı bulunamadı.")

    res = await provider.send_whatsapp(
        db=db,
        tenant_id=current_user.tenant_id,
        recipient=recipient,
        in_session=False,
        template_name=payload.template_name,
        language_code=payload.language_code,
    )
    if not res.get("success"):
        raise HTTPException(status_code=502, detail="WhatsApp gönderimi başarısız.")

    # Write audit log entry
    from shared_kernel.audit_helper import audit_log
    await audit_log(
        actor_id=current_user.id,
        tenant_id=current_user.tenant_id,
        entity_type="contact_center_call",
        entity_id=call_sid,
        action="send_whatsapp",
        metadata={
            "template_name": payload.template_name,
            "language_code": payload.language_code,
        }
    )

    return {"status": "ok", "provider_message_id": res.get("provider_message_id")}


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

    # Access control: supervisor/admin override OR call ownership check
    from core.security import _is_super_admin
    from models.enums import UserRole
    from modules.pms_core.role_permission_service import RolePermissionService

    granted = getattr(current_user, "granted_permissions", None)
    has_perm = (
        _is_super_admin(current_user)
        or current_user.role in {UserRole.ADMIN, UserRole.SUPERVISOR}
        or current_user.role in {UserRole.ADMIN.value, UserRole.SUPERVISOR.value}
        or RolePermissionService().check_permission(current_user.role, "listen_call_recordings", granted)
    )

    if not has_perm:
        is_owner = doc.get("agent_id") == current_user.id
        if not is_owner:
            raise HTTPException(status_code=403, detail="Bu çağrı kaydını dinleme yetkiniz yok.")

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
    provider = TwilioVoiceProvider()
    if not provider.validate_signature(
        url=_public_url(request),
        params=form,
        signature=request.headers.get("X-Twilio-Signature", ""),
        request=request,
    ):
        return Response(
            content=provider.say_fallback("Çağrı doğrulanamadı."),
            media_type=_XML,
            status_code=403,
        )

    call_sid = form.get("CallSid", "")
    to_number = form.get("To", "")
    # Kiracı YALNIZCA sunucu-basılı client kimliğinden gelir (istemci geçemez).
    from_val = form.get("From", "") or form.get("Caller", "")
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

    call_attempt_id = form.get("call_attempt_id", "")
    if tenant_id and (call_attempt_id or call_sid):
        query = {"tenant_id": tenant_id, "$or": []}
        if call_attempt_id and user_id:
            query["$or"].append({
                "agent_id": user_id,
                "call_attempt_id": call_attempt_id
            })
        if call_sid:
            query["$or"].append({
                "provider_call_sid": call_sid
            })

        existing = await db.contact_center_calls.find_one(query)
        if existing:
            logger.info(f"[CC-VOICE-OUTBOUND-LOG] call_attempt_id={call_attempt_id} parent_call_sid={call_sid} response_action=hangup duplicate_detected=true")
            logger.info(f"[CC-VOICE-DIAG] Outbound duplicate attempt ignored (idempotency match): call_attempt_id={call_attempt_id} parent_call_sid={call_sid}")
            return Response(content="<Response><Hangup/></Response>", media_type=_XML)

    try:
        await record_outbound_call(
            db,
            tenant_id=tenant_id,
            provider_call_sid=call_sid,
            to_phone=sanitized,
            agent_id=user_id,
            call_attempt_id=call_attempt_id,
        )
    except DuplicateKeyError:
        logger.info(f"[CC-VOICE-OUTBOUND-LOG] call_attempt_id={call_attempt_id} parent_call_sid={call_sid} response_action=hangup duplicate_detected=true")
        logger.info(f"[CC-VOICE-DIAG] Outbound duplicate attempt caught (race condition): call_attempt_id={call_attempt_id}")
        return Response(content="<Response><Hangup/></Response>", media_type=_XML)

    logger.info(f"[CC-VOICE-OUTBOUND-LOG] call_attempt_id={call_attempt_id} parent_call_sid={call_sid} response_action=dial duplicate_detected=false")
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
    provider = TwilioVoiceProvider()
    if not provider.validate_signature(
        url=_public_url(request),
        params=form,
        signature=request.headers.get("X-Twilio-Signature", ""),
        request=request,
    ):
        return Response(status_code=403)

    call_sid = form.get("CallSid", "")
    tenant_id = await _resolve_tenant_id(request, form.get("To", ""))
    if tenant_id and call_sid:
        duration = form.get("CallDuration") or form.get("DialCallDuration")
        try:
            duration_i = int(duration) if duration else None
        except (TypeError, ValueError):
            duration_i = None
        await update_call_status(
            db,
            tenant_id=tenant_id,
            provider_call_sid=call_sid,
            twilio_status=form.get("CallStatus") or form.get("DialCallStatus") or "",
            duration_seconds=duration_i,
            parent_call_sid=form.get("ParentCallSid"),
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
    provider = TwilioVoiceProvider()
    if not provider.validate_signature(
        url=_public_url(request),
        params=form,
        signature=request.headers.get("X-Twilio-Signature", ""),
        request=request,
    ):
        return Response(status_code=403)

    tenant_id = await _resolve_tenant_id(request, form.get("To", ""))
    call_sid = form.get("CallSid", "")
    recording_url = form.get("RecordingUrl", "")
    if tenant_id and call_sid and recording_url:
        try:
            duration = int(form.get("RecordingDuration") or 0)
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


@public_router.post("/whatsapp/status")
async def whatsapp_status(request: Request):
    """Twilio WhatsApp status callback endpoint.

    Saves and updates delivery logs for WhatsApp messages.
    """
    form = await request.form()
    provider = TwilioVoiceProvider()
    if not provider.validate_signature(
        url=_public_url(request),
        params=form,
        signature=request.headers.get("X-Twilio-Signature", ""),
        request=request,
    ):
        return Response(status_code=403)

    message_sid = form.get("MessageSid")
    message_status = form.get("MessageStatus")  # queued, sent, delivered, read, failed, undelivered
    error_code = form.get("ErrorCode")

    logger.info(f"[CC-WHATSAPP] Received Twilio status callback: MessageSid={message_sid}, status={message_status}")

    if message_sid and message_status:
        from modules.messaging.models import DeliveryStatus
        status_map = {
            "queued": DeliveryStatus.QUEUED.value,
            "sending": DeliveryStatus.SENDING.value,
            "sent": DeliveryStatus.SENT.value,
            "delivered": DeliveryStatus.DELIVERED.value,
            "read": DeliveryStatus.DELIVERED.value,
            "failed": DeliveryStatus.FAILED.value,
            "undelivered": DeliveryStatus.FAILED.value
        }
        mapped_status = status_map.get(message_status.lower(), DeliveryStatus.QUEUED.value)

        update_fields = {
            "status": mapped_status,
            "updated_at": datetime.now(UTC).isoformat()
        }
        if message_status.lower() in ("delivered", "read"):
            update_fields["delivered_at"] = datetime.now(UTC).isoformat()
        if error_code:
            update_fields["error_message"] = f"Twilio Error {error_code}"

        await db.messaging_delivery_logs.update_one(
            {"provider_message_id": message_sid},
            {"$set": update_fields}
        )

    return Response(status_code=204)


# ── Contact Center Phase 2 - IVR, Queues, Agent States, Guest 360 ──

class QueueConfigCreate(BaseModel):
    name: str
    extension: str
    priority: int = 1
    queue_timeout_seconds: int = 300
    max_wait_limit: int = 10
    waiting_music_url: str | None = None
    fallback_target: str | None = None
    working_hours_start: str | None = None  # e.g. "08:00"
    working_hours_end: str | None = None  # e.g. "18:00"
    working_days: list[int] | None = None  # e.g. [1, 2, 3, 4, 5]
    holiday_redirect_phone: str | None = None
    sla_threshold_seconds: int = 20
    sla_target_percentage: int = 80


class QueueConfigUpdate(BaseModel):
    name: str | None = None
    extension: str | None = None
    priority: int | None = None
    queue_timeout_seconds: int | None = None
    max_wait_limit: int | None = None
    waiting_music_url: str | None = None
    fallback_target: str | None = None
    working_hours_start: str | None = None
    working_hours_end: str | None = None
    working_days: list[int] | None = None
    holiday_redirect_phone: str | None = None
    sla_threshold_seconds: int | None = None
    sla_target_percentage: int | None = None


class AgentStateUpdate(BaseModel):
    state: str

    @field_validator("state")
    @classmethod
    def validate_state(cls, v):
        allowed = {"ready", "break_short", "break_meal", "meeting", "training", "wrap_up", "offline"}
        if v not in allowed:
            raise ValueError(f"State must be one of {allowed}")
        return v


def _dec(svc, val: str | None) -> str | None:
    if not val:
        return None
    try:
        return svc.decrypt_value(val)
    except Exception:
        return "[şifreli veri]"


@router.post("/contact-center/queues", status_code=201)
async def create_queue(
    payload: QueueConfigCreate,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
    _perm=Depends(require_op("manage_contact_center")),
):
    existing = await db.contact_center_queues.find_one({
        "tenant_id": current_user.tenant_id,
        "extension": payload.extension
    })
    if existing:
        raise HTTPException(status_code=409, detail="Bu dahili numara zaten kullanılıyor.")

    doc = {
        "id": str(uuid4()),
        "tenant_id": current_user.tenant_id,
        "name": payload.name,
        "extension": payload.extension,
        "priority": payload.priority,
        "queue_timeout_seconds": payload.queue_timeout_seconds,
        "max_wait_limit": payload.max_wait_limit,
        "waiting_music_url": payload.waiting_music_url,
        "fallback_target": payload.fallback_target,
        "working_hours_start": payload.working_hours_start,
        "working_hours_end": payload.working_hours_end,
        "working_days": payload.working_days,
        "holiday_redirect_phone": payload.holiday_redirect_phone,
        "sla_threshold_seconds": payload.sla_threshold_seconds,
        "sla_target_percentage": payload.sla_target_percentage,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    await db.contact_center_queues.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/contact-center/queues")
async def list_queues(
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
    _perm=Depends(require_op("manage_contact_center")),
):
    cursor = db.contact_center_queues.find({"tenant_id": current_user.tenant_id})
    docs = await cursor.to_list(length=100)
    for d in docs:
        d.pop("_id", None)
    return {"queues": docs}


@router.get("/contact-center/queues/{queue_id}")
async def get_queue(
    queue_id: str,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
    _perm=Depends(require_op("manage_contact_center")),
):
    doc = await db.contact_center_queues.find_one({"id": queue_id, "tenant_id": current_user.tenant_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Kuyruk bulunamadı.")
    doc.pop("_id", None)
    return doc


@router.put("/contact-center/queues/{queue_id}")
async def update_queue(
    queue_id: str,
    payload: QueueConfigUpdate,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
    _perm=Depends(require_op("manage_contact_center")),
):
    doc = await db.contact_center_queues.find_one({"id": queue_id, "tenant_id": current_user.tenant_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Kuyruk bulunamadı.")

    payload_dict = payload.model_dump(exclude_unset=True)
    if not payload_dict:
        doc.pop("_id", None)
        return doc

    if "extension" in payload_dict and payload_dict["extension"] != doc["extension"]:
        existing = await db.contact_center_queues.find_one({
            "tenant_id": current_user.tenant_id,
            "extension": payload_dict["extension"]
        })
        if existing:
            raise HTTPException(status_code=409, detail="Bu dahili numara zaten kullanılıyor.")

    update_fields = dict(payload_dict)
    update_fields["updated_at"] = datetime.now(UTC)

    await db.contact_center_queues.update_one(
        {"id": queue_id, "tenant_id": current_user.tenant_id},
        {"$set": update_fields}
    )

    updated_doc = await db.contact_center_queues.find_one({"id": queue_id, "tenant_id": current_user.tenant_id})
    updated_doc.pop("_id", None)
    return updated_doc


@router.delete("/contact-center/queues/{queue_id}", status_code=204)
async def delete_queue(
    queue_id: str,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
    _perm=Depends(require_op("manage_contact_center")),
):
    res = await db.contact_center_queues.delete_one({"id": queue_id, "tenant_id": current_user.tenant_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kuyruk bulunamadı.")
    return Response(status_code=204)


async def set_agent_presence_state(tenant_id: str, agent_id: str, state_name: str) -> dict:
    now = datetime.now(UTC)
    last_active = await db.contact_center_agent_states.find_one({
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "ended_at": None
    })
    if last_active:
        if last_active["state"] == state_name:
            return last_active
        duration = int((now - last_active["started_at"]).total_seconds())
        await db.contact_center_agent_states.update_one(
            {"id": last_active["id"]},
            {"$set": {"ended_at": now, "duration_seconds": duration}}
        )

    doc = {
        "id": str(uuid4()),
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "state": state_name,
        "duration_seconds": 0,
        "started_at": now,
        "ended_at": None
    }
    await db.contact_center_agent_states.insert_one(doc)

    try:
        from core.ws_rooms import tenant_broadcast_room
        from websocket_server import sio
        await sio.emit(
            "contact_center:agent_state_update",
            {
                "agent_id": agent_id,
                "state": state_name,
            },
            room=tenant_broadcast_room(tenant_id),
        )
    except Exception:
        pass

    return doc


async def _delayed_wrap_up_expiration(tenant_id: str, agent_id: str) -> None:
    await asyncio.sleep(15)
    doc = await db.contact_center_agent_states.find_one({
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "ended_at": None
    })
    if doc and doc.get("state") == "wrap_up":
        await set_agent_presence_state(tenant_id, agent_id, "ready")


@router.post("/contact-center/agents/states")
async def update_agent_state(
    payload: AgentStateUpdate,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    doc = await set_agent_presence_state(current_user.tenant_id, current_user.id, payload.state)
    res = dict(doc)
    res.pop("_id", None)
    return res


@router.get("/contact-center/agents/my-state")
async def get_my_state(
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    state_doc = await db.contact_center_agent_states.find_one({
        "tenant_id": current_user.tenant_id,
        "agent_id": current_user.id,
        "ended_at": None
    })
    if not state_doc:
        return {"state": "offline", "duration_seconds": 0, "started_at": None}

    now = datetime.now(UTC)
    duration = int((now - state_doc["started_at"]).total_seconds())
    return {
        "state": state_doc["state"],
        "duration_seconds": duration,
        "started_at": state_doc["started_at"]
    }


@router.get("/contact-center/agents/states")
async def list_agents_states(
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
    _perm=Depends(require_op("manage_contact_center")),
):
    pipeline = [
        {"$match": {"tenant_id": current_user.tenant_id, "ended_at": None}},
        {"$lookup": {
            "from": "users",
            "localField": "agent_id",
            "foreignField": "id",
            "as": "user_info"
        }},
        {"$unwind": "$user_info"},
        {"$project": {
            "_id": 0,
            "agent_id": 1,
            "state": 1,
            "started_at": 1,
            "agent_name": "$user_info.name",
            "agent_username": "$user_info.username"
        }}
    ]
    cursor = db.contact_center_agent_states.aggregate(pipeline)
    items = await cursor.to_list(length=100)
    now = datetime.now(UTC)
    for item in items:
        item["duration_seconds"] = int((now - item["started_at"]).total_seconds())
    return {"agents": items}





@public_router.post("/inbound")
async def voice_inbound(request: Request):
    """Twilio incoming call webhook: Gelen çağrıyı karşılar ve IVR menüsünü sunar."""
    form = await request.form()
    provider = TwilioVoiceProvider()
    if not provider.validate_signature(
        url=_public_url(request),
        params=form,
        signature=request.headers.get("X-Twilio-Signature", ""),
        request=request,
    ):
        return Response(status_code=403)

    to_num = form.get("To") or ""
    tenant_id = await _resolve_tenant_id(request, to_num)
    if not tenant_id:
        return Response(content=provider.say_fallback("Hata: Otel bulunamadı."), media_type=_XML)

    tz_doc = await db.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0, "timezone": 1}) or {}
    tz_name = tz_doc.get("timezone") or "Europe/Istanbul"
    import zoneinfo
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = zoneinfo.ZoneInfo("Europe/Istanbul")

    now = datetime.now(tz)
    current_time_str = now.strftime("%H:%M")
    current_day = now.isoweekday()

    import holidays
    tr_holidays = holidays.Turkey(years=[now.year])
    is_holiday = now.date() in tr_holidays

    first_queue = await db.contact_center_queues.find_one({"tenant_id": tenant_id})
    if first_queue:
        wh_start = first_queue.get("working_hours_start")
        wh_end = first_queue.get("working_hours_end")
        wh_days = first_queue.get("working_days")

        is_working_day = current_day in wh_days if wh_days else True
        is_working_hour = True
        if wh_start and wh_end:
            is_working_hour = wh_start <= current_time_str <= wh_end

        if not is_working_day or not is_working_hour or is_holiday:
            redirect_phone = first_queue.get("holiday_redirect_phone")
            if redirect_phone:
                twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Say language="tr-TR">Çalışma saatleri dışındayız veya resmi tatildir. Nöbetçi hattımıza aktarılıyorsunuz.</Say><Dial>{redirect_phone}</Dial></Response>'
                return Response(content=twiml, media_type=_XML)
            else:
                twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Say language="tr-TR">Çalışma saatleri dışındayız veya resmi tatildir. Lütfen mesai saatleri içinde tekrar arayınız.</Say><Hangup/></Response>'
                return Response(content=twiml, media_type=_XML)

    cursor = db.contact_center_queues.find({"tenant_id": tenant_id}).sort("extension", 1)
    queues = await cursor.to_list(length=10)

    if not queues:
        twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Say language="tr-TR">Müşteri temsilcisine bağlanıyorsunuz.</Say><Enqueue>OperatorQueue</Enqueue></Response>'
        return Response(content=twiml, media_type=_XML)

    menu_parts = []
    for q in queues:
        menu_parts.append(f"{q['name']} için lütfen {q['extension']}'i tuşlayınız.")

    menu_text = "Hoş geldiniz. " + " ".join(menu_parts)
    gather_url = f"/api/voice/inbound/gather?tenant_id={tenant_id}"

    twiml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response>'
        f'<Gather action="{gather_url}" numDigits="1" timeout="5" language="tr-TR">'
        f'<Say language="tr-TR">{menu_text}</Say>'
        f'</Gather>'
        f'<Say language="tr-TR">Herhangi bir tuşlama yapmadınız. Tekrar dinlemek için bekleyiniz.</Say>'
        f'<Redirect>/api/voice/inbound?tenant_id={tenant_id}</Redirect>'
        f'</Response>'
    )
    return Response(content=twiml, media_type=_XML)


@public_router.post("/inbound/gather")
async def voice_inbound_gather(request: Request):
    """IVR tuşlamasını alır ve kuyruğa aktarır."""
    form = await request.form()
    provider = TwilioVoiceProvider()
    if not provider.validate_signature(
        url=_public_url(request),
        params=form,
        signature=request.headers.get("X-Twilio-Signature", ""),
        request=request,
    ):
        return Response(status_code=403)

    tenant_id = request.query_params.get("tenant_id")
    digits = form.get("Digits") or ""

    if not tenant_id:
        return Response(content=provider.say_fallback("Hata: Geçersiz istek."), media_type=_XML)

    queue = await db.contact_center_queues.find_one({
        "tenant_id": tenant_id,
        "extension": digits
    })

    if not queue:
        twiml = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response>'
            f'<Say language="tr-TR">Geçersiz bir tuşlama yaptınız.</Say>'
            f'<Redirect>/api/voice/inbound?tenant_id={tenant_id}</Redirect>'
            f'</Response>'
        )
        return Response(content=twiml, media_type=_XML)

    call_sid = form.get("CallSid") or ""
    from_phone = form.get("From") or ""

    await record_inbound_call(
        db,
        tenant_id=tenant_id,
        provider_call_sid=call_sid,
        from_phone=from_phone,
    )
    await db.contact_center_calls.update_one(
        {"provider_call_sid": call_sid, "tenant_id": tenant_id},
        {"$set": {"queue_id": queue["id"]}}
    )

    try:
        from core.ws_rooms import tenant_broadcast_room
        from websocket_server import sio
        await sio.emit(
            "contact_center:incoming_call",
            {
                "tenant_id": tenant_id,
                "call_id": call_sid,
                "from": from_phone,
            },
            room=tenant_broadcast_room(tenant_id),
        )
    except Exception as e:
        logger.warning(f"Failed to emit socket event for incoming call: {e}")

    route_url = f"/api/voice/inbound/route-queue?tenant_id={tenant_id}&queue_id={queue['id']}"
    twiml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response>'
        f'<Redirect>{route_url}</Redirect>'
        f'</Response>'
    )
    return Response(content=twiml, media_type=_XML)


@public_router.post("/inbound/route-queue")
async def voice_route_queue(request: Request):
    """Sıradaki uygun ajanı (en uzun süredir ready olan) seçer ve arar."""
    form = await request.form()
    provider = TwilioVoiceProvider()
    if not provider.validate_signature(
        url=_public_url(request),
        params=form,
        signature=request.headers.get("X-Twilio-Signature", ""),
        request=request,
    ):
        return Response(status_code=403)

    tenant_id = request.query_params.get("tenant_id")
    queue_id = request.query_params.get("queue_id")
    call_sid = form.get("CallSid") or ""

    if not tenant_id or not queue_id:
        return Response(content=provider.say_fallback("Hata: Geçersiz kuyruk parametreleri."), media_type=_XML)

    # 1. Fetch queue configuration
    queue = await db.contact_center_queues.find_one({"id": queue_id, "tenant_id": tenant_id})
    if not queue:
        return Response(content=provider.say_fallback("Hata: Kuyruk bulunamadı."), media_type=_XML)

    # 2. Check maximum wait timeout
    call_doc = await db.contact_center_calls.find_one({"provider_call_sid": call_sid, "tenant_id": tenant_id})
    if call_doc and call_doc.get("started_at"):
        elapsed = (datetime.now(UTC) - call_doc["started_at"]).total_seconds()
        timeout_limit = queue.get("queue_timeout_seconds") or 300
        if elapsed >= timeout_limit:
            # Trigger fallback routing
            redirect_phone = queue.get("holiday_redirect_phone")
            if redirect_phone:
                twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Say language="tr-TR">Temsilcilerimize şu anda ulaşılamıyor. Nöbetçi hattımıza aktarılıyorsunuz.</Say><Dial>{redirect_phone}</Dial></Response>'
                return Response(content=twiml, media_type=_XML)
            else:
                twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Say language="tr-TR">Üzgünüz, tüm müşteri temsilcilerimiz şu anda meşgul. Lütfen daha sonra tekrar arayınız.</Say><Hangup/></Response>'
                return Response(content=twiml, media_type=_XML)

    # 3. Find dialed agents for this call session to avoid routing loop
    dialed_agents = call_doc.get("dialed_agents") or [] if call_doc else []

    # 4. Find all ready agents for this tenant (ended_at is None, state is "ready")
    cursor = db.contact_center_agent_states.find({
        "tenant_id": tenant_id,
        "state": "ready",
        "ended_at": None,
        "agent_id": {"$nin": dialed_agents}
    }).sort("started_at", 1)  # Longest idle first
    ready_states = await cursor.to_list(length=10)

    if ready_states:
        # Select the longest idle agent
        selected_state = ready_states[0]
        selected_agent_id = selected_state["agent_id"]

        # Append to dialed_agents in DB
        await db.contact_center_calls.update_one(
            {"provider_call_sid": call_sid, "tenant_id": tenant_id},
            {"$addToSet": {"dialed_agents": selected_agent_id}, "$set": {"agent_id": selected_agent_id}}
        )

        dial_action_url = f"/api/voice/inbound/dial-action?tenant_id={tenant_id}&queue_id={queue_id}&agent_id={selected_agent_id}"
        agent_callback_url = f"/api/voice/agent-status-callback?tenant_id={tenant_id}&agent_id={selected_agent_id}"

        twiml = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response>'
            f'<Dial action="{dial_action_url}" timeout="15">'
            f'<Client statusCallbackEvent="initiated ringing answered completed" statusCallback="{agent_callback_url}">'
            f'client:{tenant_id}:{selected_agent_id}'
            f'</Client>'
            f'</Dial>'
            f'</Response>'
        )
        return Response(content=twiml, media_type=_XML)

    # 5. No agent available -> Play wait music and retry
    twiml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response>'
        f'<Say language="tr-TR">Lütfen bekleyiniz, tüm temsilcilerimiz şu anda meşguldür.</Say>'
        f'<Play>http://demo.twilio.com/docs/classic.mp3</Play>'
        f'<Redirect>/api/voice/inbound/route-queue?tenant_id={tenant_id}&amp;queue_id={queue_id}</Redirect>'
        f'</Response>'
    )
    return Response(content=twiml, media_type=_XML)


@public_router.post("/inbound/dial-action")
async def voice_dial_action(request: Request):
    """Ajan araması sonlandığında çalışır. Cevapsızsa sıradakine yönlendirir."""
    form = await request.form()
    provider = TwilioVoiceProvider()
    if not provider.validate_signature(
        url=_public_url(request),
        params=form,
        signature=request.headers.get("X-Twilio-Signature", ""),
        request=request,
    ):
        return Response(status_code=403)

    tenant_id = request.query_params.get("tenant_id")
    queue_id = request.query_params.get("queue_id")
    dial_status = form.get("DialCallStatus") or ""

    if dial_status == "completed":
        # The call was successfully answered and has completed (hung up)
        twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'
        return Response(content=twiml, media_type=_XML)

    # If not completed (e.g. no-answer, busy, failed), route to the next agent
    route_url = f"/api/voice/inbound/route-queue?tenant_id={tenant_id}&queue_id={queue_id}"
    twiml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response>'
        f'<Redirect>{route_url}</Redirect>'
        f'</Response>'
    )
    return Response(content=twiml, media_type=_XML)


@public_router.post("/agent-status-callback")
async def voice_agent_status_callback(request: Request):
    """Twilio agent client leg status callback'i. Ajan durum geçişlerini yapar."""
    form = await request.form()
    provider = TwilioVoiceProvider()
    if not provider.validate_signature(
        url=_public_url(request),
        params=form,
        signature=request.headers.get("X-Twilio-Signature", ""),
        request=request,
    ):
        return Response(status_code=403)

    tenant_id = request.query_params.get("tenant_id")
    agent_id = request.query_params.get("agent_id")
    call_status = form.get("CallStatus") or ""

    if tenant_id and agent_id:
        if call_status == "in-progress":
            # Call answered -> agent goes to "on_call"
            await set_agent_presence_state(tenant_id, agent_id, "on_call")
        elif call_status == "completed":
            # Call ended -> agent goes to "wrap_up" and triggers delayed expiration back to ready
            await set_agent_presence_state(tenant_id, agent_id, "wrap_up")
            asyncio.create_task(_delayed_wrap_up_expiration(tenant_id, agent_id))

    return Response(status_code=204)


@public_router.post("/queue/wait-music")
async def voice_queue_wait_music(request: Request):
    """Kuyrukta bekleyen kullanıcı için bekleme müziği ve anons TwiML'i."""
    twiml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response>'
        f'<Play>http://demo.twilio.com/docs/classic.mp3</Play>'
        f'</Response>'
    )
    return Response(content=twiml, media_type=_XML)


# ── Supervisor Dashboard & Operations Endpoints ──

class SupervisorActionPayload(BaseModel):
    action: str  # force_state, transfer_call, move_queue
    agent_id: str | None = None
    target_state: str | None = None
    call_sid: str | None = None
    target_agent_id: str | None = None
    target_queue_id: str | None = None


class IntervenePayload(BaseModel):
    action: str  # listen, whisper, barge
    call_sid: str


class CallDispositionPayload(BaseModel):
    call_id: str
    disposition: str
    notes: str | None = None
    tags: list[str] | None = None
    callback_at: str | None = None
    linked_reservation_id: str | None = None
    linked_complaint_id: str | None = None


@router.get("/supervisor/dashboard")
async def get_supervisor_dashboard(
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    if current_user.role not in {"supervisor", "admin", "super_admin"}:
        raise HTTPException(status_code=403, detail="Yalnızca yönetici veya supervisor bu işlemi gerçekleştirebilir.")

    tenant_id = current_user.tenant_id
    now = datetime.now(UTC)
    today_start = datetime(now.year, now.month, now.day, tzinfo=UTC)

    # 1. Active calls (ringing, answered)
    cursor_active = db.contact_center_calls.find({
        "tenant_id": tenant_id,
        "status": {"$in": ["ringing", "answered"]}
    })
    active_calls = await cursor_active.to_list(length=100)
    for c in active_calls:
        c.pop("_id", None)
        c["started_at"] = c["started_at"].isoformat() if c.get("started_at") else None
        c["answered_at"] = c["answered_at"].isoformat() if c.get("answered_at") else None

    # 2. Queued callers (status ringing and no agent_id)
    queued_callers = [c for c in active_calls if c.get("status") == "ringing" and not c.get("agent_id")]

    # 3. Longest wait time in queue
    longest_wait = 0
    for q_call in queued_callers:
        if q_call.get("started_at"):
            started = datetime.fromisoformat(q_call["started_at"])
            wait = (now - started).total_seconds()
            if wait > longest_wait:
                longest_wait = int(wait)

    # 4. Agent counts by state
    cursor_states = db.contact_center_agent_states.find({
        "tenant_id": tenant_id,
        "ended_at": None
    })
    states = await cursor_states.to_list(length=200)
    counts = {"ready": 0, "on_call": 0, "wrap_up": 0, "break": 0, "offline": 0}
    for s in states:
        state_name = s["state"]
        if state_name == "ready":
            counts["ready"] += 1
        elif state_name == "on_call":
            counts["on_call"] += 1
        elif state_name == "wrap_up":
            counts["wrap_up"] += 1
        elif state_name.startswith("break_"):
            counts["break"] += 1
        elif state_name == "offline":
            counts["offline"] += 1

    # 5. Average answer time today
    cursor_answered_today = db.contact_center_calls.find({
        "tenant_id": tenant_id,
        "answered_at": {"$gte": today_start}
    })
    answered_today = await cursor_answered_today.to_list(length=1000)
    answer_times = []
    for c in answered_today:
        if c.get("answered_at") and c.get("started_at"):
            answer_times.append((c["answered_at"] - c["started_at"]).total_seconds())
    avg_answer_time = sum(answer_times) / len(answer_times) if answer_times else 0

    # 6. Abandoned call rate today
    total_calls_today = await db.contact_center_calls.count_documents({
        "tenant_id": tenant_id,
        "started_at": {"$gte": today_start}
    })
    abandoned_calls_today = await db.contact_center_calls.count_documents({
        "tenant_id": tenant_id,
        "status": {"$in": ["missed", "failed"]},
        "started_at": {"$gte": today_start}
    })
    abandoned_rate = abandoned_calls_today / total_calls_today if total_calls_today > 0 else 0

    # 7. SLA metrics per queue
    cursor_queues = db.contact_center_queues.find({"tenant_id": tenant_id})
    queues = await cursor_queues.to_list(length=20)
    queue_slas = []
    for q in queues:
        q_id = q["id"]
        threshold = q.get("sla_threshold_seconds") or 20
        target = q.get("sla_target_percentage") or 80

        # Filter calls for this queue today
        q_calls = [c for c in answered_today if c.get("queue_id") == q_id]
        total_q = len(q_calls)
        met_q = 0
        for c in q_calls:
            if c.get("answered_at") and c.get("started_at"):
                duration = (c["answered_at"] - c["started_at"]).total_seconds()
                if duration <= threshold:
                    met_q += 1

        pct = (met_q / total_q * 100) if total_q > 0 else 100.0
        status_color = "green"
        if pct < target - 10:
            status_color = "red"
        elif pct < target:
            status_color = "yellow"

        queue_slas.append({
            "queue_id": q_id,
            "name": q["name"],
            "sla_threshold_seconds": threshold,
            "sla_target_percentage": target,
            "actual_percentage": pct,
            "status": status_color
        })

    return {
        "active_calls_count": len(active_calls),
        "queued_callers_count": len(queued_callers),
        "longest_wait_seconds": longest_wait,
        "average_answer_time_seconds": avg_answer_time,
        "abandoned_rate": abandoned_rate,
        "agent_states": counts,
        "queue_slas": queue_slas
    }


@router.get("/supervisor/agents")
async def get_supervisor_agents(
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    if current_user.role not in {"supervisor", "admin", "super_admin"}:
        raise HTTPException(status_code=403, detail="Yalnızca yönetici veya supervisor bu işlemi gerçekleştirebilir.")

    tenant_id = current_user.tenant_id
    now = datetime.now(UTC)
    today_start = datetime(now.year, now.month, now.day, tzinfo=UTC)

    # Find all users with role call_center_agent or who have active states
    cursor_agents = db.users.find({"tenant_id": tenant_id, "role": {"$in": ["call_center_agent", "supervisor", "admin"]}})
    agents = await cursor_agents.to_list(length=200)

    res = []
    for a in agents:
        # Get active state
        state_doc = await db.contact_center_agent_states.find_one({
            "tenant_id": tenant_id,
            "agent_id": a["id"],
            "ended_at": None
        })
        state = state_doc["state"] if state_doc else "offline"
        state_duration = int((now - state_doc["started_at"]).total_seconds()) if state_doc else 0

        # Calculate active call duration
        call_duration = 0
        if state == "on_call":
            active_call = await db.contact_center_calls.find_one({
                "tenant_id": tenant_id,
                "agent_id": a["id"],
                "status": "answered"
            })
            if active_call and active_call.get("answered_at"):
                call_duration = int((now - active_call["answered_at"]).total_seconds())

        # Calls answered & missed today
        answered_today = await db.contact_center_calls.count_documents({
            "tenant_id": tenant_id,
            "agent_id": a["id"],
            "status": "completed",
            "answered_at": {"$gte": today_start}
        })

        # Missed checks: agent was in dialed_agents list but didn't answer
        missed_today = await db.contact_center_calls.count_documents({
            "tenant_id": tenant_id,
            "dialed_agents": a["id"],
            "agent_id": {"$ne": a["id"]},
            "started_at": {"$gte": today_start}
        })

        # Average handle time today
        cursor_calls = db.contact_center_calls.find({
            "tenant_id": tenant_id,
            "agent_id": a["id"],
            "status": "completed",
            "answered_at": {"$gte": today_start}
        })
        calls = await cursor_calls.to_list(length=1000)
        durations = [c.get("duration_seconds") or 0 for c in calls]
        avg_handle_time = sum(durations) / len(durations) if durations else 0

        res.append({
            "agent_id": a["id"],
            "name": a.get("name") or a.get("username"),
            "username": a.get("username"),
            "state": state,
            "state_duration_seconds": state_duration,
            "active_call_duration_seconds": call_duration,
            "assigned_queues": ["Rezervasyon", "Resepsiyon"],  # Default/mock queues
            "answered_today": answered_today,
            "missed_today": missed_today,
            "average_handle_time_seconds": avg_handle_time
        })

    return {"agents": res}


@router.post("/supervisor/actions")
async def post_supervisor_action(
    payload: SupervisorActionPayload,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    if current_user.role not in {"supervisor", "admin", "super_admin"}:
        raise HTTPException(status_code=403, detail="Yalnızca yönetici veya supervisor bu işlemi gerçekleştirebilir.")

    tenant_id = current_user.tenant_id

    if payload.action == "force_state":
        if not payload.agent_id or not payload.target_state:
            raise HTTPException(status_code=400, detail="Eksik ajan veya hedef durum bilgisi.")
        # Perform state override
        await set_agent_presence_state(tenant_id, payload.agent_id, payload.target_state)
        # Log audit log
        from shared_kernel.audit_helper import audit_log
        await audit_log(
            actor_id=current_user.id,
            tenant_id=tenant_id,
            entity_type="contact_center_agent",
            entity_id=payload.agent_id,
            action="supervisor_force_state",
            metadata={"target_state": payload.target_state}
        )
        return {"success": True, "detail": f"Ajan {payload.agent_id} durumu {payload.target_state} olarak güncellendi."}

    elif payload.action == "transfer_call":
        if not payload.call_sid or (not payload.target_agent_id and not payload.target_queue_id):
            raise HTTPException(status_code=400, detail="Eksik çağrı veya hedef bilgisi.")
        # Perform transfer updates in DB
        update_fields = {}
        if payload.target_agent_id:
            update_fields["agent_id"] = payload.target_agent_id
        if payload.target_queue_id:
            update_fields["queue_id"] = payload.target_queue_id

        await db.contact_center_calls.update_one(
            {"provider_call_sid": payload.call_sid, "tenant_id": tenant_id},
            {"$set": update_fields}
        )
        from shared_kernel.audit_helper import audit_log
        await audit_log(
            actor_id=current_user.id,
            tenant_id=tenant_id,
            entity_type="contact_center_call",
            entity_id=payload.call_sid,
            action="supervisor_transfer_call",
            metadata=update_fields
        )
        return {"success": True, "detail": "Çağrı aktarma işlemi tamamlandı."}

    elif payload.action == "move_queue":
        if not payload.call_sid or not payload.target_queue_id:
            raise HTTPException(status_code=400, detail="Eksik çağrı veya kuyruk bilgisi.")
        await db.contact_center_calls.update_one(
            {"provider_call_sid": payload.call_sid, "tenant_id": tenant_id},
            {"$set": {"queue_id": payload.target_queue_id}}
        )
        from shared_kernel.audit_helper import audit_log
        await audit_log(
            actor_id=current_user.id,
            tenant_id=tenant_id,
            entity_type="contact_center_call",
            entity_id=payload.call_sid,
            action="supervisor_move_queue",
            metadata={"target_queue_id": payload.target_queue_id}
        )
        return {"success": True, "detail": "Kuyruk taşıma işlemi tamamlandı."}

    raise HTTPException(status_code=400, detail="Geçersiz aksiyon.")


@router.post("/supervisor/intervene")
async def post_supervisor_intervene(
    payload: IntervenePayload,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    if current_user.role not in {"supervisor", "admin", "super_admin"}:
        raise HTTPException(status_code=403, detail="Yalnızca yönetici veya supervisor bu işlemi gerçekleştirebilir.")

    # Audit log the intervention action
    from shared_kernel.audit_helper import audit_log
    await audit_log(
        actor_id=current_user.id,
        tenant_id=current_user.tenant_id,
        entity_type="contact_center_call",
        entity_id=payload.call_sid,
        action=f"supervisor_{payload.action}",
        metadata={"supervisor_agent_id": current_user.id}
    )

    # Return intervention details for simulation/TwiML
    return {
        "success": True,
        "action": payload.action,
        "call_sid": payload.call_sid,
        "supervisor_client_id": f"client:{current_user.tenant_id}:{current_user.id}"
    }


@router.post("/agents/disposition")
async def post_agent_disposition(
    payload: CallDispositionPayload,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    tenant_id = current_user.tenant_id

    doc = {
        "id": str(uuid4()),
        "tenant_id": tenant_id,
        "call_id": payload.call_id,
        "agent_id": current_user.id,
        "disposition": payload.disposition,
        "notes": payload.notes,
        "tags": payload.tags or [],
        "callback_at": payload.callback_at,
        "linked_reservation_id": payload.linked_reservation_id,
        "linked_complaint_id": payload.linked_complaint_id,
        "created_at": datetime.now(UTC)
    }
    await db.contact_center_dispositions.insert_one(doc)

    # Transition agent back to ready state immediately (closing wrap_up)
    await set_agent_presence_state(tenant_id, current_user.id, "ready")

    return {"success": True, "detail": "Çağrı değerlendirme formu kaydedildi ve Müsait durumuna geçildi."}


@router.get("/callbacks")
async def get_callbacks(
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    cursor = db.contact_center_callbacks.find({
        "tenant_id": current_user.tenant_id,
        "status": "pending"
    }).sort("abandoned_at", -1)
    docs = await cursor.to_list(length=100)
    for d in docs:
        d.pop("_id", None)
        d["abandoned_at"] = d["abandoned_at"].isoformat() if d.get("abandoned_at") else None
    return {"callbacks": docs}


@router.post("/callbacks/{callback_id}/assign")
async def post_callback_assign(
    callback_id: str,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    res = await db.contact_center_callbacks.update_one(
        {"id": callback_id, "tenant_id": current_user.tenant_id, "status": "pending"},
        {"$set": {
            "status": "assigned",
            "assigned_agent_id": current_user.id,
            "assigned_at": datetime.now(UTC)
        }}
    )
    if not getattr(res, "matched_count", 0):
        raise HTTPException(status_code=404, detail="Geri arama kaydı bulunamadı veya atanmış durumda.")
    return {"success": True, "detail": "Geri arama kaydı atandı."}


@router.post("/callbacks/{callback_id}/complete")
async def post_callback_complete(
    callback_id: str,
    result: str = "completed",
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    res = await db.contact_center_callbacks.update_one(
        {"id": callback_id, "tenant_id": current_user.tenant_id},
        {"$set": {
            "status": "completed",
            "resolved_at": datetime.now(UTC),
            "result": result
        }}
    )
    if not getattr(res, "matched_count", 0):
        raise HTTPException(status_code=404, detail="Geri arama kaydı bulunamadı.")
    return {"success": True, "detail": "Geri arama kaydı tamamlandı."}
