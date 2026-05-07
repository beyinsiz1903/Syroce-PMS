"""
Meta WhatsApp Business Cloud API — Inbound Webhook.

Endpoints (public, no auth):
  GET  /api/whatsapp/webhook   → Meta verification handshake
  POST /api/whatsapp/webhook   → Inbound message + status callbacks

Tenant resolution: payload includes
  entry[].changes[].value.metadata.phone_number_id
which is matched against
  messaging_provider_configs.credentials_encrypted.phone_number_id
to find the owning tenant.

Security:
  - GET endpoint validates `hub.verify_token` against per-tenant
    `webhook_verify_token` stored in the provider config; fails closed
    if no tenant matches.
  - POST endpoint verifies `X-Hub-Signature-256` HMAC-SHA256 of the raw
    body against per-tenant `app_secret`. If `app_secret` is not
    configured for a tenant, signature check is skipped (logged as
    warning). Production must always set app_secret.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response

from modules.messaging.models import ConsentStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp", tags=["WhatsApp Webhook"])


def _get_db():
    from server import db
    return db


async def _find_config_by_phone_id(phone_number_id: str) -> dict | None:
    """Return the active whatsapp provider config that owns this phone_number_id."""
    if not phone_number_id:
        return None
    db = _get_db()
    return await db.messaging_provider_configs.find_one(
        {
            "provider_type": "whatsapp",
            "enabled": True,
            "credentials_encrypted.phone_number_id": phone_number_id,
        },
        {"_id": 0},
    )


async def _find_config_by_verify_token(token: str) -> dict | None:
    if not token:
        return None
    db = _get_db()
    return await db.messaging_provider_configs.find_one(
        {
            "provider_type": "whatsapp",
            "enabled": True,
            "credentials_encrypted.webhook_verify_token": token,
        },
        {"_id": 0},
    )


def _verify_signature(raw_body: bytes, signature_header: str, app_secret: str) -> bool:
    if not signature_header or not app_secret:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = signature_header.split("=", 1)[1]
    digest = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, digest)


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
):
    """Meta verification handshake.

    Meta sends GET with `hub.mode=subscribe`, `hub.verify_token`, `hub.challenge`.
    We must echo `hub.challenge` if the verify token matches an active tenant.
    """
    if hub_mode != "subscribe":
        raise HTTPException(status_code=400, detail="invalid hub.mode")

    cfg = await _find_config_by_verify_token(hub_verify_token)
    if not cfg:
        logger.warning("WhatsApp webhook verify failed: token mismatch")
        raise HTTPException(status_code=403, detail="verify token mismatch")

    logger.info(
        "WhatsApp webhook verified for tenant=%s",
        cfg.get("tenant_id", "?"),
    )
    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/webhook")
async def receive_webhook(request: Request) -> dict[str, Any]:
    """Receive inbound messages and delivery status callbacks.

    Returns 200 quickly — Meta will retry for 24h if we return non-2xx.
    Failures must NOT raise; we log + 200 to avoid retry storms.
    """
    raw_body = await request.body()
    try:
        payload = await request.json()
    except Exception:
        logger.warning("WhatsApp webhook: invalid JSON body")
        return {"received": True}

    signature = request.headers.get("x-hub-signature-256", "")

    db = _get_db()
    processed = 0

    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            phone_number_id = (
                value.get("metadata", {}).get("phone_number_id", "") or ""
            )
            cfg = await _find_config_by_phone_id(phone_number_id)
            if not cfg:
                logger.warning(
                    "WhatsApp webhook: no tenant for phone_number_id=%s",
                    phone_number_id,
                )
                continue

            tenant_id = cfg.get("tenant_id")
            creds = cfg.get("credentials_encrypted", {}) or {}
            app_secret = creds.get("app_secret", "")
            is_sandbox = bool(cfg.get("is_sandbox"))

            # Fail-closed: production (non-sandbox) MUST have app_secret + valid signature.
            # Sandbox modunda Meta test araçları imza göndermeyebilir, sadece warning.
            if not app_secret:
                if is_sandbox:
                    logger.warning(
                        "WhatsApp webhook (sandbox): app_secret not set for tenant=%s — "
                        "accepting unsigned payload (DO NOT use in production)",
                        tenant_id,
                    )
                else:
                    logger.error(
                        "WhatsApp webhook: app_secret not set for tenant=%s in LIVE mode — "
                        "rejecting payload (set app_secret to enable inbound)",
                        tenant_id,
                    )
                    continue
            elif not _verify_signature(raw_body, signature, app_secret):
                logger.warning(
                    "WhatsApp webhook: signature mismatch for tenant=%s",
                    tenant_id,
                )
                continue

            now_iso = datetime.now(UTC).isoformat()

            # 1) Inbound text/media messages — idempotent upsert by (tenant_id, wa_message_id)
            for msg in value.get("messages", []) or []:
                wa_msg_id = msg.get("id", "")
                if not wa_msg_id:
                    logger.warning("WhatsApp inbound: missing message id; skipping")
                    continue
                doc = {
                    "tenant_id": tenant_id,
                    "provider_type": "whatsapp",
                    "direction": "inbound",
                    "wa_message_id": wa_msg_id,
                    "from": msg.get("from", ""),
                    "timestamp": msg.get("timestamp", ""),
                    "type": msg.get("type", ""),
                    "text": (msg.get("text") or {}).get("body", ""),
                    "raw": msg,
                    "phone_number_id": phone_number_id,
                }
                try:
                    res = await db.wa_inbound_messages.update_one(
                        {"tenant_id": tenant_id, "wa_message_id": wa_msg_id},
                        {
                            "$set": doc,
                            "$setOnInsert": {"received_at": now_iso},
                        },
                        upsert=True,
                    )
                    # Sadece yeni eklenen mesajları say (Meta retry'da tekrar sayma)
                    if res.upserted_id is not None:
                        processed += 1
                except Exception:
                    logger.exception("WhatsApp inbound upsert failed")

                # Auto opt-in: kullanıcı yazdıysa pencere açıldı + onay verilmiş sayılır
                try:
                    await db.messaging_consents.update_one(
                        {
                            "tenant_id": tenant_id,
                            "recipient": msg.get("from", ""),
                            "channel": "whatsapp",
                        },
                        {
                            "$set": {
                                "tenant_id": tenant_id,
                                "recipient": msg.get("from", ""),
                                "channel": "whatsapp",
                                "status": ConsentStatus.OPT_IN.value,
                                "source": "wa_inbound",
                                "updated_at": now_iso,
                            },
                            "$setOnInsert": {"created_at": now_iso},
                        },
                        upsert=True,
                    )
                except Exception:
                    logger.exception("WhatsApp consent upsert failed")

            # 2) Status callbacks (sent → delivered → read → failed)
            for st in value.get("statuses", []) or []:
                wa_msg_id = st.get("id", "")
                status = st.get("status", "")
                if not wa_msg_id or not status:
                    continue
                update_doc: dict[str, Any] = {
                    "status": status,
                    "updated_at": now_iso,
                }
                if status == "delivered":
                    update_doc["delivered_at"] = now_iso
                if status == "failed":
                    errors = st.get("errors", []) or []
                    if errors:
                        first = errors[0] or {}
                        update_doc["error_message"] = (
                            first.get("title") or first.get("message") or ""
                        )[:500]
                try:
                    await db.messaging_delivery_logs.update_one(
                        {
                            "tenant_id": tenant_id,
                            "provider_message_id": wa_msg_id,
                        },
                        {"$set": update_doc},
                    )
                    processed += 1
                except Exception:
                    logger.exception("WhatsApp status update failed")

    return {"received": True, "processed": processed}
