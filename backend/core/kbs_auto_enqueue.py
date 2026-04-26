"""KBS auto-enqueue: check-in / check-out sonrası otomatik bildirim kuyruğu.

Atomik check-in/out tamamlandığında çağrılır. Hata olursa log'lar ama
exception fırlatmaz — KBS bildirimi opsiyonel bir sonraki adımdır, ana
PMS akışını bloklamamalıdır.

Aynı (booking_id, action) için pending/in_progress iş varsa yeni iş
açmaz (idempotent).
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime

from core.database import db
from core.kbs_payload_validation import validate_kbs_payload

logger = logging.getLogger("core.kbs_auto_enqueue")

QUEUE_KIND = "queue_job"
DEFAULT_MAX_ATTEMPTS = 5


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _build_payload_snapshot(tenant_id: str, booking_id: str) -> dict:
    booking = await db.bookings.find_one(
        {"tenant_id": tenant_id, "id": booking_id},
        {
            "_id": 0, "id": 1, "guest_id": 1, "guest_name": 1,
            "guest_email": 1, "guest_phone": 1, "room_number": 1,
            "check_in": 1, "check_out": 1, "guest_nationality": 1,
        },
    )
    if not booking:
        return {}

    guest: dict = {}
    if booking.get("guest_id"):
        guest = await db.guests.find_one(
            {"tenant_id": tenant_id, "id": booking["guest_id"]},
            {
                "_id": 0, "nationality": 1, "id_number": 1,
                "passport_number": 1, "birth_date": 1, "gender": 1,
                "address": 1, "father_name": 1, "mother_name": 1,
                "birth_place": 1,
            },
        ) or {}

    return {
        "guest_name": booking.get("guest_name", ""),
        "room_number": booking.get("room_number", ""),
        "check_in": booking.get("check_in", ""),
        "check_out": booking.get("check_out", ""),
        "nationality": guest.get("nationality")
            or booking.get("guest_nationality") or "TC",
        "id_number": guest.get("id_number", ""),
        "passport_number": guest.get("passport_number", ""),
        "birth_date": guest.get("birth_date", ""),
        "gender": guest.get("gender", ""),
        "father_name": guest.get("father_name", ""),
        "mother_name": guest.get("mother_name", ""),
        "birth_place": guest.get("birth_place", ""),
        "address": guest.get("address", ""),
    }


async def auto_enqueue_kbs(
    tenant_id: str,
    booking_id: str,
    action: str = "checkin",
    *,
    actor: str = "system:auto_enqueue",
) -> dict | None:
    """Otomatik enqueue. Hata olursa None döner ve log yazar.

    Eksik veriyle iş kuyruğa girer mi? HAYIR — payload eksikse bunun
    yerine `kbs_alerts` koleksiyonuna `missing_data` alarmı yazılır
    (operatöre uyarı). Sertifika alındıktan sonra bile bu alarmlar
    operatörü hızla yönlendirir.

    KBS_AUTO_ENQUEUE=0 env değişkeniyle kapatılabilir.
    """
    if os.environ.get("KBS_AUTO_ENQUEUE", "1") == "0":
        return None

    try:
        existing = await db.kbs_reports.find_one(
            {
                "_kind": QUEUE_KIND,
                "tenant_id": tenant_id,
                "booking_id": booking_id,
                "action": action,
                "status": {"$in": ["pending", "in_progress"]},
            },
            {"_id": 0, "id": 1},
        )
        if existing:
            logger.info(
                "KBS auto-enqueue skipped (already queued): booking=%s action=%s",
                booking_id, action,
            )
            return existing

        snapshot = await _build_payload_snapshot(tenant_id, booking_id)
        if not snapshot:
            logger.warning(
                "KBS auto-enqueue skipped (booking not found): booking=%s",
                booking_id,
            )
            return None

        ok, missing = validate_kbs_payload(snapshot)
        if not ok:
            await db.kbs_alerts.insert_one({
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "kind": "missing_data",
                "booking_id": booking_id,
                "action": action,
                "missing_fields": missing,
                "guest_name": snapshot.get("guest_name", ""),
                "room_number": snapshot.get("room_number", ""),
                "created_at": _now_iso(),
                "acknowledged": False,
            })
            logger.warning(
                "KBS auto-enqueue blocked (missing fields): booking=%s missing=%s",
                booking_id, missing,
            )
            return None

        booking = await db.bookings.find_one(
            {"tenant_id": tenant_id, "id": booking_id},
            {"_id": 0, "guest_id": 1},
        )
        now_iso = _now_iso()
        job = {
            "_kind": QUEUE_KIND,
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "guest_id": (booking or {}).get("guest_id"),
            "action": action,
            "status": "pending",
            "attempts": 0,
            "max_attempts": DEFAULT_MAX_ATTEMPTS,
            "worker_id": None,
            "leased_until": None,
            "next_retry_at": None,
            "last_error": None,
            "kbs_reference": None,
            "payload": snapshot,
            "notes": "",
            "enqueued_by": actor,
            "source": "auto",
            "created_at": now_iso,
            "updated_at": now_iso,
            "claimed_at": None,
            "completed_at": None,
            "failed_at": None,
        }
        await db.kbs_reports.insert_one(job)
        logger.info(
            "KBS auto-enqueue ok: booking=%s action=%s job=%s",
            booking_id, action, job["id"],
        )
        return job
    except Exception as e:
        logger.warning(
            "KBS auto-enqueue failed (non-blocking): booking=%s action=%s err=%s",
            booking_id, action, e,
        )
        return None
