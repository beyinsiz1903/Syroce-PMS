"""
Unmatched OTA Reservation Hold — shared helper (Exely + HotelRunner).
=====================================================================

Bir OTA rezervasyonu (Exely/HotelRunner) oda/fiyat eslestirmesi
yapilamadigi icin "pending_mapping" / "unmapped_room_type" kararina
dustugunde, sessizce park edilip envanter kilitlenmeden birakilmasi
overbooking riski yaratir. Bu modul her iki saglayici icin de ORTAK
calisir ve su garantiyi verir:

  1. Eslestirilemeyen rezervasyon icin bir "tutma" (hold) PMS booking
     kaydi olusturulur (status="pending_mapping", action_needed=True).
     Rezervasyon HARD-FAIL olarak isaretli kalir; otomatik kabul YOK.
  2. Envanter korumasi icin sentinel oda-gece kilitleri (room_night_locks)
     yazilir. Kilitler `rooms` koleksiyonundaki gercek bir odayi degil,
     `ota-unmatched::{provider}::{external_id}` sentinel oda kimligini
     hedefler -> envanter motoru bu kilitleri guvenle yok sayar (gercek
     oda tipi bilinmedigi icin spesifik bir tip bloke edilemez; bu kilitler
     durumun durust Layer-1 artefaktidir, asil operasyonel koruma ALARM'dir).
  3. Idempotent ACIL alarm: kalici in-app bildirim (tenant'a izole,
     dedup_key ile tekrarsiz) + tenant-scoped websocket + Control Plane
     uyari motoru. Baslik tam olarak:
       "ACIL: ESLESMEYEN REZERVASYON - AKSIYON BEKLIYOR"
     (Turkce buyuk-I karakteri ile.)

Eslestirme duzeltildiginde `release_unmatched_reservation_hold(..., delete_hold=True)`
tutma kaydini ve sentinel kilitlerini siler (cift sayim olmaz), ardindan
cagiran modul gercek booking'i olusturur. Iptal geldiginde ise
`release_unmatched_reservation_hold(..., delete_hold=False)` kilitleri serbest
birakir ve tutmayi cancelled olarak isaretler.

ONEMLI sinirlama (durust): Control Plane uyari motorunun cooldown'u trigger
bazindadir (per-reservation degil), bu yuzden cp-alert kanali kisa pencerede
farkli rezervasyonlar icin az-uyarabilir. Per-rezervasyon idempotency ve asil
gorunurluk, tenant'a izole in-app bildirim (dedup_key) tarafindan saglanir.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

from core.atomic_booking import _night_dates, release_booking_nights
from core.database import db
from core.tenant_db import tenant_context

logger = logging.getLogger("channel_manager.unmatched_hold")

# Tutma booking'lerini ve sentinel kilitlerini tanimlayan sabitler.
UNMATCHED_HOLD_SOURCE = "ota_unmatched_hold"
UNMATCHED_HOLD_LOCK_TYPE = "ota_unmatched_hold"
UNMATCHED_HOLD_STATUS = "pending_mapping"

ALARM_TITLE = "ACİL: EŞLEŞMEYEN REZERVASYON - AKSİYON BEKLİYOR"
ALARM_TRIGGER = "unmatched_reservation"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sentinel_room_id(provider: str, external_id: str) -> str:
    """Idempotent, per-external sentinel oda kimligi.

    `rooms` koleksiyonunda BULUNMAZ -> envanter motoru, takvim, kat
    hizmetleri ve walk-in akislari bu kilitleri guvenle yok sayar.
    """
    return f"ota-unmatched::{provider}::{external_id}"


def _norm_dt(value: str) -> str:
    """YYYY-MM-DD veya ISO datetime -> _night_dates icin ISO datetime."""
    if not value:
        return ""
    base = str(value)[:10]
    return f"{base}T00:00:00+00:00"


async def create_unmatched_reservation_hold(
    *,
    provider: str,
    tenant_id: str,
    external_id: str,
    check_in: str,
    check_out: str,
    guest_name: str = "",
    room_type_code: str = "",
    rate_plan_code: str = "",
    total_amount: float = 0.0,
    currency: str = "TRY",
    adults: int = 1,
    children: int = 0,
    channel: str = "",
    property_id: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Eslestirilemeyen rezervasyon icin idempotent tutma + alarm olusturur.

    Returns: {"created": bool, "booking_id": str|None, "nights_held": list,
              "idempotent": bool}
    """
    if not tenant_id or not external_id:
        logger.warning(
            "[UNMATCHED-HOLD] tenant_id/external_id eksik; atlandi provider=%s ext=%s",
            provider,
            external_id,
        )
        return {"created": False, "booking_id": None, "nights_held": [], "idempotent": False}

    property_id = property_id or tenant_id

    # ── Idempotency: aktif bir tutma zaten var mi? ──────────────────
    with tenant_context(tenant_id):
                existing = await db.bookings.find_one(
                {
                "tenant_id": tenant_id,
                "external_reservation_id": external_id,
                "booking_source": UNMATCHED_HOLD_SOURCE,
                "status": {"$ne": "cancelled"},
                },
                {"_id": 0, "id": 1},
                )
    if existing:
        # Tekrar teslimatlarda yeni alarm uretmiyoruz (idempotent).
        return {
            "created": False,
            "booking_id": existing["id"],
            "nights_held": [],
            "idempotent": True,
        }

    booking_id = str(uuid.uuid4())
    now = _now()
    hold_doc = {
        "id": booking_id,
        "tenant_id": tenant_id,
        "property_id": property_id,
        "guest_name": guest_name or "Eslesmeyen Misafir",
        "check_in": check_in,
        "check_out": check_out,
        # Gercek oda tipi BILINMIYOR -> mislabel etmiyoruz.
        "room_type": None,
        "room_type_id": None,
        "room_id": None,
        "room_number": None,
        "provider_room_code": room_type_code,
        "provider_rate_code": rate_plan_code,
        "rate_plan_code": rate_plan_code,
        "adults": adults,
        "children": children,
        "total_amount": total_amount,
        "currency": currency,
        "status": UNMATCHED_HOLD_STATUS,
        "booking_source": UNMATCHED_HOLD_SOURCE,
        "channel": channel or provider,
        "external_reservation_id": external_id,
        # NOT: source.external_reservation_id BILEREK yok -> import bridge'in
        # check_booking_source_exists duplicate kisa-devresi tutmayi gercek
        # booking sanip rebind'i atlamasin.
        "source": {
            "provider": provider,
            "kind": UNMATCHED_HOLD_SOURCE,
            "hold": True,
        },
        "action_needed": True,
        "requires_mapping": True,
        "is_inventory_hold": True,
        "hold_status": "ota_unmatched",
        "allocation_source": "ota_unmatched_hold",
        "note": note,
        "created_at": now,
        "updated_at": now,
    }

    try:
        with tenant_context(tenant_id):
                    await db.bookings.insert_one(hold_doc)
    except Exception as exc:
        logger.exception(
            "[UNMATCHED-HOLD] tutma booking insert basarisiz provider=%s ext=%s: %s",
            provider,
            external_id,
            exc,
        )
        return {"created": False, "booking_id": None, "nights_held": [], "idempotent": False}

    # ── Sentinel oda-gece kilitleri (envanter koruma artefakti) ─────
    sentinel_room = _sentinel_room_id(provider, external_id)
    nights = []
    try:
        nights = _night_dates(_norm_dt(check_in), _norm_dt(check_out))
    except Exception as exc:
        logger.warning(
            "[UNMATCHED-HOLD] gece hesaplama basarisiz ext=%s (%s -> %s): %s",
            external_id,
            check_in,
            check_out,
            exc,
        )

    held = []
    for night in nights:
        lock_doc = {
            "tenant_id": tenant_id,
            "room_id": sentinel_room,
            "night_date": night,
            "booking_id": booking_id,
            "lock_type": UNMATCHED_HOLD_LOCK_TYPE,
            "reason": f"OTA unmatched hold ({provider}:{external_id})",
            "created_by": "system:unmatched_hold",
            "created_at": now,
        }
        try:
            with tenant_context(tenant_id):
                        await db.room_night_locks.insert_one(lock_doc)
            held.append(night)
        except DuplicateKeyError:
            # Idempotent: ayni sentinel oda+gece zaten kilitli.
            held.append(night)
        except Exception as exc:
            logger.warning(
                "[UNMATCHED-HOLD] sentinel kilit basarisiz ext=%s night=%s: %s",
                external_id,
                night,
                exc,
            )

    logger.info(
        "[UNMATCHED-HOLD] tutma olusturuldu provider=%s ext=%s booking=%s nights=%d",
        provider,
        external_id,
        booking_id,
        len(held),
    )

    # ── ACIL alarm (idempotent) ─────────────────────────────────────
    await _raise_unmatched_alarm(
        provider=provider,
        tenant_id=tenant_id,
        external_id=external_id,
        guest_name=guest_name,
        check_in=check_in,
        check_out=check_out,
        room_type_code=room_type_code,
        booking_id=booking_id,
    )

    return {
        "created": True,
        "booking_id": booking_id,
        "nights_held": held,
        "idempotent": False,
    }


async def release_unmatched_reservation_hold(
    *,
    tenant_id: str,
    external_id: str,
    reason: str = "released",
    delete_hold: bool = False,
) -> dict[str, Any]:
    """Tutmayi serbest birakir (idempotent).

    delete_hold=True  -> rebind: tutma kaydi + sentinel kilitleri SILINIR
                         (cagiran modul ardindan gercek booking'i olusturur,
                         boylece cift sayim olmaz).
    delete_hold=False -> iptal: kilitler serbest, tutma cancelled isaretlenir.
    """
    if not tenant_id or not external_id:
        return {"released": False, "booking_id": None, "nights_released": 0}

    with tenant_context(tenant_id):
                hold = await db.bookings.find_one(
                {
                "tenant_id": tenant_id,
                "external_reservation_id": external_id,
                "booking_source": UNMATCHED_HOLD_SOURCE,
                "status": {"$ne": "cancelled"},
                },
                {"_id": 0, "id": 1},
                )
    if not hold:
        return {"released": False, "booking_id": None, "nights_released": 0}

    booking_id = hold["id"]
    release_ok = True
    try:
        released = await release_booking_nights(tenant_id, booking_id, reason=reason)
    except Exception as exc:
        logger.exception(
            "[UNMATCHED-HOLD] kilit serbest birakma basarisiz ext=%s booking=%s: %s",
            external_id,
            booking_id,
            exc,
        )
        released = 0
        release_ok = False

    now = _now()
    deleted = False
    if delete_hold and not release_ok:
        # Task #437: kilit serbest bırakılamadıysa hold booking'i SİLME — kilit
        # sahipsiz (orphan) kalmasın, boş oda yanlışlıkla 'dolu' görünmesin.
        # Sahibi kalan hold daha sonra script/tekrar deneme ile temizlenebilir.
        with tenant_context(tenant_id):
                    await db.bookings.update_one(
                    {"id": booking_id, "tenant_id": tenant_id},
                    {"$set": {"action_needed": True, "updated_at": now}},
                    )
    elif delete_hold:
        with tenant_context(tenant_id):
                    await db.bookings.delete_one({"id": booking_id, "tenant_id": tenant_id})
        deleted = True
    else:
        with tenant_context(tenant_id):
                    await db.bookings.update_one(
                    {"id": booking_id, "tenant_id": tenant_id},
                    {
                    "$set": {
                    "status": "cancelled",
                    "cancelled_at": now,
                    "cancelled_reason": reason,
                    "action_needed": False,
                    "is_inventory_hold": False,
                    "updated_at": now,
                    }
                    },
                    )

    logger.info(
        "[UNMATCHED-HOLD] tutma serbest ext=%s booking=%s nights=%d delete=%s reason=%s",
        external_id,
        booking_id,
        released,
        delete_hold,
        reason,
    )
    return {
        "released": release_ok,
        "booking_id": booking_id,
        "nights_released": released,
        "deleted": deleted,
    }


async def _raise_unmatched_alarm(
    *,
    provider: str,
    tenant_id: str,
    external_id: str,
    guest_name: str,
    check_in: str,
    check_out: str,
    room_type_code: str,
    booking_id: str,
) -> None:
    """Idempotent ACIL alarm: in-app bildirim + websocket + Control Plane."""
    now = _now()
    ci = (check_in or "")[:10]
    co = (check_out or "")[:10]
    dedup_key = f"unmatched_mapping_{external_id}"

    # ── 1. Kalici in-app bildirim (tenant'a izole, idempotent) ──────
    # Misafir adi (PII) yalnizca tenant'a izole bildirimde yer alir.
    notif_message = (
        f"{provider.upper()} kanalindan gelen {external_id} numarali rezervasyon "
        f"({guest_name or 'Misafir'}, {ci} -> {co}) oda/fiyat eslestirmesi "
        f"yapilamadigi icin PMS'e aktarilamadi. Envanter korumasi icin gecici "
        f"tutma olusturuldu. Lutfen oda tipi eslestirmesini tamamlayin."
    )
    try:
        with tenant_context(tenant_id):
                    existing_notif = await db.notifications.find_one(
                    {
                    "tenant_id": tenant_id,
                    "dedup_key": dedup_key,
                    }
                    )
        if not existing_notif:
            with tenant_context(tenant_id):
                        await db.notifications.insert_one(
                        {
                        "id": str(uuid.uuid4()),
                        "tenant_id": tenant_id,
                        "user_id": None,
                        "type": "channel_unmatched_reservation",
                        "priority": "high",
                        "category": "channel_manager",
                        "title": ALARM_TITLE,
                        "message": notif_message,
                        "action_url": "/channel-manager",
                        "booking_id": booking_id,
                        "external_reservation_id": external_id,
                        "provider": provider,
                        "read": False,
                        "dedup_key": dedup_key,
                        "created_at": now,
                        }
                        )
            # ── 2. Tenant-scoped websocket bildirimi ────────────────
            # broadcast_notification KULLANILMAZ (global 'notifications'
            # odasina yayar -> cross-tenant PII sizintisi). Tenant-scoped
            # broadcast_booking_update tercih edilir.
            try:
                from websocket_server import broadcast_booking_update

                await broadcast_booking_update(
                    {
                        "id": booking_id,
                        "status": UNMATCHED_HOLD_STATUS,
                        "external_reservation_id": external_id,
                        "provider": provider,
                        "action_needed": True,
                        "alarm_title": ALARM_TITLE,
                    },
                    event_type="unmatched_hold",
                    tenant_id=tenant_id,
                )
            except Exception as exc:
                logger.warning(
                    "[UNMATCHED-HOLD] websocket yayini basarisiz ext=%s: %s",
                    external_id,
                    exc,
                )
    except Exception as exc:
        logger.exception(
            "[UNMATCHED-HOLD] in-app bildirim basarisiz ext=%s: %s",
            external_id,
            exc,
        )

    # ── 3. Control Plane uyari motoru (best-effort, PII'siz) ────────
    # Misafir adi cp-alert baglamina/mesajina KONULMAZ (Slack/e-posta
    # egress'inden gecebilir). Yalnizca operasyonel tanimlayicilar.
    cp_message = (
        f"{provider.upper()} kanalindan {external_id} numarali rezervasyon "
        f"({ci} -> {co}) oda/fiyat eslestirmesi yapilamadigi icin aktarilamadi. "
        f"Gecici envanter tutmasi olusturuldu; oda tipi eslestirmesi gerekli."
    )
    try:
        from controlplane.alerting import AlertSeverity, get_alerting_engine

        await get_alerting_engine().fire(
            trigger=ALARM_TRIGGER,
            severity=AlertSeverity.CRITICAL,
            title=ALARM_TITLE,
            message=cp_message,
            context={
                "provider": provider,
                "external_reservation_id": external_id,
                "check_in": ci,
                "check_out": co,
                "provider_room_code": room_type_code,
                "booking_id": booking_id,
            },
            tenant_id=tenant_id,
        )
    except Exception as exc:
        logger.warning(
            "[UNMATCHED-HOLD] control plane uyarisi basarisiz ext=%s: %s",
            external_id,
            exc,
        )
