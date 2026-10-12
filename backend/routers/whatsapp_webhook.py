"""
Meta WhatsApp Business Cloud API — Inbound Webhook.

Endpoints (public, no auth):
  GET  /api/messaging-center/whatsapp/webhook   → Meta verification handshake
  POST /api/messaging-center/whatsapp/webhook   → Inbound message + status callbacks

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
  body against the per-tenant `app_secret`. A missing secret is rejected in
    every mode: a sandbox endpoint must never become an unsigned backdoor.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response

from domains.contact_center.whatsapp_ingest import (
    ingest_whatsapp_inbound,
    sync_whatsapp_status,
)
from modules.messaging.models import ConsentStatus
from modules.messaging.recipient_crypto import seal_recipient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WhatsApp Webhook"])


def _get_db():
    """Use the explicit system view: webhook tenant resolution precedes auth."""
    from core.tenant_db import get_system_db

    return get_system_db()


async def _find_config_by_phone_id(phone_number_id: str) -> dict | None:
    """Return the active whatsapp provider config that owns this phone_number_id."""
    if not phone_number_id:
        return None
    db = _get_db()
    matches = await db.messaging_provider_configs.find(
        {
            "provider_type": "whatsapp",
            "enabled": True,
            "credentials_encrypted.phone_number_id": phone_number_id,
        },
        {"_id": 0},
    ).limit(2).to_list(2)
    return matches[0] if len(matches) == 1 else None


async def _find_config_by_verify_token(token: str) -> dict | None:
    """Look up an encrypted verify token without querying its ciphertext.

    Field encryption intentionally makes equal plaintext values have unrelated
    ciphertext.  Querying ``credentials_encrypted.webhook_verify_token`` would
    therefore fail after credentials are encrypted at rest.  This endpoint is
    called only during Meta's rare setup handshake, so a bounded scan of active
    WhatsApp configurations is both safe and operationally inexpensive.
    """
    if not token:
        return None
    db = _get_db()
    from modules.messaging.service import _decrypt_provider_creds

    configs = db.messaging_provider_configs.find(
        {"provider_type": "whatsapp", "enabled": True}, {"_id": 0}
    )
    async for cfg in configs:
        creds = _decrypt_provider_creds(
            cfg.get("credentials_encrypted", {}) or {}, "whatsapp"
        )
        if hmac.compare_digest(str(creds.get("webhook_verify_token", "")), token):
            return cfg
    return None


def _credentials(config: dict) -> dict:
    """Decrypt provider credentials only at the authenticated runtime boundary."""
    from modules.messaging.service import _decrypt_provider_creds

    return _decrypt_provider_creds(
        config.get("credentials_encrypted", {}) or {}, "whatsapp"
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


@router.get("/api/whatsapp/webhook", include_in_schema=False)
@router.get("/api/messaging-center/whatsapp/webhook")
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


@router.post("/api/whatsapp/webhook", include_in_schema=False)
@router.post("/api/messaging-center/whatsapp/webhook")
async def receive_webhook(request: Request) -> dict[str, Any]:
    """Receive inbound messages and delivery status callbacks.

    Authenticate before writes. Return 503 on persistence failures so Meta retries.
    """
    raw_body = await request.body()
    try:
        payload = await request.json()
    except Exception:
        logger.warning("WhatsApp webhook: invalid JSON body")
        raise HTTPException(400, "Invalid JSON")

    signature = request.headers.get("x-hub-signature-256", "")

    db = _get_db()
    processed = 0

    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            phone_number_id = value.get("metadata", {}).get("phone_number_id", "") or ""
            cfg = await _find_config_by_phone_id(phone_number_id)
            if not cfg:
                logger.warning(
                    "WhatsApp webhook: no tenant for phone_number_id=%s",
                    phone_number_id,
                )
                continue

            tenant_id = cfg.get("tenant_id")
            creds = _credentials(cfg)
            app_secret = creds.get("app_secret", "")

            # Fail closed in every mode.  Sandbox is a transport choice, not a
            # trust-boundary bypass: accepting unsigned payloads lets anyone
            # create guest conversations and consent records.
            if not app_secret:
                logger.error(
                    "WhatsApp webhook: app_secret not configured for tenant=%s; rejecting payload",
                    tenant_id,
                )
                raise HTTPException(403, "Webhook signature required")
            if not _verify_signature(raw_body, signature, app_secret):
                logger.warning(
                    "WhatsApp webhook: signature mismatch for tenant=%s",
                    tenant_id,
                )
                raise HTTPException(403, "Invalid webhook signature")

            now_iso = datetime.now(UTC).isoformat()

            # Meta contacts[]: wa_id -> profile.name (görünen ad; Contact Center
            # köprüsünde şifrelenir, burada persist EDİLMEZ).
            contacts_map: dict[str, str] = {}
            for c in value.get("contacts", []) or []:
                wa_id = c.get("wa_id", "")
                name = (c.get("profile") or {}).get("name", "")
                if wa_id and name:
                    contacts_map[wa_id] = name

            # 1) Inbound text/media messages — idempotent upsert by (tenant_id, wa_message_id)
            for msg in value.get("messages", []) or []:
                wa_msg_id = msg.get("id", "")
                if not wa_msg_id:
                    logger.warning("WhatsApp inbound: missing message id; skipping")
                    continue
                # PII sertleştirme: açık-metin gönderen/gövde/ham yük artık
                # wa_inbound_messages'a YAZILMAZ (bu alanların tüketicisi yok).
                # Şifreli kopyalar Contact Center köprüsünde tutulur.
                doc = {
                    "tenant_id": tenant_id,
                    "provider_type": "whatsapp",
                    "direction": "inbound",
                    "wa_message_id": wa_msg_id,
                    "timestamp": msg.get("timestamp", ""),
                    "type": msg.get("type", ""),
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
                    # Retry idempotent downstream ingestion after partial failure.
                    processed += 1
                except Exception:
                    logger.exception("WhatsApp inbound upsert failed")
                    raise HTTPException(503, "Inbound persistence unavailable") from None

                # Incoming messages open a reply window, NOT business-message consent.
                # PII-at-rest: gönderen telefonu plaintext yazılmaz; recipient_enc
                # (şifreli) + recipient_hash (HMAC blind-index) saklanır, doküman
                # tekilliği recipient_hash üzerinden kurulur.
                try:
                    inbound_at = min(datetime.fromtimestamp(int(msg.get("timestamp", 0)), UTC), datetime.now(UTC)).isoformat()
                except (ValueError, TypeError, OverflowError, OSError):
                    raise HTTPException(400, "Invalid message timestamp") from None
                sender = msg.get("from", "")
                if sender:
                    try:
                        sealed = seal_recipient(sender)
                        s_hash = sealed.get("recipient_hash", "")
                        # Match by blind-index OR legacy plaintext recipient and
                        # migrate in place ($unset plaintext) so an inbound never
                        # creates a SECOND consent row for a recipient that still
                        # has a pre-backfill legacy row.
                        res = await db.messaging_consents.update_one(
                            {
                                "tenant_id": tenant_id,
                                "channel": "whatsapp",
                                "$or": [
                                    {"recipient_hash": s_hash},
                                    {"recipient": sender},
                                ],
                            },
                            {
                                "$set": {
                                    "tenant_id": tenant_id,
                                    "recipient_enc": sealed.get("recipient_enc"),
                                    "recipient_hash": s_hash,
                                    "channel": "whatsapp",
                                    "updated_at": now_iso,
                                },
                                "$max": {"last_inbound_at": inbound_at},
                                "$unset": {"recipient": ""},
                            },
                        )
                        if res.matched_count == 0:
                            await db.messaging_consents.insert_one(
                                {
                                    "tenant_id": tenant_id,
                                    "channel": "whatsapp",
                                    "recipient_hash": s_hash,
                                    "recipient_enc": sealed.get("recipient_enc"),
                                    "status": ConsentStatus.PENDING.value,
                                    "source": "wa_inbound",
                                    "last_inbound_at": inbound_at,
                                    "created_at": now_iso,
                                    "updated_at": now_iso,
                                }
                            )
                    except Exception:
                        logger.exception("WhatsApp consent upsert failed")
                        raise HTTPException(503, "Consent persistence unavailable") from None

                # Contact Center köprüsü: gelen mesajı şifreli omnichannel
                # modele yansıt. ingest zaten kendi içinde fail-safe; webhook'un
                # 200-fast sözleşmesini korumak için ayrıca sarmalıyoruz.
                try:
                    await ingest_whatsapp_inbound(
                        db,
                        tenant_id=tenant_id,
                        phone_number_id=phone_number_id,
                        wa_message=msg,
                        contact_name=contacts_map.get(msg.get("from", "")),
                        strict=True,
                    )
                except Exception:
                    logger.exception("contact-center ingest bridge failed")
                    raise HTTPException(503, "Conversation persistence unavailable") from None

            # 2) Status callbacks (sent → delivered → read → failed)
            for st in value.get("statuses", []) or []:
                wa_msg_id = st.get("id", "")
                status = st.get("status", "")
                if not wa_msg_id or status not in ("sent", "delivered", "read", "failed"):
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
                        update_doc["error_message"] = (first.get("title") or first.get("message") or "")[:500]
                try:
                    await db.messaging_delivery_logs.update_one(
                        {
                            "tenant_id": tenant_id,
                            "provider_message_id": wa_msg_id,
                            "status": {"$nin": {"sent": ["delivered", "read", "failed"], "delivered": ["read"], "read": [], "failed": ["delivered", "read"]}[status]},
                        },
                        {"$set": update_doc},
                    )
                    processed += 1
                except Exception:
                    logger.exception("WhatsApp status update failed")
                    raise HTTPException(503, "Delivery persistence unavailable") from None

                # Contact Center köprüsü: teslimat durumunu giden CC mesajına
                # yansıt (yalnızca outbound; fail-safe, PII'siz).
                try:
                    await sync_whatsapp_status(
                        db,
                        tenant_id=tenant_id,
                        provider_message_id=wa_msg_id,
                        meta_status=status,
                        error_message=update_doc.get("error_message"),
                    )
                except Exception:
                    logger.exception("contact-center status sync failed (suppressed)")

    return {"received": True, "processed": processed}
