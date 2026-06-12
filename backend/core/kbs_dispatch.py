"""KBS PMS-içi gönderici: bekleyen kuyruğu işle (claim → send → complete/fail).

Önceki tasarımda kuyruğu harici bir masaüstü ajan/bot claim edip KBS'ye
gönderiyordu. Bu modül aynı atomik kuyruk semantiğini (lease'li claim,
CAS'li complete/fail, exp. backoff, dead-letter alarmı) PMS'in KENDİ
içinde — bir Celery beat task'ından — koşturur, böylece gönderim otomatik
olur ve harici bot zorunluluğu kalkar.

Fail-closed: ``kbs_sender.kbs_dispatch_active()`` false ise (kimlik bilgisi
yok ve test mode kapalı) hiçbir iş claim edilmez — legacy harici-bot modeli
bozulmaz. Bekleyen iş VARSA ve gönderici aktif değilse, operatör tek seferlik
(throttled) ``kbs_alerts`` uyarısıyla bilgilendirilir.

Celery, her task gövdesini ``asyncio.run()`` ile yürütür; bu yüzden bu modül
modül-seviyesi Motor client'a DOKUNMAZ — çağıran taze, loop'a bağlı bir db
geçirir (``celery_tasks._fresh_mongo``).
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from core.kbs_payload_validation import validate_kbs_payload
from core.kbs_sender import (
    KBSCredentialsMissing,
    KBSSendError,
    kbs_credentials_configured,
    kbs_dispatch_active,
    kbs_test_mode,
    send_kbs_notification,
)

logger = logging.getLogger("core.kbs_dispatch")

QUEUE_KIND = "queue_job"
REPORT_KIND = "report"
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_LEASE_SECONDS = 300
WORKER_ID = "system:kbs_dispatch"

# Bekleyen iş varken gönderici aktif değilse, operatöre tekrar uyarmadan önce
# beklenecek minimum süre (uyarı seli önlenir).
_UNCONFIGURED_ALERT_THROTTLE_SECONDS = 3600


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _backoff_seconds(attempts: int) -> int:
    """Exp. backoff: 60s, 120s, 240s, 480s, 960s, cap 3600s (router ile aynı)."""
    base = 60 * (2 ** max(attempts - 1, 0))
    return min(base, 3600)


async def _raise_alert(db, tenant_id: str, *, kind: str, job: dict, error: str = "") -> None:
    """db.kbs_alerts'e alarm yaz (router._raise_kbs_alert ile aynı şema)."""
    try:
        await db.kbs_alerts.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "kind": kind,
            "job_id": job.get("id"),
            "booking_id": job.get("booking_id"),
            "guest_name": (job.get("payload") or {}).get("guest_name", ""),
            "room_number": (job.get("payload") or {}).get("room_number", ""),
            "action": job.get("action"),
            "attempts": job.get("attempts"),
            "last_error": error or job.get("last_error"),
            "worker_id": job.get("worker_id"),
            "created_at": _iso(_now()),
            "acknowledged": False,
        })
        logger.warning(
            "KBS dispatch alert: tenant=%s kind=%s booking=%s err=%s",
            tenant_id, kind, job.get("booking_id"), error,
        )
    except Exception as e:  # noqa: BLE001 — alarm ana akışı etkilememeli
        logger.warning("KBS dispatch alert insert failed: %s", e)


async def _maybe_alert_unconfigured(db, pending_count: int) -> None:
    """Bekleyen iş varken gönderici aktif değil → operatörü throttled uyar.

    Tenant-bağımsız tek bir 'config' alarmı yazılır (kimlik bilgisi tüm sistem
    için tek). Son uyarıdan beri throttle penceresi geçmediyse no-op.
    """
    if pending_count <= 0:
        return
    try:
        now = _now()
        existing = await db.kbs_alerts.find_one(
            {"kind": "send_unconfigured"},
            {"_id": 0, "created_at": 1},
            sort=[("created_at", -1)],
        )
        if existing and existing.get("created_at"):
            try:
                last = datetime.fromisoformat(existing["created_at"])
                if last.tzinfo is None:
                    last = last.replace(tzinfo=UTC)
                if (now - last).total_seconds() < _UNCONFIGURED_ALERT_THROTTLE_SECONDS:
                    return
            except (TypeError, ValueError):
                pass
        await db.kbs_alerts.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": "_system",
            "kind": "send_unconfigured",
            "last_error": (
                "KBS otomatik gönderim yapılandırılmamış (KBS_API_URL/"
                "KBS_API_TOKEN yok) — bekleyen bildirimler iletilemiyor"
            ),
            "pending_count": pending_count,
            "created_at": _iso(now),
            "acknowledged": False,
        })
        logger.warning(
            "KBS dispatch: gönderici yapılandırılmamış, %d bekleyen iş var",
            pending_count,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("KBS unconfigured alert failed: %s", e)


async def _count_claimable(db, now_iso: str) -> int:
    """Şu an claim edilebilir (backoff penceresi geçmiş) bekleyen iş sayısı."""
    return await db.kbs_reports.count_documents({
        "_kind": QUEUE_KIND,
        "status": "pending",
        "$or": [
            {"next_retry_at": None},
            {"next_retry_at": {"$exists": False}},
            {"next_retry_at": {"$lte": now_iso}},
        ],
    })


async def _claim_one(db, now: datetime) -> dict | None:
    """Bir bekleyen işi atomik claim et (pending → in_progress, attempts+1).

    find_one_and_update CAS: backoff penceresi geçmiş pending VEYA lease'i
    dolmuş in_progress işlerden ilkini alır. None → claim edilebilir iş yok.
    """
    from pymongo import ReturnDocument

    now_iso = _iso(now)
    leased_until = _iso(now + timedelta(seconds=DEFAULT_LEASE_SECONDS))
    query = {
        "_kind": QUEUE_KIND,
        "$or": [
            {"$and": [
                {"status": "pending"},
                {"$or": [
                    {"next_retry_at": None},
                    {"next_retry_at": {"$exists": False}},
                    {"next_retry_at": {"$lte": now_iso}},
                ]},
            ]},
            {"status": "in_progress", "leased_until": {"$lt": now_iso}},
        ],
    }
    update = {
        "$set": {
            "status": "in_progress",
            "worker_id": WORKER_ID,
            "leased_until": leased_until,
            "claimed_at": now_iso,
            "updated_at": now_iso,
        },
        "$inc": {"attempts": 1},
    }
    job = await db.kbs_reports.find_one_and_update(
        query, update,
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )
    return job


async def _complete(db, job: dict, reference: str) -> None:
    """in_progress → done (CAS), booking bayrağı + legacy report (router pariteli)."""
    tenant_id = job["tenant_id"]
    job_id = job["id"]
    now_iso = _iso(_now())
    is_test_ref = reference.startswith("TEST-")

    cas = await db.kbs_reports.update_one(
        {
            "_kind": QUEUE_KIND, "tenant_id": tenant_id, "id": job_id,
            "status": "in_progress", "worker_id": WORKER_ID,
        },
        {
            "$set": {
                "status": "done",
                "kbs_reference": reference,
                "completed_at": now_iso,
                "updated_at": now_iso,
                "kbs_test": is_test_ref,
            },
            "$unset": {"_open_lock": ""},
        },
    )
    if cas.modified_count == 0:
        logger.warning("KBS dispatch complete CAS no-op (lease drift?): job=%s", job_id)
        return

    booking_update = {
        "kbs_reported": True,
        "kbs_reported_at": now_iso,
        "kbs_reference": reference,
    }
    if is_test_ref:
        booking_update["kbs_test"] = True
    await db.bookings.update_one(
        {"tenant_id": tenant_id, "id": job["booking_id"]},
        {"$set": booking_update},
    )
    await db.kbs_reports.insert_one({
        "_kind": REPORT_KIND,
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "date": (job.get("payload", {}).get("check_in") or now_iso)[:10],
        "status": "submitted",
        "guest_count": 1,
        "guest_ids": [job["booking_id"]],
        "submission_reference": reference,
        "notes": "via auto-dispatch",
        "submitted_by": f"worker:{WORKER_ID}",
        "submitted_by_email": "system",
        "queue_job_id": job_id,
        "kbs_test": is_test_ref,
        "created_at": now_iso,
    })


async def _fail(db, job: dict, error: str) -> bool:
    """in_progress → pending(retry) | dead (CAS, router pariteli). dead ise alarm.

    Returns: will_retry.
    """
    tenant_id = job["tenant_id"]
    job_id = job["id"]
    now = _now()
    now_iso = _iso(now)
    attempts = job.get("attempts", 0)
    max_attempts = job.get("max_attempts", DEFAULT_MAX_ATTEMPTS)
    will_retry = attempts < max_attempts

    if will_retry:
        update = {
            "$set": {
                "status": "pending",
                "worker_id": None,
                "leased_until": None,
                "next_retry_at": _iso(now + timedelta(seconds=_backoff_seconds(attempts))),
                "last_error": error,
                "updated_at": now_iso,
            },
        }
    else:
        update = {
            "$set": {
                "status": "dead",
                "failed_at": now_iso,
                "last_error": error,
                "updated_at": now_iso,
            },
            "$unset": {"_open_lock": ""},
        }
    cas = await db.kbs_reports.update_one(
        {
            "_kind": QUEUE_KIND, "tenant_id": tenant_id, "id": job_id,
            "status": "in_progress", "worker_id": WORKER_ID,
        },
        update,
    )
    if cas.modified_count == 0:
        logger.warning("KBS dispatch fail CAS no-op (lease drift?): job=%s", job_id)
        return will_retry
    if not will_retry:
        dead = dict(job)
        dead["attempts"] = attempts
        dead["status"] = "dead"
        await _raise_alert(db, tenant_id, kind="dead_letter", job=dead, error=error)
    return will_retry


async def _handle_missing_data(db, job: dict, missing: list[str]) -> None:
    """Gönderim öncesi payload eksik → missing_data alarmı + işi dead'e çek.

    Eksik veriyle gönderim DENENMEZ (KBS reddeder, attempts boşa yanar). İş
    dead'e çekilir ve operatör missing_data alarmıyla yönlendirilir; veri
    tamamlandığında nightly sweep / check-in yeniden enqueue eder.
    """
    tenant_id = job["tenant_id"]
    job_id = job["id"]
    now_iso = _iso(_now())
    await db.kbs_reports.update_one(
        {"_kind": QUEUE_KIND, "tenant_id": tenant_id, "id": job_id, "worker_id": WORKER_ID},
        {
            "$set": {
                "status": "dead",
                "failed_at": now_iso,
                "last_error": f"missing_data: {','.join(missing)}",
                "updated_at": now_iso,
            },
            "$unset": {"_open_lock": ""},
        },
    )
    try:
        await db.kbs_alerts.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "kind": "missing_data",
            "job_id": job_id,
            "booking_id": job.get("booking_id"),
            "action": job.get("action"),
            "missing_fields": missing,
            "guest_name": (job.get("payload") or {}).get("guest_name", ""),
            "room_number": (job.get("payload") or {}).get("room_number", ""),
            "created_at": now_iso,
            "acknowledged": False,
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("KBS missing_data alert failed: %s", e)
    logger.warning(
        "KBS dispatch blocked (missing fields): booking=%s missing=%s",
        job.get("booking_id"), missing,
    )


async def dispatch_pending_kbs_jobs(db, *, limit: int = 50) -> dict:
    """Bekleyen KBS kuyruğunu işle: claim → send → complete/fail.

    Args:
        db: taze, loop'a bağlı Motor db (TenantAware DEĞİL — sistem geneli tarar).
        limit: tek koşuda işlenecek üst sınır.

    Returns: özet sözlük.
    """
    now_iso = _iso(_now())

    if not kbs_dispatch_active():
        pending = await _count_claimable(db, now_iso)
        await _maybe_alert_unconfigured(db, pending)
        return {
            "skipped": "inactive",
            "credentials": kbs_credentials_configured(),
            "test_mode": kbs_test_mode(),
            "pending": pending,
        }

    sent = failed = dead = missing = 0
    processed = 0
    for _ in range(max(1, limit)):
        job = await _claim_one(db, _now())
        if job is None:
            break
        processed += 1

        # max_attempts aşıldıysa hemen dead (router claim pariteli)
        if job.get("attempts", 0) > job.get("max_attempts", DEFAULT_MAX_ATTEMPTS):
            await db.kbs_reports.update_one(
                {"_kind": QUEUE_KIND, "tenant_id": job["tenant_id"], "id": job["id"]},
                {
                    "$set": {
                        "status": "dead", "failed_at": now_iso, "updated_at": now_iso,
                        "last_error": "max_attempts exceeded on claim",
                    },
                    "$unset": {"_open_lock": ""},
                },
            )
            await _raise_alert(
                db, job["tenant_id"], kind="dead_letter", job=job,
                error="max_attempts exceeded on claim",
            )
            dead += 1
            continue

        payload = job.get("payload") or {}
        ok, missing_fields = validate_kbs_payload(payload)
        if not ok:
            await _handle_missing_data(db, job, missing_fields)
            missing += 1
            continue

        try:
            reference = await send_kbs_notification(payload, job.get("action", "checkin"))
        except KBSCredentialsMissing as exc:
            # Yarış: dispatch_active true iken kimlik bilgisi kayboldu. İşi
            # bekleyene geri bırak (attempts'i geri al), gönderim denenmemiş say.
            await db.kbs_reports.update_one(
                {"_kind": QUEUE_KIND, "tenant_id": job["tenant_id"], "id": job["id"],
                 "worker_id": WORKER_ID},
                {
                    "$set": {
                        "status": "pending", "worker_id": None, "leased_until": None,
                        "updated_at": _iso(_now()),
                    },
                    "$inc": {"attempts": -1},
                },
            )
            logger.warning("KBS dispatch: kimlik bilgisi kayboldu, iş geri bırakıldı: %s", exc)
            break
        except KBSSendError as exc:
            if await _fail(db, job, str(exc)):
                failed += 1
            else:
                dead += 1
            continue
        except Exception as exc:  # noqa: BLE001 — beklenmedik → retry'lanır
            if await _fail(db, job, f"unexpected: {exc}"):
                failed += 1
            else:
                dead += 1
            continue

        await _complete(db, job, reference)
        sent += 1

    return {
        "processed": processed,
        "sent": sent,
        "retry": failed,
        "dead": dead,
        "missing_data": missing,
    }
