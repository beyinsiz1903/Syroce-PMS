"""
Webhook Delivery Service with Exponential Backoff Retry
=======================================================

Replaces fire-and-forget webhook delivery with:
  - Exponential backoff: 2s, 4s, 8s, 16s, 32s (max 5 retries)
  - Idempotency key per delivery
  - Attempt tracking: attempt_count, next_retry_at, last_error
  - Terminal failure → DLQ (dead letter queue)
  - Ops events emitted at each lifecycle stage
  - Queryable delivery records
"""

import asyncio
import hashlib
import hmac
import json
import logging
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from routers.ops_event_emitter import (
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_SUCCESS,
    SEVERITY_WARNING,
    emit_ops_event,
)

logger = logging.getLogger("webhook_retry")

# Retry config
MAX_ATTEMPTS = 5
BASE_DELAY_SECONDS = 2.0
MAX_DELAY_SECONDS = 60.0
DELIVERY_TIMEOUT_SECONDS = 10

# Delivery statuses
STATUS_PENDING = "pending"
STATUS_DELIVERING = "delivering"
STATUS_SUCCEEDED = "succeeded"
STATUS_RETRYING = "retrying"
STATUS_FAILED = "failed"
STATUS_DLQ = "dlq"


def _now_iso():
    return datetime.now(UTC).isoformat()


def _uuid():
    return str(uuid.uuid4())


def _calculate_backoff(attempt: int) -> float:
    """Exponential backoff with jitter: base * 2^attempt + random(0,1)"""
    delay = min(BASE_DELAY_SECONDS * (2**attempt) + random.uniform(0, 1), MAX_DELAY_SECONDS)
    return delay


def _generate_idempotency_key(webhook_id: str, event: str, delivery_id: str) -> str:
    """Generate idempotency key for delivery deduplication."""
    raw = f"{webhook_id}:{event}:{delivery_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


async def deliver_webhook_with_retry(
    webhook_doc: dict,
    event: str,
    data: dict,
) -> dict[str, Any]:
    """Deliver webhook with exponential backoff retry.

    Returns delivery result dict.
    """
    from core.tenant_db import get_system_db

    sysdb = get_system_db()

    delivery_id = _uuid()
    idempotency_key = _generate_idempotency_key(webhook_doc["id"], event, delivery_id)
    tenant_id = webhook_doc.get("tenant_id", "")
    agency_id = webhook_doc.get("agency_id", "")
    webhook_url = webhook_doc["url"]
    correlation_id = _uuid()

    # Build payload
    payload = {
        "event": event,
        "timestamp": _now_iso(),
        "delivery_id": delivery_id,
        "idempotency_key": idempotency_key,
        "data": data,
    }
    body = json.dumps(payload, default=str)

    # Build headers
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": event,
        "X-Webhook-Delivery": delivery_id,
        "X-Idempotency-Key": idempotency_key,
    }
    secret = webhook_doc.get("secret")
    if secret:
        sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={sig}"

    # Create initial delivery record
    delivery_record = {
        "id": delivery_id,
        "webhook_id": webhook_doc["id"],
        "agency_id": agency_id,
        "tenant_id": tenant_id,
        "event": event,
        "url": webhook_url,
        "idempotency_key": idempotency_key,
        "correlation_id": correlation_id,
        "status": STATUS_PENDING,
        "attempt_count": 0,
        "max_attempts": MAX_ATTEMPTS,
        "last_error": None,
        "last_status_code": None,
        "next_retry_at": None,
        "attempts": [],
        "created_at": _now_iso(),
        "completed_at": None,
    }
    await sysdb.webhook_deliveries.insert_one(delivery_record)

    # Emit: delivery started
    await emit_ops_event(
        "webhook.delivery.started",
        tenant_id,
        channel="b2b_webhook",
        severity=SEVERITY_INFO,
        title=f"Webhook teslimatı baslatildi: {event}",
        details={
            "delivery_id": delivery_id,
            "webhook_id": webhook_doc["id"],
            "url": webhook_url,
            "event": event,
            "agency_id": agency_id,
        },
        affected_entity_type="webhook",
        affected_entity_id=webhook_doc["id"],
        correlation_id=correlation_id,
    )

    # Retry loop
    last_error = None
    last_status_code = 0

    for attempt in range(MAX_ATTEMPTS):
        attempt_start = _now_iso()
        attempt_error = None
        attempt_status_code = 0

        try:
            # Update status to delivering
            await sysdb.webhook_deliveries.update_one(
                {"id": delivery_id},
                {
                    "$set": {
                        "status": STATUS_DELIVERING,
                        "attempt_count": attempt + 1,
                    }
                },
            )

            # v109 Bug DAL round-7 follow-up #3: replaced bespoke SSRF check
            # with centralized rebinding-safe helper. safe_post_async resolves
            # all IPs, validates each, and pins the TCP destination so
            # rebinding cannot race the connect() call.
            # Follow-up #4 nit: keep exact "SSRF blocked: ..." string by
            # setting attempt_error directly (don't re-raise into broad
            # Exception handler which would prepend "Unexpected error:").
            from integrations.xchange.safety import EgressDenied, safe_post_async

            try:
                resp = await safe_post_async(
                    webhook_url,
                    timeout=DELIVERY_TIMEOUT_SECONDS,
                    content=body,
                    headers=headers,
                )
                attempt_status_code = resp.status_code
            except EgressDenied as _ed:
                attempt_error = f"SSRF blocked: {_ed}"
                attempt_status_code = 0

            if attempt_error is None and 200 <= attempt_status_code < 300:
                # SUCCESS
                attempt_record = {
                    "attempt_number": attempt + 1,
                    "status_code": attempt_status_code,
                    "error": None,
                    "started_at": attempt_start,
                    "completed_at": _now_iso(),
                }

                await sysdb.webhook_deliveries.update_one(
                    {"id": delivery_id},
                    {
                        "$set": {
                            "status": STATUS_SUCCEEDED,
                            "last_status_code": attempt_status_code,
                            "completed_at": _now_iso(),
                        },
                        "$push": {"attempts": attempt_record},
                    },
                )

                await emit_ops_event(
                    "webhook.delivery.succeeded",
                    tenant_id,
                    channel="b2b_webhook",
                    severity=SEVERITY_SUCCESS,
                    title=f"Webhook basariyla teslim edildi: {event}",
                    details={
                        "delivery_id": delivery_id,
                        "url": webhook_url,
                        "attempt_count": attempt + 1,
                        "status_code": attempt_status_code,
                    },
                    affected_entity_type="webhook",
                    affected_entity_id=webhook_doc["id"],
                    correlation_id=correlation_id,
                )

                logger.info(
                    "[WEBHOOK] Delivered %s to %s (attempt %d, status %d)",
                    event,
                    webhook_url,
                    attempt + 1,
                    attempt_status_code,
                )
                return {"delivery_id": delivery_id, "status": STATUS_SUCCEEDED, "attempts": attempt + 1}

            # Non-2xx response — treat as failure for this attempt
            # (Skip if attempt_error is already set, e.g. SSRF blocked.)
            if attempt_error is None:
                attempt_error = f"HTTP {attempt_status_code}"

        except httpx.TimeoutException:
            attempt_error = "Connection timeout"
        except httpx.ConnectError as exc:
            attempt_error = f"Connection error: {str(exc)[:200]}"
        except Exception as exc:
            attempt_error = f"Unexpected error: {str(exc)[:200]}"

        # Record failed attempt
        last_error = attempt_error
        last_status_code = attempt_status_code

        attempt_record = {
            "attempt_number": attempt + 1,
            "status_code": attempt_status_code,
            "error": attempt_error,
            "started_at": attempt_start,
            "completed_at": _now_iso(),
        }

        # Determine if we should retry
        if attempt < MAX_ATTEMPTS - 1:
            backoff = _calculate_backoff(attempt)
            next_retry_at = (datetime.now(UTC) + timedelta(seconds=backoff)).isoformat()

            await sysdb.webhook_deliveries.update_one(
                {"id": delivery_id},
                {
                    "$set": {
                        "status": STATUS_RETRYING,
                        "last_error": attempt_error,
                        "last_status_code": attempt_status_code,
                        "next_retry_at": next_retry_at,
                        "attempt_count": attempt + 1,
                    },
                    "$push": {"attempts": attempt_record},
                },
            )

            await emit_ops_event(
                "webhook.delivery.retrying",
                tenant_id,
                channel="b2b_webhook",
                severity=SEVERITY_WARNING,
                title=f"Webhook retry: {event} (deneme {attempt + 1}/{MAX_ATTEMPTS})",
                details={
                    "delivery_id": delivery_id,
                    "url": webhook_url,
                    "attempt_count": attempt + 1,
                    "last_error": attempt_error,
                    "next_retry_at": next_retry_at,
                    "backoff_seconds": round(backoff, 1),
                },
                affected_entity_type="webhook",
                affected_entity_id=webhook_doc["id"],
                correlation_id=correlation_id,
            )

            logger.warning(
                "[WEBHOOK] Delivery failed for %s (attempt %d/%d, error: %s). Retrying in %.1fs",
                webhook_url,
                attempt + 1,
                MAX_ATTEMPTS,
                attempt_error,
                backoff,
            )

            await asyncio.sleep(backoff)
        else:
            # Last attempt — record as terminal failure
            await sysdb.webhook_deliveries.update_one(
                {"id": delivery_id},
                {
                    "$set": {
                        "status": STATUS_FAILED,
                        "last_error": attempt_error,
                        "last_status_code": attempt_status_code,
                        "attempt_count": attempt + 1,
                        "completed_at": _now_iso(),
                    },
                    "$push": {"attempts": attempt_record},
                },
            )

    # ═══ TERMINAL FAILURE — Move to DLQ ═══
    dlq_id = _uuid()
    dlq_doc = {
        "id": dlq_id,
        "delivery_id": delivery_id,
        "webhook_id": webhook_doc["id"],
        "agency_id": agency_id,
        "tenant_id": tenant_id,
        "event": event,
        "url": webhook_url,
        "payload": payload,
        "attempt_count": MAX_ATTEMPTS,
        "last_error": last_error,
        "last_status_code": last_status_code,
        "idempotency_key": idempotency_key,
        "correlation_id": correlation_id,
        "status": "pending",  # pending in DLQ for manual retry
        "created_at": _now_iso(),
        "retried_at": None,
    }
    await sysdb.webhook_dlq.insert_one(dlq_doc)

    # Update delivery status to DLQ
    await sysdb.webhook_deliveries.update_one(
        {"id": delivery_id},
        {"$set": {"status": STATUS_DLQ, "dlq_id": dlq_id}},
    )

    # Emit terminal failure event
    await emit_ops_event(
        "webhook.delivery.terminal_failure",
        tenant_id,
        channel="b2b_webhook",
        severity=SEVERITY_CRITICAL,
        title=f"Webhook teslimatı tamamen başarısız: {event}",
        details={
            "delivery_id": delivery_id,
            "dlq_id": dlq_id,
            "url": webhook_url,
            "event": event,
            "attempt_count": MAX_ATTEMPTS,
            "last_error": last_error,
            "last_status_code": last_status_code,
            "agency_id": agency_id,
        },
        affected_entity_type="webhook",
        affected_entity_id=webhook_doc["id"],
        correlation_id=correlation_id,
    )

    # Also emit DLQ event
    await emit_ops_event(
        "webhook.delivery.dlq",
        tenant_id,
        channel="b2b_webhook",
        severity=SEVERITY_CRITICAL,
        title=f"Webhook DLQ'ya tasindi: {event}",
        details={
            "dlq_id": dlq_id,
            "delivery_id": delivery_id,
            "url": webhook_url,
            "agency_id": agency_id,
        },
        affected_entity_type="webhook",
        affected_entity_id=webhook_doc["id"],
        correlation_id=correlation_id,
    )

    logger.error(
        "[WEBHOOK-DLQ] Terminal failure for %s → %s. DLQ ID: %s (attempts: %d)",
        event,
        webhook_url,
        dlq_id,
        MAX_ATTEMPTS,
    )

    return {"delivery_id": delivery_id, "status": STATUS_DLQ, "dlq_id": dlq_id, "attempts": MAX_ATTEMPTS}


async def fire_webhooks_with_retry(tenant_id: str, agency_id: str, event: str, data: dict):
    """Find all active webhooks for agency subscribed to event and deliver with retry."""
    from core.tenant_db import get_system_db

    sysdb = get_system_db()

    webhooks = await sysdb.agency_webhooks.find(
        {
            "tenant_id": tenant_id,
            "agency_id": agency_id,
            "is_active": True,
            "events": event,
        },
        {"_id": 0},
    ).to_list(50)

    results = []
    for wh in webhooks:
        try:
            result = await deliver_webhook_with_retry(wh, event, data)
            results.append(result)
        except Exception as exc:
            logger.error("Webhook fire error for %s: %s", wh.get("url"), exc)
            results.append({"delivery_id": None, "status": "error", "error": str(exc)})

    return results


# Module-level strong-reference set for fire-and-forget tasks.
# Prevents asyncio garbage-collecting in-flight webhook deliveries
# (event loop only weak-refs tasks). Tasks self-evict on completion.
_pending_emit_tasks: set = set()


def schedule_emit_reservation_updated(
    tenant_id: str,
    booking_id: str,
    change: str,
    extra: dict | None = None,
) -> None:
    """Sync, GC-safe scheduler for `emit_reservation_updated`.

    Call this from request handlers — it creates the task, holds a strong
    reference until completion, and never raises (logs internally).
    """
    try:
        import asyncio as _asyncio

        loop = _asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (e.g. called from sync context) — skip silently.
        logger.warning(
            "schedule_emit_reservation_updated: no running loop (booking=%s change=%s)",
            booking_id,
            change,
        )
        return
    try:
        task = loop.create_task(emit_reservation_updated(tenant_id, booking_id, change, extra))
        _pending_emit_tasks.add(task)
        task.add_done_callback(_pending_emit_tasks.discard)
    except Exception:
        logger.exception(
            "schedule_emit_reservation_updated failed (booking=%s change=%s)",
            booking_id,
            change,
        )


async def emit_reservation_updated(
    tenant_id: str,
    booking_id: str,
    change: str,
    extra: dict | None = None,
) -> None:
    """PMS-side `reservation.updated` emitter.

    Looks up the booking; if it has `agency_id`, fires `reservation.updated`
    webhook to all subscribed agency endpoints with retry/DLQ semantics.

    `change` describes the trigger (e.g. "checked_in", "checked_out",
    "payment_added", "payment_voided", "charge_added", "charge_voided",
    "late_checkout_approved", "early_checkin_approved", "room_moved",
    "room_upgraded"). Failure is non-fatal — PMS flows must not break
    if webhook delivery has issues (logged via deliver_webhook_with_retry).
    """
    try:
        from core.database import db

        booking = await db.bookings.find_one(
            {"id": booking_id, "tenant_id": tenant_id},
            {
                "_id": 0,
                "id": 1,
                "agency_id": 1,
                "confirmation_code": 1,
                "status": 1,
                "room_type": 1,
                "room_number": 1,
                "check_in": 1,
                "check_out": 1,
                "guest_name": 1,
                "total_amount": 1,
                "balance": 1,
                "checked_in_at": 1,
                "checked_out_at": 1,
            },
        )
        if not booking or not booking.get("agency_id"):
            return  # not an agency booking → nothing to emit

        payload = {
            "reservation_id": booking.get("id"),
            "confirmation_code": booking.get("confirmation_code", ""),
            "status": booking.get("status", ""),
            "change": change,
            "room_type": booking.get("room_type", ""),
            "room_number": booking.get("room_number", ""),
            "check_in": booking.get("check_in", ""),
            "check_out": booking.get("check_out", ""),
            "guest_name": booking.get("guest_name", ""),
            "total_amount": booking.get("total_amount"),
            "balance": booking.get("balance"),
            "checked_in_at": booking.get("checked_in_at"),
            "checked_out_at": booking.get("checked_out_at"),
            "updated_at": _now_iso(),
        }
        if extra:
            payload.update(extra)

        await fire_webhooks_with_retry(tenant_id, booking["agency_id"], "reservation.updated", payload)
    except Exception:
        logger.exception(
            "emit_reservation_updated failed (tenant=%s booking=%s change=%s)",
            tenant_id,
            booking_id,
            change,
        )


async def retry_dlq_item(dlq_id: str) -> dict[str, Any]:
    """Manually retry a DLQ item."""
    from core.tenant_db import get_system_db

    sysdb = get_system_db()

    dlq_item = await sysdb.webhook_dlq.find_one({"id": dlq_id}, {"_id": 0})
    if not dlq_item:
        return {"ok": False, "error": "DLQ item bulunamadi"}

    if dlq_item["status"] != "pending":
        return {"ok": False, "error": f"DLQ item durumu: {dlq_item['status']}. Sadece 'pending' durumundakiler retry edilebilir."}

    # Mark DLQ item as retrying
    await sysdb.webhook_dlq.update_one(
        {"id": dlq_id},
        {"$set": {"status": "retrying", "retried_at": _now_iso()}},
    )

    # Get webhook doc
    wh = await sysdb.agency_webhooks.find_one(
        {"id": dlq_item["webhook_id"]},
        {"_id": 0},
    )
    if not wh:
        await sysdb.webhook_dlq.update_one(
            {"id": dlq_id},
            {"$set": {"status": "failed", "last_error": "Webhook bulunamadi"}},
        )
        return {"ok": False, "error": "Ilgili webhook bulunamadi"}

    # Attempt single delivery
    payload_data = dlq_item.get("payload", {}).get("data", {})
    event = dlq_item["event"]

    try:
        result = await deliver_webhook_with_retry(wh, event, payload_data)
        if result["status"] == STATUS_SUCCEEDED:
            await sysdb.webhook_dlq.update_one(
                {"id": dlq_id},
                {"$set": {"status": "resolved", "resolved_at": _now_iso()}},
            )
            return {"ok": True, "result": result}
        else:
            await sysdb.webhook_dlq.update_one(
                {"id": dlq_id},
                {"$set": {"status": "pending", "last_error": result.get("error", "Retry başarısız")}},
            )
            return {"ok": False, "result": result}
    except Exception as exc:
        await sysdb.webhook_dlq.update_one(
            {"id": dlq_id},
            {"$set": {"status": "pending", "last_error": str(exc)}},
        )
        return {"ok": False, "error": str(exc)}
