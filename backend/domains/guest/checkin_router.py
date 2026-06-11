"""
Domain Router: Online Check-in & Pre-Arrival

Extracted from legacy_routes.py — online check-in submission,
upsell acceptance, pre-arrival communications.
"""
import base64
import binascii
import logging
import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from core.audit import log_audit_event
from core.database import db
from core.security import get_current_user
from domains.guest.checkin_id_photo_storage import load_id_photo, save_id_photo
from models.schemas import User
from modules.pms_core.role_permission_service import MODULE_ROLES  # v97 DW
from modules.pms_core.role_permission_service import require_module as require_module_v97  # v97 DW
from security.upload_validator import MAX_IMAGE_BYTES

logger = logging.getLogger("domains.guest.checkin_router")

router = APIRouter(prefix="/api", tags=["checkin-domain"])

# --- Signature SVG sanitization ----------------------------------------------
# The mobile guest app sends a handwritten signature as an SVG string. Any
# admin/front-desk surface that renders this SVG inline (e.g. inside a
# WebView, an HTML report, or a registration card PDF) would otherwise be
# vulnerable to stored XSS. We strip the obvious vectors here before persist.
_SIG_SVG_MAX_BYTES = 256 * 1024  # 256 KiB is plenty for a stroke-only SVG
_SIG_SCRIPT_RE = re.compile(r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL)
_SIG_OPEN_SCRIPT_RE = re.compile(r"<\s*script\b[^>]*/?\s*>", re.IGNORECASE)
_SIG_FOREIGN_OBJECT_RE = re.compile(
    r"<\s*foreignObject\b[^>]*>.*?<\s*/\s*foreignObject\s*>", re.IGNORECASE | re.DOTALL
)
_SIG_EVENT_HANDLER_RE = re.compile(r"\son[a-z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)
_SIG_JS_URI_RE = re.compile(r"(?:href|xlink:href)\s*=\s*([\"'])\s*javascript:[^\"']*\1", re.IGNORECASE)


def _sanitize_signature_svg(raw: str | None) -> str | None:
    """Best-effort sanitization of guest-supplied signature SVG.

    Returns the cleaned SVG, or None if the input is missing / not a plausible
    SVG / would be empty after cleaning. We do *not* attempt full XML parsing
    because the signature pad emits a strictly-controlled subset (svg + path
    elements only); we just remove the script-style attack surface defensively.
    """
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    if len(s.encode("utf-8")) > _SIG_SVG_MAX_BYTES:
        return None
    # Must look like an SVG document; reject anything else outright.
    if "<svg" not in s.lower():
        return None
    s = _SIG_SCRIPT_RE.sub("", s)
    s = _SIG_OPEN_SCRIPT_RE.sub("", s)
    s = _SIG_FOREIGN_OBJECT_RE.sub("", s)
    s = _SIG_EVENT_HANDLER_RE.sub("", s)
    s = _SIG_JS_URI_RE.sub("", s)
    cleaned = s.strip()
    return cleaned or None


def _allow_frontdesk_or_guest(current_user: User = Depends(get_current_user)) -> User:
    """Allow staff with frontdesk module access OR a guest_app user (own check-in)."""
    role = getattr(current_user.role, "value", str(current_user.role))
    allowed = {getattr(r, "value", str(r)) for r in MODULE_ROLES.get("frontdesk", set())}
    allowed.add("guest_app")
    if role not in allowed:
        from core.security import _is_super_admin
        if not _is_super_admin(current_user):
            raise HTTPException(status_code=403, detail="Online check-in yetkisi yok")
    return current_user


async def _assert_booking_accessible(
    booking_id: str, current_user: User
) -> dict:
    """Resolve a booking and enforce ownership (guest_app sees only own booking)."""
    booking = await db.bookings.find_one(
        {"id": booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    role = getattr(current_user.role, "value", str(current_user.role))
    if role == "guest_app":
        from security.encrypted_lookup import build_guest_pii_query
        guest_doc = await db.guests.find_one(
            {"tenant_id": current_user.tenant_id, **build_guest_pii_query("email", current_user.email)},
            {"_id": 0, "id": 1},
        )
        if not guest_doc or booking.get("guest_id") != guest_doc.get("id"):
            raise HTTPException(status_code=403, detail="Bu rezervasyon size ait değil")
    return booking


@router.post("/checkin/online/{booking_id}/id-photo")
async def upload_online_checkin_id_photo(
    booking_id: str,
    photo: UploadFile = File(...),
    current_user: User = Depends(_allow_frontdesk_or_guest),
):
    """Stage a guest ID photo before submitting the online check-in form.

    Multipart upload path:
      - Validated with magic-bytes (rejects SVG/PDF/polyglots) and size-capped.
      - Encrypted with the platform crypto service (AES-256-GCM + HKDF key,
        AAD-bound to tenant + booking + photo_id) before being written to a
        private filesystem location outside the public ``/api/uploads`` mount.
      - Plaintext bytes never touch the database; only sha-256 hash and
        sanitized metadata are recorded.

    Returns ``{photo_id, sha256, content_type, size_bytes}``; supply
    ``photo_id`` as ``id_photo_id`` in the subsequent JSON check-in submission.
    """
    booking = await _assert_booking_accessible(booking_id, current_user)
    file_bytes = await photo.read(MAX_IMAGE_BYTES + 1)
    stored = save_id_photo(
        tenant_id=current_user.tenant_id,
        booking_id=booking_id,
        image_bytes=file_bytes,
        field_label="Kimlik fotografi",
    )

    # Stage metadata so a later checkin submission can claim this photo and
    # so orphan-cleanup jobs can age out abandoned uploads.
    stage_doc = {
        **stored.to_dict(),
        "guest_id": booking.get("guest_id"),
        "uploaded_by": current_user.id,
        "uploaded_by_role": getattr(current_user.role, "value", str(current_user.role)),
        "uploaded_at": datetime.now(UTC).isoformat(),
        "claimed": False,
    }
    await db.online_checkin_id_photos.insert_one(stage_doc)

    return {
        "photo_id": stored.photo_id,
        "sha256": stored.sha256,
        "content_type": stored.content_type,
        "size_bytes": stored.size_bytes,
    }


@router.post("/checkin/online")
async def submit_online_checkin(
    checkin_data: dict,
    current_user: User = Depends(_allow_frontdesk_or_guest),
):
    """Online check-in submission"""
    from pydantic import ValidationError

    from domains.guest.online_checkin_models import OnlineCheckinRequest

    # Body raw dict olarak alınıyor (legacy kontrat); pydantic doğrulamasını
    # burada elle çağırıyoruz. Eksik/yanlış alanlarda ValidationError'ı yakalayıp
    # FastAPI'nin standart 422 sözleşmesine dönüştürüyoruz — aksi halde
    # ValidationError handler'a düşmeden 500 üretir (F8K stres NO-GO P1).
    if not isinstance(checkin_data, dict):
        raise HTTPException(status_code=422, detail="Geçersiz istek gövdesi")
    try:
        request = OnlineCheckinRequest(**checkin_data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except TypeError as exc:
        # Beklenmeyen kwarg / pozisyonel argüman uyuşmazlıkları da
        # client-side hata olarak işaretlensin (500 değil).
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    booking = await _assert_booking_accessible(request.booking_id, current_user)

    # Sanitize any drawn signature once, up front; both validation and
    # persistence below use the cleaned value so a malicious-only payload
    # (e.g. <svg><script>...</script></svg>) cannot satisfy the contract or
    # be stored. Staff submissions go through the same scrubbing.
    sanitized_svg = _sanitize_signature_svg(request.signature_svg)

    # Guest-app callers must satisfy the digital-signature contract and the
    # 06:00-on-check-in-day eligibility gate (mirror of the mobile UI rule).
    role = getattr(current_user.role, "value", str(current_user.role))
    if role == "guest_app":
        # Digital-signature contract: explicit consent + either a drawn
        # signature (sanitized SVG) or a typed full name (accessibility
        # fallback). Booking ownership is already enforced by
        # _assert_booking_accessible.
        has_drawn = sanitized_svg is not None
        has_typed = bool((request.signature_text or "").strip())
        if not (request.signature_consent and (has_drawn or has_typed)):
            raise HTTPException(status_code=400, detail="Dijital imza onayı gerekli")
        # 06:00 eligibility: online check-in opens at 06:00 on the check-in
        # day in the property's local timezone. Mobile uses device-local time
        # (Turkish guests in Türkiye), so we evaluate the gate in
        # Europe/Istanbul to keep client and server consistent.
        ci_raw = booking.get("check_in")
        if ci_raw:
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo("Europe/Istanbul")
            except Exception:
                tz = None
            try:
                ci_str = ci_raw if isinstance(ci_raw, str) else ci_raw.isoformat()
                ci_date = datetime.fromisoformat(ci_str.replace("Z", "+00:00")).date()
            except Exception:
                ci_date = None
            if ci_date is not None:
                now_local = datetime.now(tz) if tz else datetime.now(UTC)
                today = now_local.date()
                if today < ci_date or (today == ci_date and now_local.hour < 6):
                    raise HTTPException(
                        status_code=400,
                        detail="Online check-in giriş günü saat 06:00'dan itibaren açılır",
                    )

    # ── Resolve the ID photo: prefer a previously-staged multipart upload
    #    (id_photo_id), fall back to legacy inline base64. In both cases the
    #    bytes are encrypted at rest via core.crypto and only metadata lands
    #    in MongoDB — never the raw image.
    id_photo_meta: dict | None = None
    if request.id_photo_id:
        stage_doc = await db.online_checkin_id_photos.find_one(
            {
                "photo_id": request.id_photo_id,
                "tenant_id": current_user.tenant_id,
                "booking_id": request.booking_id,
            },
            {"_id": 0},
        )
        if not stage_doc:
            raise HTTPException(
                status_code=400,
                detail="Kimlik fotografi bulunamadi veya bu rezervasyona ait degil.",
            )
        id_photo_meta = {
            "photo_id": stage_doc["photo_id"],
            "sha256": stage_doc.get("sha256"),
            "content_type": stage_doc.get("content_type"),
            "size_bytes": stage_doc.get("size_bytes"),
            "extension": stage_doc.get("extension"),
            "source": "multipart_upload",
        }
    elif request.id_photo_base64:
        try:
            raw = base64.b64decode(request.id_photo_base64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(
                status_code=400,
                detail="Kimlik fotografi gecersiz base64 verisi iceriyor.",
            )
        stored = save_id_photo(
            tenant_id=current_user.tenant_id,
            booking_id=request.booking_id,
            image_bytes=raw,
            field_label="Kimlik fotografi",
        )
        await db.online_checkin_id_photos.insert_one({
            **stored.to_dict(),
            "guest_id": booking.get("guest_id"),
            "uploaded_by": current_user.id,
            "uploaded_by_role": role,
            "uploaded_at": datetime.now(UTC).isoformat(),
            "claimed": True,
            "source": "legacy_inline_base64",
        })
        id_photo_meta = {
            **stored.to_dict(),
            "source": "legacy_inline_base64",
        }

    checkin_record = {
        "id": str(uuid.uuid4()),
        "booking_id": request.booking_id,
        "tenant_id": current_user.tenant_id,
        "guest_id": booking["guest_id"],
        "passport_number": request.passport_number,
        "passport_expiry": request.passport_expiry,
        "nationality": request.nationality,
        "estimated_arrival_time": request.estimated_arrival_time,
        "flight_number": request.flight_number,
        "coming_from": request.coming_from,
        "room_view": request.room_view,
        "floor_preference": request.floor_preference,
        "bed_type": request.bed_type,
        "pillow_type": request.pillow_type,
        "room_temperature": request.room_temperature,
        "special_requests": request.special_requests,
        "dietary_restrictions": request.dietary_restrictions,
        "accessibility_needs": request.accessibility_needs,
        "newspaper_preference": request.newspaper_preference,
        "smoking_preference": request.smoking_preference,
        "connecting_rooms": request.connecting_rooms,
        "quiet_room": request.quiet_room,
        "mobile_number": request.mobile_number,
        "whatsapp_number": request.whatsapp_number,
        # Identity & digital signature.
        # ID-photo bytes live encrypted on disk via core.crypto; the DB only
        # records the opaque reference + sanitized metadata so a DB dump never
        # leaks the photo.
        "id_photo": id_photo_meta,
        "id_photo_uploaded": id_photo_meta is not None,
        "signature_text": (request.signature_text or "").strip() or None,
        "signature_svg": sanitized_svg,
        "signature_method": (
            "drawn" if sanitized_svg
            else ("typed" if (request.signature_text or "").strip() else None)
        ),
        "signature_consent": bool(request.signature_consent),
        "signed_at": datetime.now(UTC).isoformat() if request.signature_consent else None,
        "status": "pending",
        "submitted_at": datetime.now(UTC).isoformat(),
        "processed": False,
    }
    await db.online_checkins.insert_one(checkin_record)

    if id_photo_meta:
        # Tie the staged photo to the freshly-created checkin record so staff
        # can locate it via either the photo_id or the checkin_id.
        await db.online_checkin_id_photos.update_one(
            {"photo_id": id_photo_meta["photo_id"], "tenant_id": current_user.tenant_id},
            {"$set": {"claimed": True, "checkin_id": checkin_record["id"]}},
        )

    await db.bookings.update_one(
        {"id": request.booking_id, "tenant_id": current_user.tenant_id},
        {
            "$set": {
                "online_checkin_completed": True,
                "online_checkin_at": datetime.now(UTC).isoformat(),
                "special_requests": request.special_requests,
                "estimated_arrival_time": request.estimated_arrival_time,
            }
        },
    )

    upsell_offers = []
    current_room = await db.rooms.find_one(
        {"id": booking["room_id"], "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if current_room and current_room["room_type"] == "Standard":
        upsell_offers.append({
            "id": str(uuid.uuid4()),
            "type": "room_upgrade",
            "title": "Deluxe Oda Upgrade",
            "description": "Konaklama deneyiminizi Deluxe odamiza yukseltin! Daha genis alan, daha iyi manzara.",
            "original_price": 100.0,
            "discounted_price": 75.0,
            "savings": 25.0,
        })

    if request.estimated_arrival_time:
        try:
            arrival_hour = int(request.estimated_arrival_time.split(":")[0])
            if arrival_hour < 14:
                upsell_offers.append({
                    "id": str(uuid.uuid4()),
                    "type": "early_checkin",
                    "title": "Erken Check-in Garantisi",
                    "description": f"Odaniz {request.estimated_arrival_time} saatinde hazir olacak.",
                    "original_price": 50.0,
                    "discounted_price": 35.0,
                    "savings": 15.0,
                })
        except Exception:
            pass

    for offer in upsell_offers:
        offer_doc = {
            **offer,
            "booking_id": request.booking_id,
            "tenant_id": current_user.tenant_id,
            "guest_id": booking["guest_id"],
            "status": "pending",
            "offered_at": datetime.now(UTC).isoformat(),
        }
        await db.upsell_offers.insert_one(offer_doc)

    return {
        "checkin_id": checkin_record["id"],
        "booking_id": request.booking_id,
        "status": "approved",
        "room_number": current_room.get("room_number") if current_room else None,
        "estimated_ready_time": "14:00",
        "upsell_offers": upsell_offers,
        "check_in_instructions": "Lutfen resepsiyona geldiginizde kimliginizi ibraz edin.",
        "message": "Online check-in basariyla tamamlandi!",
    }


# Route order matters: the static `/checkin/online/id-photos` GET must be
# declared BEFORE the dynamic `/checkin/online/{booking_id}` GET below.
# FastAPI matches in declaration order, so if the dynamic route ran first
# a list-call would silently dispatch into `get_online_checkin_status` with
# booking_id="id-photos" and return the guest status payload instead of the
# staff list.
@router.get("/checkin/online/id-photos")
async def list_online_checkin_id_photos(
    booking_id: str | None = Query(default=None),
    guest_id: str | None = Query(default=None),
    claimed: bool | None = Query(
        default=None,
        description=(
            "true → yalnızca check-in formuna bağlanmış kayıtlar; "
            "false → yetim (henüz claim edilmemiş) yüklemeler; "
            "atlandığında her ikisi de döner."
        ),
    ),
    uploaded_after: str | None = Query(
        default=None,
        description="ISO timestamp; uploaded_at >= filtresi.",
    ),
    uploaded_before: str | None = Query(
        default=None,
        description="ISO timestamp; uploaded_at <= filtresi.",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),
):
    """Task #86 — Bekleyen kimlik fotoğrafları listesi (resepsiyon paneli).

    Otomatik temizlik (Task #72) 90 gün sonra ve yetim yüklemeleri 24
    saatte siliyor; ancak personelin **bekleyen kayıtları görmesi**,
    yanlış yüklenen ya da KVKK silme talebi gelen bir fotoğrafı
    süresinden önce manuel silmesi için bir UI yok. Bu uç söz konusu
    listeyi tenant kapsamında, sayfalı ve filtreli döner. Fotoğraf
    bayt'ları KVKK gereği yanıtın bir parçası değildir; her satır
    yalnızca metadata içerir.
    """
    query: dict = {"tenant_id": current_user.tenant_id}
    if booking_id:
        query["booking_id"] = booking_id
    if guest_id:
        query["guest_id"] = guest_id
    if claimed is not None:
        query["claimed"] = bool(claimed)
    if uploaded_after or uploaded_before:
        ts: dict = {}
        if uploaded_after:
            ts["$gte"] = uploaded_after
        if uploaded_before:
            ts["$lte"] = uploaded_before
        query["uploaded_at"] = ts

    retention_days = await _id_photo_retention_days(current_user.tenant_id)
    cursor = (
        db.online_checkin_id_photos
        .find(query, {"_id": 0})
        .sort("uploaded_at", -1)
        .skip(int(offset))
        .limit(int(limit))
    )
    docs = await cursor.to_list(int(limit))
    total = await db.online_checkin_id_photos.count_documents(query)

    return {
        "items": [_public_id_photo_row(d, retention_days) for d in docs],
        "total": total,
        "retention_days": retention_days,
        "filters": {
            "booking_id": booking_id,
            "guest_id": guest_id,
            "claimed": claimed,
            "uploaded_after": uploaded_after,
            "uploaded_before": uploaded_before,
        },
        "pagination": {"limit": limit, "offset": offset},
    }


@router.get("/checkin/online/{booking_id}")
async def get_online_checkin_status(
    booking_id: str, current_user: User = Depends(get_current_user)
):
    """Online check-in durumunu getir"""
    await _assert_booking_accessible(booking_id, current_user)
    checkin = await db.online_checkins.find_one(
        {"booking_id": booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not checkin:
        return {"completed": False, "checkin": None}
    # Defensive: even though new records do not persist inline photo bytes any
    # more, an upgraded tenant may still have legacy `id_photo_base64` rows.
    # Strip the raw payload from every status response so the bytes never
    # round-trip through the JSON layer again.
    if isinstance(checkin, dict):
        checkin.pop("id_photo_base64", None)
    return {"completed": True, "checkin": checkin}


@router.get(
    "/checkin/online/{checkin_id}/id-photo",
    responses={200: {"content": {"image/*": {}}}},
)
async def download_online_checkin_id_photo(
    checkin_id: str,
    reason: str = Query(
        default="",
        description=(
            "Görüntüleme gerekçesi (KVKK amaç sınırlandırması). "
            "Önceden tanımlı seçenek veya serbest metin olabilir; boş gönderilemez."
        ),
        max_length=500,
    ),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # staff-only access
):
    """Download a guest's encrypted ID photo as image bytes (staff only).

    Decrypts the AES-GCM envelope on the fly using the AAD bound at upload
    time (tenant + booking + photo_id). Caching is disabled so the bytes never
    sit in shared/proxy caches.

    KVKK / iç denetim gereği görüntüleme öncesi kısa bir gerekçe
    (örn. "polis denetimi", "check-in doğrulaması", "şikayet incelemesi")
    zorunludur. Gerekçe boş veya yalnızca boşluk karakterlerinden oluşuyorsa
    istek 400 ile reddedilir; geçerli bir gerekçe gelirse audit kaydının
    `details` ve `after_value.reason` alanlarına yazılır.
    """
    reason_clean = (reason or "").strip()
    if not reason_clean:
        raise HTTPException(
            status_code=400,
            detail="Kimlik fotoğrafı görüntüleme için gerekçe zorunludur",
        )
    # Sınır kontrolü: FastAPI Query max_length=500 zaten zorlar ama strip
    # sonrası uzunluk değişebileceği için defansif bir kontrol daha koyalım.
    if len(reason_clean) > 500:
        raise HTTPException(
            status_code=400,
            detail="Gerekçe metni çok uzun (en fazla 500 karakter)",
        )

    checkin = await db.online_checkins.find_one(
        {"id": checkin_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not checkin:
        raise HTTPException(status_code=404, detail="Online check-in bulunamadi")

    meta = checkin.get("id_photo")
    if not isinstance(meta, dict) or not meta.get("photo_id"):
        raise HTTPException(status_code=404, detail="Bu check-in icin kimlik fotografi yok")

    image_bytes = load_id_photo(
        tenant_id=current_user.tenant_id,
        booking_id=checkin["booking_id"],
        photo_id=meta["photo_id"],
    )

    # Görüntüleme denetim kaydı: kim, ne zaman, hangi check-in/booking için
    # ve hangi gerekçeyle kimlik fotoğrafını açtığını izleyebilmek için her
    # başarılı çözümü audit timeline'a yaz. Fotoğraf baytları KVKK gereği
    # kayıt altına alınmaz; yalnızca metadata referansı (photo_id + sha256)
    # ve resepsiyonistin girdiği gerekçe tutulur.
    try:
        await log_audit_event(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action="view_online_checkin_id_photo",
            entity_type="online_checkin",
            entity_id=checkin_id,
            details=(
                f"Resepsiyon kimlik fotoğrafı görüntüleme: kullanıcı={current_user.id} "
                f"booking_id={checkin['booking_id']} photo_id={meta.get('photo_id')} "
                f"gerekçe={reason_clean}"
            ),
            after_value={
                "booking_id": checkin["booking_id"],
                "photo_id": meta.get("photo_id"),
                "sha256": meta.get("sha256"),
                "content_type": meta.get("content_type"),
                "reason": reason_clean,
            },
            db=db,
        )
    except Exception as audit_exc:  # noqa: BLE001 - audit must not break view
        # Denetim kaydı başarısız olursa fotoğraf görüntülemeyi engelleme;
        # ana akış (resepsiyon iş akışı) bozulmamalı. Yine de gözlemlenebilirlik
        # için yapısal log düşelim ki audit pipeline arızası farkedilebilsin.
        logger.warning(
            "audit_log_failed for view_online_checkin_id_photo "
            "tenant=%s user=%s checkin=%s error=%s",
            current_user.tenant_id,
            current_user.id,
            checkin_id,
            audit_exc,
        )

    return Response(
        content=image_bytes,
        media_type=meta.get("content_type") or "application/octet-stream",
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "Content-Disposition": (
                f'inline; filename="id_photo_{checkin_id}{meta.get("extension") or ""}"'
            ),
        },
    )


async def _id_photo_retention_days(tenant_id: str) -> int:
    """Saklama süresini tek noktadan oku (cleanup worker ile aynı kaynak).

    Task #124'te per-tenant'a çevrildi: önce ``tenant_settings.id_photo_retention_days``,
    sonra ``ID_PHOTO_RETENTION_DAYS`` env, son olarak 90. Cleanup
    worker'ı ile birebir aynı çözümleyiciyi çağırır ki worker'ın
    silme cutoff'u ile UI'daki "sona erme" tarihi tutarsız olmasın.
    """
    from domains.guest.checkin_id_photo_cleanup import (
        resolve_tenant_retention_days,
    )
    return await resolve_tenant_retention_days(db, tenant_id)


def _expires_at_iso(uploaded_at: str | None, retention_days: int) -> str | None:
    """`uploaded_at + retention_days` ISO çıktısı; geçersiz girişte None."""
    if not uploaded_at:
        return None
    try:
        from datetime import timedelta
        ts = uploaded_at if isinstance(uploaded_at, str) else uploaded_at.isoformat()
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (dt + timedelta(days=retention_days)).isoformat()
    except Exception:
        return None


def _public_id_photo_row(doc: dict, retention_days: int) -> dict:
    """Listeleme cevabı için güvenli proje — DB'deki dahili alanlardan
    arındır, UI'nın ihtiyacı olan alanları aç."""
    uploaded_at = doc.get("uploaded_at")
    return {
        "photo_id": doc.get("photo_id"),
        "booking_id": doc.get("booking_id"),
        "guest_id": doc.get("guest_id"),
        "checkin_id": doc.get("checkin_id"),
        "claimed": bool(doc.get("claimed")),
        "uploaded_at": uploaded_at,
        "expires_at": _expires_at_iso(uploaded_at, retention_days),
        "uploaded_by": doc.get("uploaded_by"),
        "uploaded_by_role": doc.get("uploaded_by_role"),
        "content_type": doc.get("content_type"),
        "extension": doc.get("extension"),
        "size_bytes": doc.get("size_bytes"),
        "sha256": doc.get("sha256"),
        "source": doc.get("source"),
    }


@router.delete("/checkin/online/id-photos/{photo_id}")
async def manual_delete_online_checkin_id_photo(
    photo_id: str,
    reason: str = Query(
        default="",
        description=(
            "Manuel silme gerekçesi (KVKK / iç denetim). "
            "Boş veya yalnızca boşluk olamaz; en fazla 500 karakter."
        ),
        max_length=500,
    ),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),
):
    """Task #86 — Bir kimlik fotoğrafını süresinden önce manuel sil.

    Audit kaydı bırakılır (`action="manual_delete"`, metadata.reason =
    `"manual_delete:<gerekçe>"`); şifrelenmiş dosya ve metadata kaydı
    cleanup ile aynı yolla silinir (`_delete_one`).
    """
    reason_clean = (reason or "").strip()
    if not reason_clean:
        raise HTTPException(
            status_code=400,
            detail="Manuel silme için gerekçe zorunludur",
        )

    doc = await db.online_checkin_id_photos.find_one(
        {"photo_id": photo_id, "tenant_id": current_user.tenant_id},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Kimlik fotoğrafı bulunamadı veya bu kiracıya ait değil",
        )

    from domains.guest.checkin_id_photo_cleanup import _delete_one
    deleted = await _delete_one(
        db=db,
        doc=doc,
        reason=f"manual_delete:{reason_clean}",
        actor_id=current_user.id,
    )
    if not deleted:
        # Hem dosya hem metadata silme başarısız oldu — diskte ya
        # da DB'de kalıntı olabileceğini bildir, hata yutma.
        raise HTTPException(
            status_code=500,
            detail="Kimlik fotoğrafı silinemedi (dosya veya metadata).",
        )
    return {
        "photo_id": photo_id,
        "deleted": True,
        "reason": reason_clean,
    }


@router.post("/checkin/online/id-photos/bulk-delete")
async def bulk_delete_online_checkin_id_photos(
    payload: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),
):
    """Task #86 — KVKK silme talebi için booking_id veya guest_id
    bazlı toplu manuel silme.

    İstek gövdesi::

        {
          "booking_id": "...",   # ya bu
          "guest_id":   "...",   # ya bu (en az biri)
          "reason":     "KVKK silme talebi #2026-..."
        }

    Her silinen kayıt için ayrı bir audit kaydı düşer; toplu silmenin
    sayısı yanıtta döner. Hiç eşleşme olmazsa 0 döner — 404 değil
    (operasyon idempotent).
    """
    booking_id = (payload.get("booking_id") or "").strip() or None
    guest_id = (payload.get("guest_id") or "").strip() or None
    reason_clean = (payload.get("reason") or "").strip()

    if not (booking_id or guest_id):
        raise HTTPException(
            status_code=400,
            detail="booking_id veya guest_id alanlarından en az biri zorunludur",
        )
    if not reason_clean:
        raise HTTPException(
            status_code=400,
            detail="Toplu silme için gerekçe zorunludur (KVKK izlenebilirlik)",
        )
    if len(reason_clean) > 500:
        raise HTTPException(
            status_code=400,
            detail="Gerekçe metni çok uzun (en fazla 500 karakter)",
        )

    query: dict = {"tenant_id": current_user.tenant_id}
    if booking_id:
        query["booking_id"] = booking_id
    if guest_id:
        query["guest_id"] = guest_id

    # KVKK kapsamında **kısmi silme kabul edilemez** — bir misafirin
    # silme talebi gelmişse koleksiyondaki TÜM eşleşen kayıtlar
    # silinmeli. Bu yüzden cursor'u sonuna kadar async iterate ederiz;
    # ne `to_list(N)` cap'i ne de sayfalama eşiği vardır. Tek bir doküman
    # ~150-200 byte (file path + metadata) olduğundan binlerce doküman
    # bile bellek baskısı yaratmaz; yine de cursor üzerinden işlediğimiz
    # için tek seferde tüm dokümanlar belleğe yüklenmez.
    from domains.guest.checkin_id_photo_cleanup import _delete_one
    cursor = db.online_checkin_id_photos.find(query, {"_id": 0})
    matched = 0
    deleted_count = 0
    failed_ids: list[str] = []
    async for doc in cursor:
        matched += 1
        try:
            ok = await _delete_one(
                db=db,
                doc=doc,
                reason=f"manual_delete:{reason_clean}",
                actor_id=current_user.id,
            )
            if ok:
                deleted_count += 1
            else:
                failed_ids.append(str(doc.get("photo_id") or ""))
        except Exception:
            logger.exception(
                "bulk_delete_online_checkin_id_photos: delete failed for photo_id=%s",
                doc.get("photo_id"),
            )
            failed_ids.append(str(doc.get("photo_id") or ""))

    return {
        "matched": matched,
        "deleted": deleted_count,
        "failed_photo_ids": failed_ids,
        "booking_id": booking_id,
        "guest_id": guest_id,
        "reason": reason_clean,
    }


async def _build_retention_setting_response(tenant_id: str) -> dict:
    """GET ve PUT için ortak yanıt şekli; per-tenant ayar + meta verisi.

    `tenant_override` alanı, DB'deki ham değer int parse edilemiyorsa
    (geçmiş migration kalıntısı, tipik olarak string) None olarak
    döner — `resolve_tenant_retention_days` zaten env varsayılanına
    düştüğü için efektif değer doğru olur, ama UI'da "rozet" ve form
    için sayısal bir override görmek anlamlı; parse edilemiyorsa
    'tenant override yok gibi davran' diyoruz ki 500 yerine UI temiz
    bir env_default deneyimi gösterebilsin.
    """
    from domains.guest.checkin_id_photo_cleanup import (
        MAX_RETENTION_DAYS,
        MIN_RETENTION_DAYS,
        env_default_retention_days,
        resolve_tenant_retention_days,
    )

    settings = await db.tenant_settings.find_one(
        {"tenant_id": tenant_id},
        {"_id": 0, "id_photo_retention_days": 1},
    )
    raw_tenant_value = (settings or {}).get("id_photo_retention_days")
    effective = await resolve_tenant_retention_days(db, tenant_id)

    tenant_override: int | None = None
    if raw_tenant_value is not None and not isinstance(raw_tenant_value, bool):
        try:
            tenant_override = int(raw_tenant_value)
        except (TypeError, ValueError):
            tenant_override = None

    return {
        "retention_days": effective,
        "source": "tenant" if tenant_override is not None else "env_default",
        "env_default": env_default_retention_days(),
        "tenant_override": tenant_override,
        "min_days": MIN_RETENTION_DAYS,
        "max_days": MAX_RETENTION_DAYS,
    }


@router.get("/checkin/online/settings/id-photo-retention")
async def get_id_photo_retention_setting(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),
):
    """Task #124 — Tenant'ın efektif kimlik fotoğrafı saklama süresi.

    Yanıt UI'a hem efektif değeri hem de "değer nereden geliyor" bilgisini
    verir; admin formu "global default kullanılıyor" / "tenant özelleşti"
    rozetini doğru çizebilsin diye gerekli.
    """
    return await _build_retention_setting_response(current_user.tenant_id)


@router.put("/checkin/online/settings/id-photo-retention")
async def update_id_photo_retention_setting(
    payload: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),
):
    """Task #124 — Tenant'a özel saklama süresini set et / sıfırla.

    Body:
      ``{"retention_days": <int>}`` — değeri MIN_RETENTION_DAYS..MAX_RETENTION_DAYS
        aralığına düşürür ve ``tenant_settings.id_photo_retention_days`` olarak yazar.
      ``{"retention_days": null}`` — alanı kaldırır; bir sonraki okumada env
        varsayılanı geri döner.

    Sınır dışı sayı ya da int olmayan değer 400 döner; bu sayede UI'daki
    spinner/clamp davranışı backend tarafından da garanti edilir.
    """
    from domains.guest.checkin_id_photo_cleanup import (
        MAX_RETENTION_DAYS,
        MIN_RETENTION_DAYS,
        clamp_retention_days,
    )

    if "retention_days" not in payload:
        raise HTTPException(
            status_code=400,
            detail="`retention_days` alanı zorunlu (sıfırlamak için null gönder).",
        )
    raw = payload.get("retention_days")

    if raw is None:
        # Sıfırla: alanı sil, env default'a dön.
        await db.tenant_settings.update_one(
            {"tenant_id": current_user.tenant_id},
            {
                "$setOnInsert": {"tenant_id": current_user.tenant_id},
                "$unset": {"id_photo_retention_days": ""},
            },
            upsert=True,
        )
    else:
        # Strict int parse: bool Python'da int alt-türüdür, kullanıcı
        # `true` gönderirse 1 gün ayarı yazılırdı — bunu kazara değiştirme
        # riski olarak görüp 400 dönüyoruz.
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise HTTPException(
                status_code=400,
                detail="`retention_days` tam sayı (gün) olmalı.",
            )
        value = raw
        if value < MIN_RETENTION_DAYS or value > MAX_RETENTION_DAYS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"`retention_days` {MIN_RETENTION_DAYS}–{MAX_RETENTION_DAYS} "
                    "gün aralığında olmalı."
                ),
            )
        clamped = clamp_retention_days(value)
        await db.tenant_settings.update_one(
            {"tenant_id": current_user.tenant_id},
            {
                "$setOnInsert": {"tenant_id": current_user.tenant_id},
                "$set": {
                    "id_photo_retention_days": clamped,
                    "id_photo_retention_updated_at": datetime.now(UTC).isoformat(),
                    "id_photo_retention_updated_by": current_user.id,
                },
            },
            upsert=True,
        )
        # Audit izi: kim, ne zaman, neye çekti? KVKK kapsamında saklama
        # süresi değişikliği iz bırakmalı — denetimde "Mart'ta 90 gündü
        # ama Mayıs'ta 30 yapıldı" sorgusu yanıtlanabilsin.
        try:
            await log_audit_event(
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                action="update_id_photo_retention",
                entity_type="tenant_settings",
                entity_id=current_user.tenant_id,
                details=(
                    f"id_photo_retention_days set to {clamped} (input={value})"
                ),
                after_value={"id_photo_retention_days": clamped},
                db=db,
            )
        except Exception:  # pragma: no cover - audit must not break write
            logger.warning(
                "audit_log_failed for update_id_photo_retention tenant=%s",
                current_user.tenant_id,
            )

    return await _build_retention_setting_response(current_user.tenant_id)


@router.post("/upsell/accept")
async def accept_upsell_offer(
    data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Upsell teklifini kabul et"""
    offer_id = data.get("offer_id")
    action = data.get("action")

    offer = await db.upsell_offers.find_one(
        {"id": offer_id, "tenant_id": current_user.tenant_id}
    )
    if not offer:
        raise HTTPException(status_code=404, detail="Teklif bulunamadi")

    await db.upsell_offers.update_one(
        {"id": offer_id},
        {"$set": {"status": "accepted" if action == "accept" else "rejected", "responded_at": datetime.now(UTC).isoformat()}},
    )

    if action == "accept":
        booking_id = offer.get("booking_id")
        charge = {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "booking_id": booking_id,
            "charge_category": "upsell",
            "description": offer.get("title"),
            "amount": offer.get("discounted_price") or offer.get("original_price"),
            "posted_at": datetime.now(UTC).isoformat(),
            "voided": False,
        }

        folio = await db.folios.find_one(
            {"booking_id": booking_id, "folio_type": "guest"}, {"_id": 0}
        )
        if folio:
            charge["folio_id"] = folio["id"]
            await db.folio_charges.insert_one(charge)

        return {
            "success": True,
            "message": f'{offer.get("title")} basariyla eklendi!',
            "charge_added": True,
            "amount": charge["amount"],
        }
    else:
        return {"success": True, "message": "Teklif reddedildi", "charge_added": False}


@router.get("/pre-arrival/communications/{booking_id}")
async def get_pre_arrival_communications(
    booking_id: str, current_user: User = Depends(get_current_user)
):
    """Pre-arrival iletisim gecmisi"""
    communications = await db.pre_arrival_communications.find(
        {"booking_id": booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    ).to_list(100)

    return {"booking_id": booking_id, "communications": communications, "total": len(communications)}
