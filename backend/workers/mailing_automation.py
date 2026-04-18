"""Mailing automation worker.

Periodically scans bookings for trigger events (booking_created,
checkin_reminder, checkout_thanks) per tenant and sends the configured
template via Resend. De-dupes via the `mailing_automation_log` collection
and consumes credits the same way manual campaigns do.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import UTC, date, datetime, timedelta

logger = logging.getLogger("workers.mailing_automation")

INTERVAL_SECONDS = 600  # 10 minutes
BOOKING_CREATED_LOOKBACK_HOURS = 24  # only notify bookings created in last 24h
PER_RUN_TENANT_LIMIT = 200
PER_TRIGGER_PER_RUN_LIMIT = 100

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_task: asyncio.Task | None = None


def _today() -> date:
    return datetime.now(UTC).date()


def _safe_date(s) -> date | None:
    if not s:
        return None
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).date()
    except Exception:
        try:
            return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
        except Exception:
            return None


def _personalize(html: str, subject: str, name: str, hotel: str) -> tuple[str, str]:
    repl = {
        "{{name}}": name, "{{hotel}}": hotel,
        "{{misafir}}": name, "{{otel}}": hotel,
    }
    for k, v in repl.items():
        html = html.replace(k, v)
        subject = subject.replace(k, v)
    return subject, html


async def _resolve_guest_email_and_name(db, tenant_id: str, guest_id: str) -> tuple[str | None, str]:
    """Find guest email (decrypting if needed) and display name. Tenant-scoped."""
    if not guest_id or not tenant_id:
        return None, "Misafir"
    g = await db.guests.find_one({"id": guest_id, "tenant_id": tenant_id}, {"_id": 0})
    if not g:
        return None, "Misafir"
    email = g.get("email")
    if not (isinstance(email, str) and _EMAIL_RE.match(email)):
        try:
            from security.encrypted_lookup import decrypt_user_doc
            d = decrypt_user_doc({**g})
            e = d.get("email")
            email = e if (isinstance(e, str) and _EMAIL_RE.match(e)) else None
        except Exception:
            email = None
    name = g.get("name") or f"{g.get('first_name', '')} {g.get('last_name', '')}".strip() or "Misafir"
    return (email.lower() if email else None), name


async def _ensure_credits_doc(db, tenant_id: str) -> None:
    """Create mailing_credits doc with 100 free credits if missing."""
    await db.mailing_credits.update_one(
        {"tenant_id": tenant_id},
        {"$setOnInsert": {
            "tenant_id": tenant_id,
            "balance": 100,
            "lifetime_used": 0,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }},
        upsert=True,
    )


async def _consume_credit_atomic(db, tenant_id: str) -> bool:
    """Try to deduct 1 credit. Return True on success."""
    res = await db.mailing_credits.find_one_and_update(
        {"tenant_id": tenant_id, "balance": {"$gte": 1}},
        {"$inc": {"balance": -1, "lifetime_used": 1},
         "$set": {"updated_at": datetime.now(UTC).isoformat()}},
    )
    return res is not None


async def _refund_credit(db, tenant_id: str) -> None:
    await db.mailing_credits.update_one(
        {"tenant_id": tenant_id},
        {"$inc": {"balance": 1, "lifetime_used": -1}},
    )


async def _claim_send(db, tenant_id: str, trigger: str, booking_id: str) -> bool:
    """Atomically claim the right to send. Returns False if already claimed.
    Relies on a unique index over (tenant_id, trigger_type, booking_id)."""
    try:
        await db.mailing_automation_log.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "trigger_type": trigger,
            "booking_id": booking_id,
            "status": "claimed",
            "claimed_at": datetime.now(UTC).isoformat(),
        })
        return True
    except Exception:
        return False


async def _finalize_send(db, tenant_id: str, trigger: str, booking_id: str,
                         email: str, ok: bool, provider_id: str | None = None,
                         err: str | None = None) -> None:
    await db.mailing_automation_log.update_one(
        {"tenant_id": tenant_id, "trigger_type": trigger, "booking_id": booking_id},
        {"$set": {
            "recipient_email": email,
            "status": "sent" if ok else "failed",
            "provider_id": provider_id,
            "error": err,
            "sent_at": datetime.now(UTC).isoformat(),
        }},
    )


async def _ensure_indexes(db) -> None:
    try:
        await db.mailing_automation_log.create_index(
            [("tenant_id", 1), ("trigger_type", 1), ("booking_id", 1)],
            unique=True, name="uniq_tenant_trigger_booking",
        )
    except Exception as e:
        logger.warning("[mailing-auto] index create skipped: %s", e)


def _bookings_query_for(trigger: str, offset_days: int) -> dict:
    today = _today()
    target = today + timedelta(days=offset_days)
    if trigger == "booking_created":
        cutoff = (datetime.now(UTC) - timedelta(hours=BOOKING_CREATED_LOOKBACK_HOURS)).isoformat()
        return {"created_at": {"$gte": cutoff}}
    if trigger == "checkin_reminder":
        # offset_days is typically -1 → target == tomorrow
        ds = target.isoformat()
        return {"$or": [
            {"check_in": {"$regex": f"^{ds}"}},
            {"check_in": ds},
        ]}
    if trigger == "checkout_thanks":
        # offset_days is positive (after checkout) → check_out date == today - offset_days
        target = today - timedelta(days=offset_days)
        ds = target.isoformat()
        return {"$or": [
            {"check_out": {"$regex": f"^{ds}"}},
            {"check_out": ds},
        ]}
    if trigger == "in_house_guests":
        # currently in house: check_in <= today AND check_out > today
        ts = today.isoformat()
        return {
            "check_in": {"$lte": ts + "T23:59:59"},
            "check_out": {"$gt": ts},
        }
    return {}


async def _run_trigger_for_tenant(db, tenant: dict, automation: dict) -> int:
    """Process one (tenant, automation) pair. Returns sent count."""
    from core.email import send_email

    trigger = automation["trigger_type"]
    template = await db.mailing_templates.find_one(
        {"id": automation.get("template_id"), "tenant_id": tenant["id"]}, {"_id": 0}
    )
    if not template:
        return 0

    offset_days = int(automation.get("offset_days", 0) or 0)
    base_query = _bookings_query_for(trigger, offset_days)
    query = {**base_query, "tenant_id": tenant["id"]}
    cursor = db.bookings.find(query, {"_id": 0}).limit(PER_TRIGGER_PER_RUN_LIMIT)

    sent = 0
    hotel = tenant.get("property_name") or tenant.get("name") or "Otel"
    reply_to = tenant.get("email")

    async for booking in cursor:
        bid = booking.get("id") or booking.get("booking_id")
        if not bid:
            continue
        # Atomic claim: only one worker can proceed for this (tenant, trigger, booking)
        if not await _claim_send(db, tenant["id"], trigger, bid):
            continue
        email, gname = await _resolve_guest_email_and_name(
            db, tenant["id"], booking.get("guest_id", "")
        )
        if not email:
            await _finalize_send(db, tenant["id"], trigger, bid, "<no-email>", False,
                                 err="guest has no email")
            continue
        if not await _consume_credit_atomic(db, tenant["id"]):
            await _finalize_send(db, tenant["id"], trigger, bid, email, False,
                                 err="insufficient credits")
            logger.info("[mailing-auto] tenant=%s out of credits — pausing", tenant["id"])
            return sent
        psubj, phtml = _personalize(template["html"], template["subject"],
                                    booking.get("guest_name") or gname, hotel)
        try:
            r = await send_email(to=email, subject=psubj, html=phtml, reply_to=reply_to)
            ok = bool(r.get("sent"))
            if not ok:
                await _refund_credit(db, tenant["id"])
            await _finalize_send(db, tenant["id"], trigger, bid, email, ok,
                                 provider_id=r.get("id"), err=r.get("error"))
            if ok:
                sent += 1
        except Exception as e:
            await _refund_credit(db, tenant["id"])
            await _finalize_send(db, tenant["id"], trigger, bid, email, False, err=str(e))

    return sent


async def _run_once() -> dict:
    from server import db
    summary = {"tenants_processed": 0, "total_sent": 0}
    cursor = db.mailing_automations.find({"enabled": True}, {"_id": 0}).limit(PER_RUN_TENANT_LIMIT)
    automations = await cursor.to_list(PER_RUN_TENANT_LIMIT)
    by_tenant: dict[str, list[dict]] = {}
    for a in automations:
        by_tenant.setdefault(a["tenant_id"], []).append(a)

    for tenant_id, automations_for_tenant in by_tenant.items():
        tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0})
        if not tenant:
            continue
        await _ensure_credits_doc(db, tenant_id)
        summary["tenants_processed"] += 1
        for a in automations_for_tenant:
            try:
                count = await _run_trigger_for_tenant(db, tenant, a)
                summary["total_sent"] += count
                if count > 0:
                    await db.mailing_automations.update_one(
                        {"tenant_id": tenant_id, "trigger_type": a["trigger_type"]},
                        {"$set": {
                            "last_run_at": datetime.now(UTC).isoformat(),
                            "last_sent_count": count,
                        }},
                    )
            except Exception:
                logger.exception("[mailing-auto] failed for tenant=%s trigger=%s",
                                 tenant_id, a.get("trigger_type"))
    if summary["total_sent"]:
        logger.info("[mailing-auto] cycle complete: %s", summary)
    return summary


async def _loop() -> None:
    logger.info("[mailing-auto] worker started (interval=%ds)", INTERVAL_SECONDS)
    try:
        from server import db
        await _ensure_indexes(db)
    except Exception as e:
        logger.warning("[mailing-auto] could not ensure indexes: %s", e)
    while True:
        try:
            await _run_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[mailing-auto] cycle crashed")
        try:
            await asyncio.sleep(INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise


def start() -> asyncio.Task:
    """Start the background worker. Idempotent."""
    global _task
    if _task and not _task.done():
        return _task
    _task = asyncio.create_task(_loop(), name="mailing-automation")
    return _task


async def stop() -> None:
    """Cancel the background worker if running."""
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):
            pass
    _task = None
