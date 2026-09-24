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
from core.kbs_payload_builder import build_kbs_payload_snapshot
from core.kbs_payload_validation import validate_kbs_payload

logger = logging.getLogger("core.kbs_auto_enqueue")

QUEUE_KIND = "queue_job"
DEFAULT_MAX_ATTEMPTS = 5


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _build_payload_snapshot(tenant_id: str, booking_id: str, target_guest_id: str | None = None) -> dict:
    _booking, _guest, snapshot = await build_kbs_payload_snapshot(db, tenant_id, booking_id, target_guest_id)
    return snapshot


async def _enqueue_single_guest(
    tenant_id: str,
    booking_id: str,
    guest_id: str | None,
    action: str,
    actor: str,
) -> dict | None:
    try:
        lock_id = f"{tenant_id}:{booking_id}:{guest_id or 'primary'}:{action}"
        existing = await db.kbs_reports.find_one(
            {
                "_kind": QUEUE_KIND,
                "tenant_id": tenant_id,
                "_open_lock": lock_id,
            },
            {"_id": 0, "id": 1},
        )
        if existing:
            return existing

        snapshot = await _build_payload_snapshot(tenant_id, booking_id, guest_id)
        if not snapshot:
            return None

        booking = await db.bookings.find_one(
            {"tenant_id": tenant_id, "id": booking_id},
            {"_id": 0, "guest_id": 1, "kbs_reported": 1, "kbs_test": 1},
        )

        if action == "checkout" and not ((booking or {}).get("kbs_reported") and not (booking or {}).get("kbs_test")):
            await db.kbs_alerts.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "kind": "checkin_not_confirmed",
                    "booking_id": booking_id,
                    "action": action,
                    "guest_name": snapshot.get("guest_name", ""),
                    "room_number": snapshot.get("room_number", ""),
                    "created_at": _now_iso(),
                    "acknowledged": False,
                }
            )
            return None

        ok, missing = validate_kbs_payload(snapshot, action)
        if not ok:
            await db.kbs_alerts.insert_one(
                {
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
                }
            )
            return None

        now_iso = _now_iso()
        job = {
            "_kind": QUEUE_KIND,
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "guest_id": guest_id or (booking or {}).get("guest_id"),
            "action": action,
            "status": "pending",
            "_open_lock": lock_id,
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
        try:
            await db.kbs_reports.insert_one(job)
        except Exception as ins_err:
            if "duplicate key" in str(ins_err).lower() or "E11000" in str(ins_err):
                existing2 = await db.kbs_reports.find_one({"_kind": QUEUE_KIND, "tenant_id": tenant_id, "_open_lock": lock_id}, {"_id": 0})
                return existing2
            raise
        return job
    except Exception as e:
        logger.warning(f"KBS auto-enqueue failed for guest {guest_id}: {e}")
        return None


async def auto_enqueue_kbs(
    tenant_id: str,
    booking_id: str,
    action: str = "checkin",
    *,
    actor: str = "system:auto_enqueue",
    target_guest_id: str | None = None,
) -> list[dict] | dict | None:
    if os.environ.get("KBS_AUTO_ENQUEUE", "1") == "0":
        return None

    if target_guest_id:
        return await _enqueue_single_guest(tenant_id, booking_id, target_guest_id, action, actor)

    # If no specific guest is provided, enqueue for ALL guests in the booking
    booking = await db.bookings.find_one({"tenant_id": tenant_id, "id": booking_id}, {"_id": 0, "guest_id": 1})
    if not booking:
        return None

    guests_to_enqueue = [booking.get("guest_id")]

    # Also fetch all booking_guests that do NOT have a checkout_date yet (if checkin)
    # or fetch all if checkout.
    bg_links = await db.booking_guests.find({"tenant_id": tenant_id, "booking_id": booking_id}, {"_id": 0}).to_list(100)
    for bg in bg_links:
        if bg.get("guest_id") and bg.get("guest_id") not in guests_to_enqueue:
            # For checkout, only enqueue if they haven't already checked out early
            if action == "checkout" and bg.get("checkout_date"):
                continue
            guests_to_enqueue.append(bg["guest_id"])

    jobs = []
    for gid in guests_to_enqueue:
        if not gid:
            continue
        res = await _enqueue_single_guest(tenant_id, booking_id, gid, action, actor)
        if res:
            jobs.append(res)
    return jobs if jobs else None

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
                booking_id,
                action,
            )
            return existing

        snapshot = await _build_payload_snapshot(tenant_id, booking_id)
        if not snapshot:
            logger.warning(
                "KBS auto-enqueue skipped (booking not found): booking=%s",
                booking_id,
            )
            return None

        booking = await db.bookings.find_one(
            {"tenant_id": tenant_id, "id": booking_id},
            {"_id": 0, "guest_id": 1, "kbs_reported": 1, "kbs_test": 1},
        )

        # Kurumdan doğrulanmış bir giriş makbuzu yoksa otomatik çıkış
        # bildirimi anlamsızdır: Jandarma bu isteği "tesiste kayıt yok"
        # diye reddeder. Bu durumda sahte bir checkout kuyruğu yerine net bir
        # operatör alarmı üretiriz. Haricen kaydedilmiş istisnai kayıtlar için
        # resepsiyon yine bilinçli olarak force=true ile manuel gönderebilir.
        if action == "checkout" and not ((booking or {}).get("kbs_reported") and not (booking or {}).get("kbs_test")):
            await db.kbs_alerts.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "kind": "checkin_not_confirmed",
                    "booking_id": booking_id,
                    "action": action,
                    "guest_name": snapshot.get("guest_name", ""),
                    "room_number": snapshot.get("room_number", ""),
                    "created_at": _now_iso(),
                    "acknowledged": False,
                }
            )
            logger.warning(
                "KBS auto-enqueue blocked (check-in not confirmed): booking=%s",
                booking_id,
            )
            return None

        ok, missing = validate_kbs_payload(snapshot, action)
        if not ok:
            await db.kbs_alerts.insert_one(
                {
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
                }
            )
            logger.warning(
                "KBS auto-enqueue blocked (missing fields): booking=%s missing=%s",
                booking_id,
                missing,
            )
            return None

        now_iso = _now_iso()
        job = {
            "_kind": QUEUE_KIND,
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "guest_id": (booking or {}).get("guest_id"),
            "action": action,
            "status": "pending",
            # Atomik tekillik kilidi (partial unique index ile birlikte):
            # open jobs (pending/in_progress) için set; closed (done/dead)
            # geçişlerinde unset edilir → aynı booking+action için aynı anda
            # en fazla 1 açık iş garanti.
            "_open_lock": f"{tenant_id}:{booking_id}:{action}",
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
        try:
            await db.kbs_reports.insert_one(job)
        except Exception as ins_err:
            # DuplicateKeyError → eşzamanlı bir başka enqueue zaten açtı; idempotent dön.
            if "duplicate key" in str(ins_err).lower() or "E11000" in str(ins_err):
                existing2 = await db.kbs_reports.find_one(
                    {
                        "_kind": QUEUE_KIND,
                        "tenant_id": tenant_id,
                        "_open_lock": f"{tenant_id}:{booking_id}:{action}",
                    },
                    {"_id": 0},
                )
                # Edge case: rakip transaction lock'u zaten unset etmiş (hızlı complete/dead).
                # (booking, action, open) ile ek arama → transient false-failure önler.
                if not existing2:
                    existing2 = await db.kbs_reports.find_one(
                        {
                            "_kind": QUEUE_KIND,
                            "tenant_id": tenant_id,
                            "booking_id": booking_id,
                            "action": action,
                            "status": {"$in": ["pending", "in_progress"]},
                        },
                        {"_id": 0},
                    )
                if existing2:
                    logger.info(
                        "KBS auto-enqueue race resolved (existing job): booking=%s action=%s",
                        booking_id,
                        action,
                    )
                    return existing2
            raise
        logger.info(
            "KBS auto-enqueue ok: booking=%s action=%s job=%s",
            booking_id,
            action,
            job["id"],
        )
        return job
    except Exception as e:
        logger.warning(
            "KBS auto-enqueue failed (non-blocking): booking=%s action=%s err=%s",
            booking_id,
            action,
            e,
        )
        return None
