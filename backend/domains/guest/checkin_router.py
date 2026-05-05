"""
Domain Router: Online Check-in & Pre-Arrival

Extracted from legacy_routes.py — online check-in submission,
upsell acceptance, pre-arrival communications.
"""
import base64
import binascii
import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from core.database import db
from core.security import get_current_user
from domains.guest.checkin_id_photo_storage import load_id_photo, save_id_photo
from models.schemas import User
from modules.pms_core.role_permission_service import MODULE_ROLES  # v97 DW
from modules.pms_core.role_permission_service import require_module as require_module_v97  # v97 DW
from security.upload_validator import MAX_IMAGE_BYTES

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
        guest_doc = await db.guests.find_one(
            {"email": current_user.email, "tenant_id": current_user.tenant_id},
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
    from domains.guest.online_checkin_models import OnlineCheckinRequest

    request = OnlineCheckinRequest(**checkin_data)

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


@router.get("/checkin/online/{booking_id}")
async def get_online_checkin_status(
    booking_id: str, current_user: User = Depends(get_current_user)
):
    """Online check-in durumunu getir"""
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
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # staff-only access
):
    """Download a guest's encrypted ID photo as image bytes (staff only).

    Decrypts the AES-GCM envelope on the fly using the AAD bound at upload
    time (tenant + booking + photo_id). Caching is disabled so the bytes never
    sit in shared/proxy caches.
    """
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
