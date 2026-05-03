"""CapX → Syroce webhook callback receiver.

Public endpoint (JWT yok). HMAC SHA-256 verify zorunlu.
Header: X-CapX-Signature: sha256=<hex>, X-CapX-Event-Id: <uuid>
Body: raw JSON.

Idempotency: aynı X-CapX-Event-Id ikinci defa gelirse 200 + "duplicate" döner.

Faz 3 — handler tablosu:
  counter_offer  → capx_counter_offers koleksiyonuna kaydet (state=pending)
  rate_update    → rate_plans koleksiyonunda ilgili room_type'ı güncelle
  diğer          → log + ack

Per-tenant signature: payload.tenant_id varsa o tenant'ın webhook_secret'ı
ile imza doğrulanır. Yoksa env CAPX_WEBHOOK_SECRET fallback.
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

from core.tenant_db import get_db_for_tenant, get_system_db
from integrations.capx import record_counter_offer, resolve_credentials

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks/capx", tags=["CapX Webhook"])

COLLECTION = "capx_events"


async def _resolve_secret(payload_tenant_id: str | None) -> str:
    """Önce payload'dan tenant_id varsa o tenant'ın secret'ı, yoksa env fallback."""
    if payload_tenant_id:
        try:
            creds = await resolve_credentials(payload_tenant_id)
            if creds.source == "tenant" and creds.webhook_secret:
                return creds.webhook_secret
        except Exception as exc:  # pragma: no cover
            logger.warning("tenant secret lookup failed: %s", exc)
    return os.getenv("CAPX_WEBHOOK_SECRET", "")


def _verify(body: bytes, secret: str, signature: str | None) -> bool:
    if not secret or not signature:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _handle_rate_update(payload: dict[str, Any]) -> dict[str, Any]:
    """CapX → otele rate güncelleme bildirimi.

    payload örnek:
      {"event_type":"rate_update","tenant_id":"...","room_type":"DBL_STD",
       "rates":[{"date":"2026-05-10","price":2900,"currency":"TRY"}, ...]}

    Best-effort: rate_plans'ta upsert, hata yutulur.
    """
    tenant_id = payload.get("tenant_id")
    room_type = payload.get("room_type")
    rates = payload.get("rates") or []
    if not tenant_id or not room_type:
        return {"updated": 0, "reason": "tenant_id/room_type missing"}

    updated = 0
    tdb = get_db_for_tenant(tenant_id)
    for r in rates:
        try:
            res = await tdb.rate_plans.update_one(
                {"room_type": room_type, "date": r.get("date")},
                {
                    "$set": {
                        "base_rate": r.get("price"),
                        "currency": r.get("currency", "TRY"),
                        "source": "capx",
                        "updated_at": datetime.now(UTC).isoformat(),
                    }
                },
                upsert=True,
            )
            if res.modified_count or res.upserted_id:
                updated += 1
        except Exception as exc:  # pragma: no cover
            logger.warning("rate_update apply failed: %s", exc)
    return {"updated": updated, "total_rates": len(rates)}


@router.post("", status_code=status.HTTP_200_OK)
async def capx_inbound(
    request: Request,
    x_capx_signature: str | None = Header(default=None, alias="X-CapX-Signature"),
    x_capx_event_id: str | None = Header(default=None, alias="X-CapX-Event-Id"),
) -> dict[str, Any]:
    body = await request.body()

    # Per-tenant signature: payload'dan tenant_id'yi peek et (verify öncesi).
    # Bu okumanın güvenliği yok ama secret lookup için gerekli.
    payload_peek: dict[str, Any] = {}
    try:
        payload_peek = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload_peek = {}

    tenant_id_hint = payload_peek.get("tenant_id")
    secret = await _resolve_secret(tenant_id_hint)
    if not _verify(body, secret, x_capx_signature):
        logger.warning("CapX webhook: invalid signature (event_id=%s tenant=%s)",
                       x_capx_event_id, (tenant_id_hint or "")[:8])
        raise HTTPException(status_code=401, detail="invalid signature")

    if not x_capx_event_id:
        raise HTTPException(status_code=400, detail="X-CapX-Event-Id header required")

    payload = payload_peek if payload_peek else {}
    if not payload and body:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    sysdb = get_system_db()
    existing = await sysdb[COLLECTION].find_one(
        {"event_id": x_capx_event_id, "direction": "inbound"},
        {"_id": 1},
    )
    if existing:
        return {"ok": True, "duplicate": True, "event_id": x_capx_event_id}

    event_type = payload.get("event_type") or payload.get("type") or "unknown"
    tenant_id = payload.get("tenant_id")

    log_doc = {
        "event_id": x_capx_event_id,
        "direction": "inbound",
        "event_type": event_type,
        "tenant_id": tenant_id,
        "payload": payload,
        "created_at": datetime.now(UTC),
        "status": "received",
    }
    await sysdb[COLLECTION].insert_one(log_doc)

    # ── Event-type dispatch ───────────────────────────────────────
    handler_result: dict[str, Any] = {}
    try:
        if event_type == "counter_offer":
            handler_result = await record_counter_offer(
                event_id=x_capx_event_id, payload=payload, tenant_id=tenant_id,
            )
        elif event_type == "rate_update":
            handler_result = await _handle_rate_update(payload)
        else:
            handler_result = {"handled": False, "kind": "log_only"}
    except Exception as exc:
        logger.exception("CapX inbound handler error (type=%s): %s", event_type, exc)
        handler_result = {"error": str(exc)}

    logger.info("CapX inbound event: type=%s event_id=%s tenant=%s",
                event_type, x_capx_event_id, (tenant_id or "")[:8])

    return {
        "ok": True,
        "event_id": x_capx_event_id,
        "event_type": event_type,
        "handler": handler_result,
    }
