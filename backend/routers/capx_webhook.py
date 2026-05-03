"""CapX → Syroce webhook callback receiver.

Public endpoint (JWT yok). HMAC SHA-256 verify zorunlu.
Header: X-CapX-Signature: sha256=<hex>, X-CapX-Event-Id: <uuid>
Body: raw JSON.

Idempotency: aynı X-CapX-Event-Id ikinci defa gelirse 200 + "duplicate" döner.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

from core.database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks/capx", tags=["CapX Webhook"])

COLLECTION = "capx_events"


def _verify_signature(body: bytes, signature: str | None) -> bool:
    secret = os.getenv("CAPX_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("", status_code=status.HTTP_200_OK)
async def capx_inbound(
    request: Request,
    x_capx_signature: str | None = Header(default=None, alias="X-CapX-Signature"),
    x_capx_event_id: str | None = Header(default=None, alias="X-CapX-Event-Id"),
) -> dict[str, Any]:
    body = await request.body()

    if not _verify_signature(body, x_capx_signature):
        logger.warning("CapX webhook: invalid signature (event_id=%s)", x_capx_event_id)
        raise HTTPException(status_code=401, detail="invalid signature")

    if not x_capx_event_id:
        raise HTTPException(status_code=400, detail="X-CapX-Event-Id header required")

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    # Idempotency check
    existing = await db[COLLECTION].find_one(
        {"event_id": x_capx_event_id, "direction": "inbound"},
        {"_id": 1},
    )
    if existing:
        return {"ok": True, "duplicate": True, "event_id": x_capx_event_id}

    event_type = payload.get("event_type") or payload.get("type") or "unknown"

    log_doc = {
        "event_id": x_capx_event_id,
        "direction": "inbound",
        "event_type": event_type,
        "payload": payload,
        "created_at": datetime.now(UTC),
        "status": "received",
    }
    await db[COLLECTION].insert_one(log_doc)

    # Asıl olay işleyici (extensible) — şimdilik sadece log + ack.
    # CapX tarafından beklenen event'ler: counter_offer, booking_confirmed,
    # rate_update, channel_status. Her biri için handler eklenebilir.
    logger.info("CapX inbound event received: type=%s event_id=%s",
                event_type, x_capx_event_id)

    return {"ok": True, "event_id": x_capx_event_id, "event_type": event_type}
