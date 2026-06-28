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
from pymongo.errors import DuplicateKeyError

from core.tenant_db import get_db_for_tenant, get_system_db
from integrations.capx import (
    handle_match_cancelled,
    handle_match_created,
    record_counter_offer,
    resolve_credentials,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks/capx", tags=["CapX Webhook"])

COLLECTION = "capx_events"

# Idempotency: (event_id, direction=inbound) çifti benzersiz olmalı.
# Lazy + idempotent ensure — ilk çağrıda 1 kez kurulur, sonraki çağrılar
# Mongo'da OperationFailure (zaten var) yutulur. Bu, find_one+insert_one
# arasındaki race penceresini kapatır: insert_one DuplicateKeyError fırlatırsa
# duplicate path çalışır.
_INDEX_ENSURED: bool = False


async def _ensure_idempotency_index() -> None:
    global _INDEX_ENSURED
    if _INDEX_ENSURED:
        return
    try:
        sysdb = get_system_db()
        await sysdb[COLLECTION].create_index(
            [("event_id", 1), ("direction", 1)],
            name="uniq_event_id_direction",
            unique=True,
            partialFilterExpression={"event_id": {"$type": "string"}},
        )
        _INDEX_ENSURED = True
        logger.info("CapX webhook: idempotency unique index ensured")
    except Exception as exc:  # noqa: BLE001
        # Index varsa veya partial filter çakışması varsa sessizce geç.
        # Bir sonraki çağrıda tekrar denenir.
        logger.debug("capx_events index ensure skipped: %s", exc)


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
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
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


@router.post("/by-tenant/{tenant_id}", status_code=status.HTTP_200_OK)
async def capx_inbound_tenant(
    tenant_id: str,
    request: Request,
    x_capx_signature: str | None = Header(default=None, alias="X-CapX-Signature"),
    x_capx_event_id: str | None = Header(default=None, alias="X-CapX-Event-Id"),
    x_capx_event_type: str | None = Header(default=None, alias="X-CapX-Event-Type"),
) -> dict[str, Any]:
    """Tenant-aware inbound webhook.

    Spec PMS_INCELEME_RAPORU.md §1-5 referansı: callback URL formatı
    `{base}/api/webhooks/capx/by-tenant/{tenant_id}` — tenant_id path'ten
    okunur, secret ona göre çözülür. `match.created` ve `match.cancelled`
    event'leri için kullanılır.
    """
    body = await request.body()
    secret = await _resolve_secret(tenant_id)
    if not _verify(body, secret, x_capx_signature):
        logger.warning(
            "CapX inbound: invalid signature (event_id=%s tenant=%s type=%s)",
            x_capx_event_id,
            (tenant_id or "")[:8],
            x_capx_event_type,
        )
        raise HTTPException(status_code=401, detail="invalid signature")

    if not x_capx_event_id:
        raise HTTPException(status_code=400, detail="X-CapX-Event-Id header required")

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON body") from None

    event_type = x_capx_event_type or payload.get("event_type") or payload.get("type") or "unknown"

    sysdb = get_system_db()
    await _ensure_idempotency_index()

    log_doc = {
        "event_id": x_capx_event_id,
        "direction": "inbound",
        "event_type": event_type,
        "tenant_id": tenant_id,
        "payload": payload,
        "created_at": datetime.now(UTC),
        "status": "received",
    }
    # Atomic idempotency: insert_one önce; DuplicateKeyError → mevcut event,
    # find_one+insert_one race window'unu kapatır.
    try:
        await sysdb[COLLECTION].insert_one(log_doc)
    except DuplicateKeyError:
        existing = await sysdb[COLLECTION].find_one(
            {"event_id": x_capx_event_id, "direction": "inbound"},
            {"_id": 1, "handler_result": 1},
        )
        return {
            "ok": True,
            "duplicate": True,
            "received": True,
            "event_id": x_capx_event_id,
            "handler": (existing or {}).get("handler_result") or {},
        }

    handler_result: dict[str, Any] = {"handled": False, "kind": "log_only"}
    try:
        if event_type == "match.created":
            handler_result = await handle_match_created(
                tenant_id=tenant_id,
                payload=payload,
            )
        elif event_type == "match.cancelled":
            handler_result = await handle_match_cancelled(
                tenant_id=tenant_id,
                payload=payload,
            )
        elif event_type == "counter_offer":
            handler_result = await record_counter_offer(
                event_id=x_capx_event_id,
                payload=payload,
                tenant_id=tenant_id,
            )
        elif event_type == "rate_update":
            handler_result = await _handle_rate_update(
                {**payload, "tenant_id": tenant_id},
            )
    except Exception as exc:
        logger.exception(
            "CapX inbound handler error (type=%s, tenant=%s): %s",
            event_type,
            (tenant_id or "")[:8],
            exc,
        )
        # Spec §6 ack-with-error: 200 dön, retry tetikleme.
        handler_result = {"handled": False, "error": str(exc)}

    try:
        await sysdb[COLLECTION].update_one(
            {"event_id": x_capx_event_id, "direction": "inbound"},
            {"$set": {"status": "processed", "handler_result": handler_result}},
        )
    except Exception:
        logger.exception("CapX inbound log update failed (non-fatal)")

    logger.info(
        "CapX inbound (tenant): type=%s event_id=%s tenant=%s action=%s",
        event_type,
        x_capx_event_id,
        (tenant_id or "")[:8],
        handler_result.get("action") or handler_result.get("kind") or "?",
    )

    return {
        "ok": True,
        "received": True,
        "event_id": x_capx_event_id,
        "event_type": event_type,
        "handler": handler_result,
    }


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
        logger.warning("CapX webhook: invalid signature (event_id=%s tenant=%s)", x_capx_event_id, (tenant_id_hint or "")[:8])
        raise HTTPException(status_code=401, detail="invalid signature")

    if not x_capx_event_id:
        raise HTTPException(status_code=400, detail="X-CapX-Event-Id header required")

    payload = payload_peek if payload_peek else {}
    if not payload and body:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    sysdb = get_system_db()
    await _ensure_idempotency_index()

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
    try:
        await sysdb[COLLECTION].insert_one(log_doc)
    except DuplicateKeyError:
        return {"ok": True, "duplicate": True, "event_id": x_capx_event_id}

    # ── Event-type dispatch ───────────────────────────────────────
    handler_result: dict[str, Any] = {}
    try:
        if event_type == "counter_offer":
            handler_result = await record_counter_offer(
                event_id=x_capx_event_id,
                payload=payload,
                tenant_id=tenant_id,
            )
        elif event_type == "rate_update":
            handler_result = await _handle_rate_update(payload)
        else:
            handler_result = {"handled": False, "kind": "log_only"}
    except Exception as exc:
        logger.exception("CapX inbound handler error (type=%s): %s", event_type, exc)
        handler_result = {"error": str(exc)}

    logger.info("CapX inbound event: type=%s event_id=%s tenant=%s", event_type, x_capx_event_id, (tenant_id or "")[:8])

    return {
        "ok": True,
        "event_id": x_capx_event_id,
        "event_type": event_type,
        "handler": handler_result,
    }
