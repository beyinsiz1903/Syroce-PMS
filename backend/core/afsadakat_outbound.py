"""
Af-sadakat Outbound Event Dispatcher
─────────────────────────────────────
Syroce → Af-sadakat olay yayını için özel modül.

İşleyiş:
1. `emit_event(tenant_id, event_type, payload)` çağrılır → olay
   `db.integration_afsadakat_outbox` koleksiyonuna `status=pending` ile yazılır.
2. Aynı çağrıda fire-and-forget tek bir teslim denemesi başlatılır.
3. Başarısız olanlar için periyodik `dispatch_pending_loop()` görevi
   exponential backoff ile yeniden dener (max 5 deneme).

İmza: HMAC-SHA256(per-tenant pms_api_key, raw_body) →
`X-Syroce-Signature: sha256=<hex>` header'ı.

Yerel modda (AFSADAKAT_BASE_URL set değil) `emit_event` sessizce no-op.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/api/integrations/syroce/webhook"
SIGNATURE_HEADER = "X-Syroce-Signature"
EVENT_HEADER = "X-Syroce-Event"
DELIVERY_HEADER = "X-Syroce-Delivery"

MAX_ATTEMPTS = 5
HTTP_TIMEOUT_S = 15.0
# Exponential backoff (saniye): 30s, 2dk, 8dk, 30dk, 2sa
_BACKOFF_S = [30, 120, 480, 1800, 7200]


def _now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _now().isoformat()


def _is_external_configured() -> bool:
    return bool(
        os.environ.get("AFSADAKAT_BASE_URL")
        and os.environ.get("AFSADAKAT_ADMIN_TOKEN")
    )


async def _get_tenant_creds(tenant_id: str) -> dict[str, Any] | None:
    """Tenant'ın Af-sadakat kayıt dokümanı (pms_api_key + ext_tenant_id)."""
    return await db.integration_afsadakat_tenants.find_one(
        {"tenant_id": tenant_id, "status": "active"}, {"_id": 0}
    )


def _sign(api_key: str, body: bytes) -> str:
    """HMAC-SHA256(api_key, body) hex digest."""
    digest = hmac.new(api_key.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


# ── Public API ──────────────────────────────────────────────────────────────

async def emit_event(
    tenant_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> str | None:
    """Af-sadakat'a olay yay (outbox + fire-and-forget teslim).

    AFSADAKAT_BASE_URL set değilse veya tenant Af-sadakat'a kayıtlı değilse
    sessizce no-op döner (None). Hatada bile çağrı yerinin akışını
    bozmaz; başarısız olay outbox'ta `status=pending` kalır ve
    dispatcher loop tarafından yeniden denenir.

    Returns: outbox event_id (yazıldıysa) veya None.
    """
    try:
        if not _is_external_configured():
            return None
        creds = await _get_tenant_creds(tenant_id)
        if not creds or not creds.get("api_key"):
            return None  # local-only mode

        event_id = str(uuid.uuid4())
        doc = {
            "id": event_id,
            "tenant_id": tenant_id,
            "ext_tenant_id": creds.get("ext_tenant_id"),
            "event_type": event_type,
            "payload": payload,
            "status": "pending",
            "attempts": 0,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "next_attempt_at": _now_iso(),
            "last_error": None,
        }
        await db.integration_afsadakat_outbox.insert_one(doc)

        # Fire-and-forget: aynı request'i bekletmeden ilk teslim denemesi
        asyncio.create_task(_try_deliver(event_id))
        return event_id
    except Exception as exc:  # outbound asla iş akışını bozmamalı
        logger.warning("[afsadakat-out] emit failed tenant=%s type=%s err=%s",
                       tenant_id, event_type, exc)
        return None


# ── Delivery ────────────────────────────────────────────────────────────────

async def _try_deliver(event_id: str) -> bool:
    """Tek bir olay için teslim denemesi. Sonuç başarısızsa outbox'ta kalır.

    Atomik claim (pending → processing) ile aynı anda iki worker'ın
    aynı olayı POST etmesini önler.
    """
    evt: dict[str, Any] | None = None
    try:
        # Atomik claim: yalnızca pending olan event'i processing'e çek
        claimed = await db.integration_afsadakat_outbox.find_one_and_update(
            {"id": event_id, "status": "pending"},
            {"$set": {"status": "processing", "updated_at": _now_iso()}},
            return_document=False,  # eski belgeyi döndür (claim başarılı mı?)
        )
        if not claimed:
            # Başka worker zaten alıyor veya event sent/failed
            return True

        evt = await db.integration_afsadakat_outbox.find_one(
            {"id": event_id}, {"_id": 0}
        )
        if not evt:
            return True

        creds = await _get_tenant_creds(evt["tenant_id"])
        base_url = (creds or {}).get("base_url") or os.environ.get("AFSADAKAT_BASE_URL")
        api_key = (creds or {}).get("api_key")
        if not base_url or not api_key:
            # Konfigürasyon eksik — failed olarak işaretle (sonsuz pending bırakma)
            await db.integration_afsadakat_outbox.update_one(
                {"id": event_id},
                {"$set": {
                    "status": "failed",
                    "last_error": "missing creds or AFSADAKAT_BASE_URL",
                    "updated_at": _now_iso(),
                }},
            )
            return False

        body = {
            "event_id": evt["id"],
            "event_type": evt["event_type"],
            "tenant_id": evt["tenant_id"],
            "ext_tenant_id": evt.get("ext_tenant_id"),
            "occurred_at": evt["created_at"],
            "payload": evt["payload"],
        }
        raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        signature = _sign(api_key, raw)

        url = f"{base_url.rstrip('/')}{WEBHOOK_PATH}"
        headers = {
            "Content-Type": "application/json",
            SIGNATURE_HEADER: signature,
            EVENT_HEADER: evt["event_type"],
            DELIVERY_HEADER: evt["id"],
        }

        # v109 Bug DAL round-7 follow-up #5: base_url comes from tenant
        # creds (`creds.base_url`) and is therefore tenant-configurable.
        # Use rebinding-safe transport. EgressDenied → mark failed (caller
        # already maps non-2xx into retry/fail outbox state).
        from integrations.xchange.safety import EgressDenied, safe_post_async
        try:
            r = await safe_post_async(url, timeout=HTTP_TIMEOUT_S, content=raw, headers=headers)
        except EgressDenied as _ed:
            await db.integration_afsadakat_outbox.update_one(
                {"id": event_id},
                {"$set": {
                    "status": "failed",
                    "last_error": f"egress_denied: {_ed}",
                    "updated_at": _now_iso(),
                }},
            )
            return False

        # 2xx → sent, 4xx (klient hatası) → failed (kalıcı), diğer → retry
        if 200 <= r.status_code < 300:
            await db.integration_afsadakat_outbox.update_one(
                {"id": event_id},
                {"$set": {
                    "status": "sent",
                    "delivered_at": _now_iso(),
                    "response_status": r.status_code,
                    "updated_at": _now_iso(),
                }},
            )
            return True

        attempts = evt.get("attempts", 0) + 1
        is_client_err = 400 <= r.status_code < 500 and r.status_code not in (408, 429)
        new_status = "failed" if (is_client_err or attempts >= MAX_ATTEMPTS) else "pending"
        backoff = _BACKOFF_S[min(attempts - 1, len(_BACKOFF_S) - 1)]
        await db.integration_afsadakat_outbox.update_one(
            {"id": event_id},
            {"$set": {
                "status": new_status,
                "attempts": attempts,
                "last_error": f"HTTP {r.status_code}: {r.text[:200]}",
                "response_status": r.status_code,
                "next_attempt_at": (_now() + timedelta(seconds=backoff)).isoformat(),
                "updated_at": _now_iso(),
            }},
        )
        return False
    except Exception as exc:
        attempts = (evt.get("attempts", 0) if evt else 0) + 1  # noqa: F821
        backoff = _BACKOFF_S[min(attempts - 1, len(_BACKOFF_S) - 1)]
        await db.integration_afsadakat_outbox.update_one(
            {"id": event_id},
            {"$set": {
                "status": "failed" if attempts >= MAX_ATTEMPTS else "pending",
                "attempts": attempts,
                "last_error": str(exc)[:300],
                "next_attempt_at": (_now() + timedelta(seconds=backoff)).isoformat(),
                "updated_at": _now_iso(),
            }},
        )
        logger.warning("[afsadakat-out] delivery failed event=%s err=%s",
                       event_id, exc)
        return False


# ── Background dispatcher loop ──────────────────────────────────────────────

_DISPATCHER_INTERVAL_S = 60  # her dakika pending event'leri tara


async def dispatch_pending_loop() -> None:
    """Pending/failed (retryable) olayları periyodik olarak yeniden dener."""
    logger.info("[afsadakat-out] dispatcher loop started")
    while True:
        try:
            if _is_external_configured():
                now_iso = _now_iso()
                cursor = db.integration_afsadakat_outbox.find(
                    {
                        "status": "pending",
                        "next_attempt_at": {"$lte": now_iso},
                        "attempts": {"$lt": MAX_ATTEMPTS},
                    },
                    {"id": 1, "_id": 0},
                ).limit(50)
                ids = [d["id"] async for d in cursor]
                for evt_id in ids:
                    await _try_deliver(evt_id)
        except Exception as exc:
            logger.warning("[afsadakat-out] dispatcher tick err: %s", exc)
        await asyncio.sleep(_DISPATCHER_INTERVAL_S)


# ── Convenience constants for event types ───────────────────────────────────

EV_RESERVATION_CREATED = "reservation.created"
EV_RESERVATION_UPDATED = "reservation.updated"
EV_RESERVATION_CANCELLED = "reservation.cancelled"
EV_GUEST_CHECKED_OUT = "guest.checked_out"
