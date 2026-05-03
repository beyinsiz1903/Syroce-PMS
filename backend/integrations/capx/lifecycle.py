"""CapX booking lifecycle helper — best-effort fire-and-forget push.

create_reservation_service ve update_reservation_service tarafından
asyncio.create_task ile çağrılır. Hata yutulur (af-sadakat pattern'i ile aynı).
Idempotency: event_id = booking_id + status hash → tekrarlı çağrılarda CapX
tarafında aynı event tek sefer işlenir.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db
from integrations.capx import CapXError, get_capx_client

logger = logging.getLogger(__name__)

# Map Syroce booking statüsü → CapX event_type
_STATUS_TO_EVENT = {
    "confirmed": "created",
    "guaranteed": "created",
    "checked_in": None,    # CapX bunu beklemiyor
    "checked_out": None,
    "cancelled": "cancelled",
    "no_show": "no_show",
}


def _idempotent_event_id(booking_id: str, event_type: str) -> str:
    """Sabit event_id: aynı booking + aynı event yeniden push edilirse CapX
    duplicate algılar. UUID4 yerine deterministic hash kullanıyoruz."""
    raw = f"capx:{booking_id}:{event_type}".encode()
    return hashlib.sha256(raw).hexdigest()[:32]


async def push_booking_lifecycle_event(
    *, booking_id: str, status: str, tenant_id: str,
    guest_name: str | None = None, check_in: str = "", check_out: str = "",
    amount: float | None = None, currency: str = "TRY",
    pms_external_ref: str | None = None,
) -> None:
    """Best-effort: CapX'e booking event push. Hata yutulur.

    Çağrı yeri: create_reservation_service (status=confirmed/guaranteed),
    update_reservation_service (status=cancelled/no_show transition).
    """
    event_type = _STATUS_TO_EVENT.get(status)
    if not event_type:
        return

    client = get_capx_client(refresh=False)
    if not client.configured or not client.webhook_secret:
        # CapX hiç yapılandırılmamış — sessizce çık (operasyona zarar yok)
        return

    body: dict[str, Any] = {
        "event_type": event_type,
        "pms_external_ref": pms_external_ref or f"syroce-booking-{booking_id}",
        "booking_id": booking_id,
        "check_in": check_in,
        "check_out": check_out,
        "currency": currency,
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    if guest_name:
        body["guest_name"] = guest_name
    if amount is not None:
        body["amount"] = amount

    event_id = _idempotent_event_id(booking_id, event_type)

    # Local event log — debugging + retry için trail
    log_doc = {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "event_type": event_type,
        "direction": "outbound",
        "created_at": datetime.now(UTC),
    }

    try:
        resp = await client.push_reservation_event(body, event_id=event_id)
        log_doc["status"] = "ok"
        log_doc["response"] = resp
    except CapXError as exc:
        log_doc["status"] = "error"
        log_doc["error"] = str(exc)
        log_doc["status_code"] = exc.status_code
        logger.warning("CapX lifecycle push failed for booking=%s: %s", booking_id, exc)
    except Exception as exc:  # noqa: BLE001
        log_doc["status"] = "error"
        log_doc["error"] = f"unexpected: {exc}"
        logger.warning("CapX lifecycle push unexpected for booking=%s: %s", booking_id, exc)

    try:
        await db["capx_events"].insert_one(log_doc)
    except Exception:
        logger.exception("CapX event log insert failed (non-fatal)")


def fire_and_forget(coro) -> None:
    """create_task wrapper — exception swallowed, log only."""
    task = asyncio.create_task(coro)

    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.warning("CapX fire-and-forget task error: %s", exc)

    task.add_done_callback(_on_done)
