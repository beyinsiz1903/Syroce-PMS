"""
Messaging Router — SMTP Email + WhatsApp Business API.
Provider settings, template CRUD, sending, delivery logs, metrics.
"""

import logging
import random
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User
from modules.messaging.recipient_crypto import (
    recipient_hash as _recipient_hash,
)
from modules.messaging.recipient_crypto import (
    reveal_delivery_log,
    reveal_recipient,
    seal_delivery_log,
    seal_recipient,
)
from modules.pms_core.role_permission_service import (  # v90 DW
    RolePermissionService,
    require_op,
)
from security.field_encryption import get_field_encryption_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/messaging-center", tags=["messaging-center"])

# Sensitive credential keys that MUST be encrypted at rest (PCI/PII).
_SMTP_SECRET_KEYS = {"smtp_password", "zoho_client_secret", "zoho_refresh_token"}
_WHATSAPP_SECRET_KEYS = {"access_token", "webhook_verify_token", "app_secret"}


def _encrypt_secrets(creds: dict, secret_keys: set[str]) -> dict:
    """Encrypt sensitive credential values in-place (envelope format).

    Empty / already-encrypted values are passed through. Returns a new dict.
    """
    try:
        svc = get_field_encryption_service()
    except Exception:
        if creds.get("email_transport") == "zoho_api" or any(creds.get(k) for k in ("zoho_client_secret", "zoho_refresh_token")):
            raise HTTPException(503, "Güvenli anahtar saklama kullanılamıyor; ayarlar kaydedilmedi.") from None
        logger.exception("field_encryption_unavailable; storing creds plaintext (insecure)")
        return dict(creds)
    out = dict(creds)
    for k in secret_keys:
        v = out.get(k)
        if v and isinstance(v, str):
            out[k] = svc.encrypt_value(v)
    return out


def _decrypt_secrets(creds: dict, secret_keys: set[str]) -> dict:
    """Decrypt envelope-encoded credential values for runtime use."""
    try:
        svc = get_field_encryption_service()
    except Exception:
        return dict(creds)
    out = dict(creds)
    for k in secret_keys:
        v = out.get(k)
        if v and isinstance(v, str):
            out[k] = svc.decrypt_value(v)
    return out


def _merge_partial_creds(existing: dict, incoming: dict, secret_keys: set[str]) -> dict:
    """Partial-update credentials: empty incoming secret = preserve existing.

    Backend masks secrets on GET (********), so the frontend cannot send the
    real value back. Treating an empty incoming secret as "no change"
    prevents silent credential wipe (Bug #2).
    """
    merged = dict(existing or {})
    for k, v in (incoming or {}).items():
        if k in secret_keys:
            # only overwrite if user actually typed something
            if v not in (None, "", "********"):
                merged[k] = v
        else:
            merged[k] = v
    return merged


_db = None
_service = None


def _get_db():
    global _db
    if _db is None:
        from server import db

        _db = db
    return _db


def _get_service():
    global _service
    if _service is None:
        from modules.messaging.service import MessagingService

        _service = MessagingService(_get_db())
    return _service


# ════════════════════════════════════════════════════════
# Provider Settings (SMTP + WhatsApp configuration)
# ════════════════════════════════════════════════════════


class SMTPSettingsReq(BaseModel):
    email_transport: Literal["smtp", "zoho_api"] = "smtp"
    zoho_region: Literal["eu", "us"] = "eu"
    zoho_account_id: str = ""
    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_refresh_token: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""  # empty = preserve existing (mask round-trip safe)
    from_email: str
    from_name: str = "Otel"
    use_tls: bool = True
    # Bug #6 fix: default fail-safe → sandbox (no real outbound until user opts in)
    is_sandbox: bool = True
    enabled: bool = True


class WhatsAppSettingsReq(BaseModel):
    access_token: str = ""  # empty = preserve existing
    phone_number_id: str
    business_name: str = ""
    waba_id: str = ""  # WhatsApp Business Account ID
    webhook_verify_token: str = ""  # Meta verification handshake (GET /api/whatsapp/webhook)
    app_secret: str = ""  # HMAC-SHA256 secret for X-Hub-Signature-256 verification
    # Bug #6 fix: default fail-safe → sandbox
    is_sandbox: bool = True
    enabled: bool = True


@router.get("/settings")
async def get_messaging_settings(current_user: User = Depends(get_current_user)):
    """Get current email and WhatsApp configuration (credentials masked)."""
    db = _get_db()
    configs = await db.messaging_provider_configs.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(10)

    result = {"email": None, "whatsapp": None}
    for cfg in configs:
        pt = cfg.get("provider_type")
        # Bug #15 follow-up: creds are envelope-encrypted at-rest.
        # Decrypt before masking so the UI sees real plaintext bits (host/email
        # plaintext, secrets shown as ********), not ciphertext gibberish.
        raw_creds = cfg.get("credentials_encrypted", {}) or {}
        if pt == "smtp_email":
            creds = _decrypt_secrets(raw_creds, _SMTP_SECRET_KEYS)
        elif pt == "whatsapp":
            creds = _decrypt_secrets(raw_creds, _WHATSAPP_SECRET_KEYS)
        else:
            creds = raw_creds
        masked = {}

        if pt == "smtp_email":
            masked = {
                "email_transport": creds.get("email_transport", "smtp"),
                "zoho_region": creds.get("zoho_region", "eu"),
                "zoho_account_id": creds.get("zoho_account_id", ""),
                "zoho_client_id": creds.get("zoho_client_id", ""),
                "zoho_client_secret": "********" if creds.get("zoho_client_secret") else "",
                "zoho_refresh_token": "********" if creds.get("zoho_refresh_token") else "",
                "smtp_host": creds.get("smtp_host", ""),
                "smtp_port": creds.get("smtp_port", 587),
                "smtp_username": _mask(creds.get("smtp_username", "")),
                "smtp_password": "********" if creds.get("smtp_password") else "",
                "from_email": creds.get("from_email", ""),
                "from_name": creds.get("from_name", "Otel"),
                "use_tls": creds.get("use_tls", True),
            }
            result["email"] = {
                "id": cfg["id"],
                "provider_type": pt,
                "is_sandbox": cfg.get("is_sandbox", False),
                "enabled": cfg.get("enabled", True),
                "health_status": cfg.get("health_status", "unknown"),
                "credentials": masked,
            }
        elif pt == "whatsapp":
            masked = {
                "access_token": _mask(creds.get("access_token", ""), show=8),
                "phone_number_id": creds.get("phone_number_id", ""),
                "business_name": creds.get("business_name", ""),
                "waba_id": creds.get("waba_id", ""),
                "webhook_verify_token": "********" if creds.get("webhook_verify_token") else "",
                "app_secret": "********" if creds.get("app_secret") else "",
            }
            result["whatsapp"] = {
                "id": cfg["id"],
                "provider_type": pt,
                "is_sandbox": cfg.get("is_sandbox", False),
                "enabled": cfg.get("enabled", True),
                "health_status": cfg.get("health_status", "unknown"),
                "credentials": masked,
            }

    return result


def _mask(value: str, show: int = 4) -> str:
    if not value or len(value) <= show:
        return "****"
    return value[:show] + "****"


@router.post("/settings/email")
async def save_email_settings(
    req: SMTPSettingsReq,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v95 DW
):
    """Save or update SMTP email configuration.

    Bug #2 fix: Empty/masked smtp_password preserves the existing one rather
    than wiping it (frontend never sees the real value due to _mask).
    Bug #15 fix: smtp_password is encrypted at-rest via field_encryption.
    """
    db = _get_db()
    incoming = {
        "email_transport": req.email_transport,
        "zoho_region": req.zoho_region,
        "zoho_account_id": req.zoho_account_id.strip(),
        "zoho_client_id": req.zoho_client_id.strip(),
        "zoho_client_secret": req.zoho_client_secret,
        "zoho_refresh_token": req.zoho_refresh_token,
        "smtp_host": req.smtp_host,
        "smtp_port": req.smtp_port,
        "smtp_username": req.smtp_username,
        "smtp_password": req.smtp_password,
        "from_email": req.from_email,
        "from_name": req.from_name,
        "use_tls": req.use_tls,
    }
    existing = await db.messaging_provider_configs.find_one({"tenant_id": current_user.tenant_id, "provider_type": "smtp_email"}, {"_id": 0})
    now = datetime.now(UTC).isoformat()
    previous = _decrypt_secrets((existing or {}).get("credentials_encrypted", {}) or {}, _SMTP_SECRET_KEYS)
    merged = _merge_partial_creds(previous, incoming, _SMTP_SECRET_KEYS | {"smtp_username"})
    if merged.get("email_transport") == "zoho_api":
        from modules.messaging.zoho_mail import validate_credentials
        try:
            validate_credentials(merged)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
    changed_transport = previous.get("email_transport", "smtp") != req.email_transport
    sandbox = req.is_sandbox or changed_transport
    creds_encrypted = _encrypt_secrets(merged, _SMTP_SECRET_KEYS)
    if existing:
        await db.messaging_provider_configs.update_one(
            {"id": existing["id"], "tenant_id": current_user.tenant_id},
            {
                "$set": {
                    "credentials_encrypted": creds_encrypted,
                    "is_sandbox": sandbox,
                    "health_status": "unknown",
                    "enabled": req.enabled,
                    "updated_at": now,
                }
            },
        )
        return {"success": True, "action": "updated", "id": existing["id"]}
    else:
        from modules.messaging.models import new_provider_config

        doc = new_provider_config(current_user.tenant_id, "smtp_email", creds_encrypted, sandbox, req.enabled)
        await db.messaging_provider_configs.insert_one(doc)
        doc.pop("_id", None)
        return {"success": True, "action": "created", "id": doc["id"]}


@router.post("/settings/whatsapp")
async def save_whatsapp_settings(
    req: WhatsAppSettingsReq,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v95 DW
):
    """Save or update WhatsApp Business API configuration.

    Bug #2 fix: Empty access_token / webhook_verify_token / app_secret preserves
    existing values (mask round-trip safe).
    Bug #15 fix: All sensitive values encrypted at-rest.
    """
    db = _get_db()
    incoming = {
        "access_token": req.access_token,
        "phone_number_id": req.phone_number_id,
        "business_name": req.business_name,
        "waba_id": req.waba_id,
        "webhook_verify_token": req.webhook_verify_token,
        "app_secret": req.app_secret,
    }
    existing = await db.messaging_provider_configs.find_one({"tenant_id": current_user.tenant_id, "provider_type": "whatsapp"}, {"_id": 0})
    now = datetime.now(UTC).isoformat()
    if existing:
        existing_creds_dec = _decrypt_secrets(existing.get("credentials_encrypted", {}) or {}, _WHATSAPP_SECRET_KEYS)
        merged = _merge_partial_creds(existing_creds_dec, incoming, _WHATSAPP_SECRET_KEYS)
        creds_encrypted = _encrypt_secrets(merged, _WHATSAPP_SECRET_KEYS)
        await db.messaging_provider_configs.update_one(
            {"id": existing["id"]},
            {
                "$set": {
                    "credentials_encrypted": creds_encrypted,
                    "is_sandbox": req.is_sandbox,
                    "enabled": req.enabled,
                    "updated_at": now,
                }
            },
        )
        return {"success": True, "action": "updated", "id": existing["id"]}
    else:
        from modules.messaging.models import new_provider_config

        creds_encrypted = _encrypt_secrets(incoming, _WHATSAPP_SECRET_KEYS)
        doc = new_provider_config(current_user.tenant_id, "whatsapp", creds_encrypted, req.is_sandbox, req.enabled)
        await db.messaging_provider_configs.insert_one(doc)
        doc.pop("_id", None)
        return {"success": True, "action": "created", "id": doc["id"]}


@router.post("/settings/test-connection")
async def test_connection(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v95 DW
):
    """Test all configured providers."""
    svc = _get_service()
    results = await svc.check_all_providers(current_user.tenant_id)
    return {"results": results}


# ════════════════════════════════════════════════════════
# Provider List (backward compat)
# ════════════════════════════════════════════════════════


@router.get("/providers")
async def list_providers(current_user: User = Depends(get_current_user)):
    db = _get_db()
    configs = await db.messaging_provider_configs.find({"tenant_id": current_user.tenant_id}, {"_id": 0, "credentials_encrypted": 0}).to_list(20)
    return {"providers": configs}


@router.post("/providers/health-check")
async def check_provider_health(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    svc = _get_service()
    results = await svc.check_all_providers(current_user.tenant_id)
    return {"results": results}


# ════════════════════════════════════════════════════════
# Templates
# ════════════════════════════════════════════════════════


@router.get("/templates")
async def list_templates(
    channel: str | None = None,
    category: str | None = None,
    current_user: User = Depends(get_current_user),
):
    db = _get_db()
    q = {"tenant_id": current_user.tenant_id}
    if channel:
        q["channel"] = channel
    if category:
        q["category"] = category
    templates = await db.messaging_templates.find(q, {"_id": 0}).to_list(100)
    return {"templates": templates}


class TemplateReq(BaseModel):
    name: str
    category: str
    channel: str
    subject: str | None = None
    body_template: str
    variables: list[str] = []


@router.post("/templates")
async def create_template(
    req: TemplateReq,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    from modules.messaging.models import new_message_template

    doc = new_message_template(
        current_user.tenant_id,
        req.name,
        req.category,
        req.channel,
        req.subject,
        req.body_template,
        req.variables,
    )
    db = _get_db()
    await db.messaging_templates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    req: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v96 DW
):
    db = _get_db()
    allowed = ["name", "subject", "body_template", "variables", "is_active", "category"]
    updates = {k: v for k, v in req.items() if k in allowed}
    updates["updated_at"] = datetime.now(UTC).isoformat()
    result = await db.messaging_templates.update_one({"id": template_id, "tenant_id": current_user.tenant_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Sablon bulunamadi")
    return {"success": True}


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v96 DW
):
    db = _get_db()
    result = await db.messaging_templates.delete_one({"id": template_id, "tenant_id": current_user.tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Sablon bulunamadi")
    return {"success": True}


# ════════════════════════════════════════════════════════
# Send Message
# ════════════════════════════════════════════════════════


class SendReq(BaseModel):
    channel: str
    recipient: str
    template_id: str | None = None
    subject: str | None = None
    body: str | None = None
    variables: dict = {}
    booking_id: str | None = None
    guest_id: str | None = None
    property_id: str | None = None
    use_case: str | None = None


@router.post("/send")
async def send_message(
    req: SendReq,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    svc = _get_service()
    # Graceful-delivery contract: send_message already returns {"success": False, ...}
    # for every known failure mode (no provider, rate limit, bad channel, opt-out).
    # An unexpected infra hiccup (e.g. a transient consent/delivery-log read under
    # burst) must NOT surface as 5xx — that would break the messaging resilience
    # contract. Convert it into the same graceful fail-closed shape (no message is
    # sent) and log it so it stays observable. Intentional HTTPExceptions propagate.
    try:
        result = await svc.send_message(
            tenant_id=current_user.tenant_id,
            channel=req.channel,
            recipient=req.recipient,
            body=req.body,
            subject=req.subject,
            template_id=req.template_id,
            variables=req.variables,
            booking_id=req.booking_id,
            guest_id=req.guest_id,
            property_id=req.property_id,
            use_case=req.use_case,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("messaging send failed (graceful fail-closed)")
        return {"success": False, "error": "send_failed"}
    return result


# ════════════════════════════════════════════════════════
# WhatsApp Template (HSM) Send
# ════════════════════════════════════════════════════════


class WhatsAppTemplateReq(BaseModel):
    """Meta'nın onayladığı template ile mesaj gönderir.

    24 saatlik konuşma penceresi dışında ya da ilk temas için
    sadece onaylı template'ler gönderilebilir (Meta kuralı).

    `components` Meta'nın beklediği yapıdadır, örnek:
      [{"type": "body",
        "parameters": [{"type": "text", "text": "Ahmet"},
                       {"type": "text", "text": "16:00"}]}]
    """

    recipient: str
    template_name: str
    language_code: str = "tr"
    components: list[dict] = []
    booking_id: str | None = None
    guest_id: str | None = None


@router.post("/send-template")
async def send_whatsapp_template(
    req: WhatsAppTemplateReq,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    from modules.messaging.whatsapp_lifecycle import WhatsAppDelivery, approved_templates
    db = _get_db()
    templates = await approved_templates(db, current_user.tenant_id)
    selected = next((t for t in templates if t["name"] == req.template_name and t["language"] == req.language_code), None)
    if not selected or not selected["supported"]:
        raise HTTPException(400, "Desteklenen ve Meta onaylı bir şablon seçin.")
    parameters = req.components[0].get("parameters", []) if req.components else []
    if (len(req.components) > 1 or (req.components and req.components[0].get("type") != "body")
            or not isinstance(parameters, list) or len(parameters) != selected["variables_count"]
            or any(not isinstance(p, dict) or p.get("type") != "text" or not str(p.get("text", "")).strip() for p in parameters)):
        raise HTTPException(400, "Şablon değişkenleri eksik veya uyumsuz.")
    delivery = WhatsAppDelivery(db)
    delivery_id = await delivery.enqueue(current_user.tenant_id, req.recipient, req.template_name,
        req.language_code, req.components, booking_id=req.booking_id, guest_id=req.guest_id, use_case="template")
    return await delivery.deliver(current_user.tenant_id, delivery_id)


@router.post("/retry/{delivery_id}")
async def retry_delivery(
    delivery_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    svc = _get_service()
    return await svc.retry_failed(current_user.tenant_id, delivery_id)


# ════════════════════════════════════════════════════════
# Delivery Logs
# ════════════════════════════════════════════════════════


@router.get("/delivery-logs")
async def get_delivery_logs(
    status: str | None = None,
    channel: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    # Bug #3 KVKK fix: delivery logs contain misafir e-postaları/telefonları + mesaj
    # body'leri (PII). VIEW_REPORTS-grade roller (FRONT_DESK/SUPERVISOR/ADMIN)
    # erişebilsin; diğerleri (HOUSEKEEPING/F&B vb.) değil.
    _perm=Depends(require_op("view_guest_list")),
):
    db = _get_db()
    q = {"tenant_id": current_user.tenant_id}
    if status:
        q["status"] = status
    if channel:
        q["channel"] = channel
    logs = await db.messaging_delivery_logs.find(q, {"_id": 0, "template_components_enc": 0}).sort("created_at", -1).to_list(limit)
    # Recipient is sealed at rest (recipient_enc + recipient_hash); decrypt at
    # this read boundary and strip the at-rest fields. This endpoint already
    # requires view_guest_list, so the raw recipient is returned (unchanged
    # behavior), matching the prior plaintext shape.
    logs = [reveal_delivery_log(log) for log in logs]
    return {"logs": logs, "total": len(logs)}


# ════════════════════════════════════════════════════════
# Metrics
# ════════════════════════════════════════════════════════


@router.get("/metrics")
async def get_messaging_metrics(days: int = Query(7, ge=1, le=90), current_user: User = Depends(get_current_user)):
    svc = _get_service()
    return await svc.get_delivery_metrics(current_user.tenant_id, days)


# ════════════════════════════════════════════════════════
# Automation Rules
# ════════════════════════════════════════════════════════


class AutomationRuleReq(BaseModel):
    trigger_event: str
    template_id: str
    channel: str
    name: str
    enabled: bool = True
    delay_minutes: int = 0
    meta_template: dict | None = None


@router.get("/automation/triggers")
async def list_trigger_events(current_user: User = Depends(get_current_user)):
    """List available trigger events with defaults."""
    from modules.messaging.automation import TRIGGER_EVENTS

    return {"triggers": TRIGGER_EVENTS}


@router.get("/automation/rules")
async def list_automation_rules(current_user: User = Depends(get_current_user)):
    db = _get_db()
    rules = await db.messaging_automation_rules.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(200)
    from modules.messaging.automation import deduplicate_automation_rules

    unique_rules = deduplicate_automation_rules(rules)
    counts = await db.messaging_delivery_logs.aggregate([
        {"$match": {"tenant_id": current_user.tenant_id, "automation_rule_id": {"$ne": None}}},
        {"$group": {"_id": {"rule": "$automation_rule_id", "status": "$status"}, "count": {"$sum": 1}}},
    ]).to_list(None)
    for rule in unique_rules:
        if rule.get("channel") == "whatsapp":
            related = [r for r in counts if r["_id"]["rule"] == rule["id"]]
            rule["total_sent"] = sum(r["count"] for r in related if r["_id"]["status"] in ("sent", "delivered", "read"))
            rule["total_failed"] = sum(r["count"] for r in related if r["_id"]["status"] in ("failed", "rejected", "unknown"))
    return {"rules": unique_rules, "total": len(unique_rules), "duplicates_suppressed": len(rules) - len(unique_rules)}


@router.post("/automation/rules")
async def create_automation_rule(
    req: AutomationRuleReq,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    from modules.messaging.automation import TRIGGER_EVENTS, new_automation_rule

    if req.trigger_event not in TRIGGER_EVENTS:
        raise HTTPException(status_code=400, detail=f"Gecersiz tetikleme olayi: {req.trigger_event}")
    db = _get_db()
    await _validate_automation_rule(db, current_user.tenant_id, req.model_dump())
    existing = await db.messaging_automation_rules.find_one(
        {
            "tenant_id": current_user.tenant_id,
            "trigger_event": req.trigger_event,
            "template_id": req.template_id,
            "channel": req.channel,
        },
        {"_id": 0, "id": 1},
    )
    if existing:
        raise HTTPException(status_code=409, detail="Aynı tetikleyici, şablon ve kanal için bir otomasyon zaten var")

    doc = new_automation_rule(
        current_user.tenant_id,
        req.trigger_event,
        req.template_id,
        req.channel,
        req.name,
        req.enabled,
        req.delay_minutes,
    )
    doc["meta_template"] = req.meta_template
    try:
        await db.messaging_automation_rules.insert_one(doc)
    except Exception as exc:
        from pymongo.errors import DuplicateKeyError

        if isinstance(exc, DuplicateKeyError):
            raise HTTPException(status_code=409, detail="Aynı otomasyon eş zamanlı olarak oluşturuldu") from exc
        raise
    doc.pop("_id", None)
    return doc


@router.put("/automation/rules/{rule_id}")
async def update_automation_rule(
    rule_id: str,
    req: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    db = _get_db()
    allowed = ["name", "template_id", "channel", "enabled", "delay_minutes", "trigger_event", "meta_template"]
    updates = {k: v for k, v in req.items() if k in allowed}
    previous = await db.messaging_automation_rules.find_one({"id": rule_id, "tenant_id": current_user.tenant_id})
    if not previous:
        raise HTTPException(404, "Kural bulunamadı")
    merged = {**previous, **updates}
    await _validate_automation_rule(db, current_user.tenant_id, merged)
    from modules.messaging.automation import automation_rule_semantic_key
    updates["semantic_key"] = automation_rule_semantic_key(merged["trigger_event"], merged["template_id"], merged["channel"])
    updates["updated_at"] = datetime.now(UTC).isoformat()
    from pymongo.errors import DuplicateKeyError
    try:
        result = await db.messaging_automation_rules.update_one({"id": rule_id, "tenant_id": current_user.tenant_id}, {"$set": updates})
    except DuplicateKeyError:
        raise HTTPException(409, "Aynı tetikleyici ve şablon için bir kural zaten var.") from None
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Kural bulunamadi")
    return {"success": True}


@router.delete("/automation/rules/{rule_id}")
async def delete_automation_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    db = _get_db()
    result = await db.messaging_automation_rules.delete_one({"id": rule_id, "tenant_id": current_user.tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kural bulunamadi")
    return {"success": True}


@router.post("/automation/test/{rule_id}")
async def test_automation_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Simulate a rule trigger with a fake booking for testing."""
    db = _get_db()
    rule = await db.messaging_automation_rules.find_one({"id": rule_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not rule:
        raise HTTPException(status_code=404, detail="Kural bulunamadi")

    await _validate_automation_rule(db, current_user.tenant_id, {**rule, "enabled": True})
    return {"success": True, "message": "Kural yapılandırması doğrulandı. Hiçbir misafire mesaj gönderilmedi.", "used_real_booking": False}


# ════════════════════════════════════════════════════════
# Seed Demo Data (for sandbox mode)
# ════════════════════════════════════════════════════════


@router.post("/seed-demo")
async def seed_demo_data(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v96 DW
):
    """Seed demo templates, delivery logs, and automation rules."""
    db = _get_db()
    tenant_id = current_user.tenant_id
    templates_seeded = 0
    logs_seeded = 0
    rules_seeded = 0

    # ── Seed templates ──
    existing_templates = await db.messaging_templates.count_documents({"tenant_id": tenant_id})
    if existing_templates == 0:
        templates = _get_demo_templates(tenant_id)
        if templates:
            await db.messaging_templates.insert_many(templates)
            templates_seeded = len(templates)

    # ── Seed sandbox providers ──
    providers_count = await db.messaging_provider_configs.count_documents({"tenant_id": tenant_id})
    if providers_count == 0:
        from modules.messaging.models import new_provider_config

        email_cfg = new_provider_config(
            tenant_id,
            "smtp_email",
            {
                "smtp_host": "sandbox.smtp.demo",
                "smtp_port": 587,
                "smtp_username": "demo",
                "smtp_password": "demo",
                "from_email": "info@demo-otel.com",
                "from_name": "Demo Otel",
                "use_tls": True,
            },
            is_sandbox=True,
            enabled=True,
        )
        email_cfg["health_status"] = "healthy"
        wa_cfg = new_provider_config(
            tenant_id,
            "whatsapp",
            {
                "access_token": "demo_sandbox_token",
                "phone_number_id": "000000000000",
                "business_name": "Demo Otel WhatsApp",
            },
            is_sandbox=True,
            enabled=True,
        )
        wa_cfg["health_status"] = "healthy"
        await db.messaging_provider_configs.insert_many([email_cfg, wa_cfg])

    # ── Seed delivery logs ──
    existing_logs = await db.messaging_delivery_logs.count_documents({"tenant_id": tenant_id})
    if existing_logs == 0:
        logs = _get_demo_delivery_logs(tenant_id)
        if logs:
            await db.messaging_delivery_logs.insert_many([seal_delivery_log(l) for l in logs])
            logs_seeded = len(logs)

    # ── Seed automation rules ──
    if await db.messaging_automation_rules.count_documents({"tenant_id": tenant_id}) == 0:
        from modules.messaging.automation import new_automation_rule

        tmpl_list = await db.messaging_templates.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(50)
        tmpl_by_cat = {t["category"]: t for t in tmpl_list}
        default_rules = [
            ("booking_confirmed", "rezervasyon_onay", "email", "Rezervasyon Onay Emaili"),
            ("pre_arrival", "yol_tarifi", "whatsapp", "Check-in Oncesi Yol Tarifi"),
            ("checked_in", "hosgeldiniz", "whatsapp", "Hos Geldiniz Mesaji"),
            ("checked_out", "checkout", "email", "Check-out Tesekkur Emaili"),
            ("checked_out", "puan_degerlendirme", "whatsapp", "Degerlendirme Linki"),
        ]
        auto_rules = []
        for trigger, category, channel, name in default_rules:
            tmpl = tmpl_by_cat.get(category)
            if tmpl:
                auto_rules.append(
                    new_automation_rule(
                        tenant_id,
                        trigger,
                        tmpl["id"],
                        channel,
                        name,
                        enabled=True,
                    )
                )
        for rule in auto_rules:
            result = await db.messaging_automation_rules.update_one(
                {
                    "tenant_id": tenant_id,
                    "trigger_event": rule["trigger_event"],
                    "template_id": rule["template_id"],
                    "channel": rule["channel"],
                },
                {"$setOnInsert": rule},
                upsert=True,
            )
            if result.upserted_id is not None:
                rules_seeded += 1

    return {"success": True, "templates": templates_seeded, "logs": logs_seeded, "automation_rules": rules_seeded}


def _get_demo_templates(tenant_id: str) -> list[dict]:
    from modules.messaging.models import new_message_template

    templates_data = [
        # ── WhatsApp Templates ──
        {
            "name": "Hos Geldiniz",
            "category": "hosgeldiniz",
            "channel": "whatsapp",
            "subject": None,
            "body_template": "Merhaba {{misafir_adi}}, {{otel_adi}}'a hos geldiniz! Odaniz {{oda_no}} numarali odadir. WiFi sifresi: {{wifi_sifre}}. Iyi tatiller dileriz!",
            "variables": ["misafir_adi", "otel_adi", "oda_no", "wifi_sifre"],
        },
        {
            "name": "Yol Tarifi",
            "category": "yol_tarifi",
            "channel": "whatsapp",
            "subject": None,
            "body_template": "Merhaba {{misafir_adi}}, {{otel_adi}}'a ulasim bilgileri:\n\nAdres: {{adres}}\nGoogle Maps: {{harita_link}}\n\nHavaalanından transfer: {{transfer_bilgi}}\n\nGorusmek uzere!",
            "variables": ["misafir_adi", "otel_adi", "adres", "harita_link", "transfer_bilgi"],
        },
        {
            "name": "Tesis Bilgileri",
            "category": "tesis_bilgi",
            "channel": "whatsapp",
            "subject": None,
            "body_template": "{{otel_adi}} Tesis Bilgileri:\n\nRestoran: {{restoran_saatleri}}\nHavuz: {{havuz_saatleri}}\nSpa: {{spa_saatleri}}\nResepsiyon: 7/24\n\nWiFi: {{wifi_sifre}}\n\nIyi tatiller!",
            "variables": ["otel_adi", "restoran_saatleri", "havuz_saatleri", "spa_saatleri", "wifi_sifre"],
        },
        {
            "name": "Puan ve Degerlendirme",
            "category": "puan_degerlendirme",
            "channel": "whatsapp",
            "subject": None,
            "body_template": "Merhaba {{misafir_adi}}, {{otel_adi}}'daki konaklamaniz nasil gecti? Bizi degerlendirmeniz bizim icin cok onemli!\n\n{{degerlendirme_link}}\n\nTesekkur ederiz!",
            "variables": ["misafir_adi", "otel_adi", "degerlendirme_link"],
        },
        {
            "name": "Iletisim Bilgileri",
            "category": "iletisim",
            "channel": "whatsapp",
            "subject": None,
            "body_template": "{{otel_adi}} Iletisim:\n\nTelefon: {{telefon}}\nEmail: {{email}}\nAdres: {{adres}}\n\nResepsiyon 7/24 hizmetinizdedir.",
            "variables": ["otel_adi", "telefon", "email", "adres"],
        },
        # ── Email Templates ──
        {
            "name": "Rezervasyon Onay",
            "category": "rezervasyon_onay",
            "channel": "email",
            "subject": "Rezervasyon Onayiniz - {{otel_adi}}",
            "body_template": "<h2>Rezervasyon Onay</h2><p>Sayin {{misafir_adi}},</p><p>Rezervasyonunuz onaylanmistir.</p><ul><li>Giris: {{giris_tarihi}}</li><li>Cikis: {{cikis_tarihi}}</li><li>Oda: {{oda_tipi}}</li><li>Konfirmasyon No: {{konfirmasyon_no}}</li></ul><p>Iyi tatiller dileriz!</p><p>{{otel_adi}}</p>",
            "variables": ["misafir_adi", "otel_adi", "giris_tarihi", "cikis_tarihi", "oda_tipi", "konfirmasyon_no"],
        },
        {
            "name": "Fatura / Folio Gonderimi",
            "category": "fatura",
            "channel": "email",
            "subject": "Faturaniz - {{otel_adi}} #{{fatura_no}}",
            "body_template": "<h2>Fatura Bilgileri</h2><p>Sayin {{misafir_adi}},</p><p>Konaklamaniza ait fatura bilgileri asagidadir:</p><table><tr><td>Fatura No:</td><td>{{fatura_no}}</td></tr><tr><td>Toplam:</td><td>{{toplam_tutar}} TL</td></tr><tr><td>Konaklama:</td><td>{{giris_tarihi}} - {{cikis_tarihi}}</td></tr></table><p>Detayli faturaniz ekte yer almaktadir.</p><p>{{otel_adi}}</p>",
            "variables": ["misafir_adi", "otel_adi", "fatura_no", "toplam_tutar", "giris_tarihi", "cikis_tarihi"],
        },
        {
            "name": "Kampanya / Promosyon",
            "category": "kampanya",
            "channel": "email",
            "subject": "{{otel_adi}} - Ozel Firsat!",
            "body_template": "<h2>{{kampanya_baslik}}</h2><p>Sayin {{misafir_adi}},</p><p>{{kampanya_aciklama}}</p><p><strong>Indirim: %{{indirim_oran}}</strong></p><p>Gecerlilik: {{gecerlilik_tarihi}}</p><p><a href='{{rezervasyon_link}}'>Hemen Rezervasyon Yap</a></p><p>{{otel_adi}}</p>",
            "variables": ["misafir_adi", "otel_adi", "kampanya_baslik", "kampanya_aciklama", "indirim_oran", "gecerlilik_tarihi", "rezervasyon_link"],
        },
        {
            "name": "Check-out Tesekkur",
            "category": "checkout",
            "channel": "email",
            "subject": "Tesekkurler - {{otel_adi}}",
            "body_template": "<h2>Tekrar Gorusmek Uzere!</h2><p>Sayin {{misafir_adi}},</p><p>{{otel_adi}}'da bizi tercih ettiginiz icin tesekkur ederiz.</p><p>Deneyiminizi bizimle paylasmak ister misiniz?</p><p><a href='{{degerlendirme_link}}'>Degerlendirme Yap</a></p><p>Tekrar bekleriz!</p>",
            "variables": ["misafir_adi", "otel_adi", "degerlendirme_link"],
        },
    ]

    return [
        new_message_template(
            tenant_id,
            t["name"],
            t["category"],
            t["channel"],
            t["subject"],
            t["body_template"],
            t["variables"],
        )
        for t in templates_data
    ]


def _get_demo_delivery_logs(tenant_id: str) -> list[dict]:
    """Generate sample delivery logs for demo."""
    from modules.messaging.models import new_delivery_log

    logs = []
    now = datetime.now(UTC)
    names = ["Ahmet Yilmaz", "Mehmet Demir", "Ayse Kaya", "Fatma Ozturk", "Ali Celik", "Zeynep Arslan", "Mustafa Sahin", "Elif Dogan", "Hasan Kilic", "Merve Aydin"]
    channels = ["email", "whatsapp"]
    statuses = ["sent", "sent", "sent", "sent", "delivered", "delivered", "failed", "queued"]
    use_cases_email = ["fatura", "rezervasyon_onay", "kampanya", "checkout"]
    use_cases_wa = ["hosgeldiniz", "yol_tarifi", "tesis_bilgi", "puan_degerlendirme"]

    for i in range(25):
        channel = channels[i % 2]
        name = names[i % len(names)]
        status = statuses[i % len(statuses)]
        minutes_ago = random.randint(10, 10000)
        created = (now - timedelta(minutes=minutes_ago)).isoformat()

        if channel == "email":
            recipient = f"{name.lower().replace(' ', '.')}@gmail.com"
            use_case = use_cases_email[i % len(use_cases_email)]
            provider_type = "smtp_email"
            subject = f"Otel Bilgilendirme - {use_case}"
        else:
            recipient = f"+9053{random.randint(10000000, 99999999)}"
            use_case = use_cases_wa[i % len(use_cases_wa)]
            provider_type = "whatsapp"
            subject = None

        log = new_delivery_log(
            tenant_id=tenant_id,
            property_id=None,
            channel=channel,
            provider_type=provider_type,
            recipient=recipient,
            template_id=None,
            subject=subject,
            body=f"Demo mesaj - {use_case} - {name}",
            use_case=use_case,
        )
        log["status"] = status
        log["created_at"] = created
        if status in ("sent", "delivered"):
            log["delivered_at"] = created
            log["provider_message_id"] = f"demo_{uuid.uuid4().hex[:8]}"
        elif status == "failed":
            log["error_message"] = "Sandbox modunda simule edildi"
        logs.append(log)

    return logs


# ════════════════════════════════════════════════════════
# Consent & Runtime
# ════════════════════════════════════════════════════════


class ConsentReq(BaseModel):
    recipient: str
    channel: str
    status: str
    evidence: str = ""


@router.post("/consent")
async def update_consent(req: ConsentReq, current_user: User = Depends(get_current_user),
                         _perm=Depends(require_op("manage_sales"))):
    if req.channel not in ("email", "whatsapp") or req.status not in ("opt_in", "opt_out", "pending"):
        raise HTTPException(400, "Geçersiz kanal veya izin durumu.")
    if req.channel == "whatsapp" and req.status == "opt_in" and not req.evidence.strip():
        raise HTTPException(400, "İznin nerede ve ne zaman alındığını belirtin.")
    db = _get_db()
    # PII-at-rest: store the recipient sealed (recipient_enc) and key the consent
    # document on the recipient_hash blind-index instead of plaintext.
    sealed = seal_recipient(req.recipient)
    r_hash = sealed.get("recipient_hash") or _recipient_hash(req.recipient)
    now_iso = datetime.now(UTC).isoformat()
    # Match an existing row by EITHER the new blind-index OR a legacy plaintext
    # recipient, and migrate it in place ($unset plaintext). This prevents a
    # SECOND row being created for a recipient that still has a pre-backfill
    # legacy row (which would make consent enforcement nondeterministic).
    res = await db.messaging_consents.update_one(
        {
            "tenant_id": current_user.tenant_id,
            "channel": req.channel,
            "$or": [{"recipient_hash": r_hash}, {"recipient": req.recipient}],
        },
        {
            "$set": {
                "status": req.status,
                "source": "operator_recorded",
                "evidence": req.evidence[:500],
                "updated_at": now_iso,
                "updated_by": current_user.id,
                "recipient_enc": sealed.get("recipient_enc"),
                "recipient_hash": r_hash,
            },
            "$unset": {"recipient": ""},
        },
    )
    if res.matched_count == 0:
        await db.messaging_consents.insert_one(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": current_user.tenant_id,
                "channel": req.channel,
                "recipient_hash": r_hash,
                "recipient_enc": sealed.get("recipient_enc"),
                "status": req.status,
                "created_at": now_iso,
                "updated_at": now_iso,
                "updated_by": current_user.id,
            }
        )
    return {"success": True}


@router.get("/runtime-status")
async def get_runtime_status(current_user: User = Depends(get_current_user)):
    svc = _get_service()
    return svc.get_runtime_status()


# ════════════════════════════════════════════════════════
# Pre-Arrival Scheduler
# ════════════════════════════════════════════════════════


@router.get("/scheduler/status")
async def get_scheduler_status(current_user: User = Depends(get_current_user)):
    """Get pre-arrival scheduler status and metrics."""
    from modules.messaging.pre_arrival_scheduler import get_pre_arrival_scheduler

    scheduler = get_pre_arrival_scheduler()
    return scheduler.get_status()


@router.post("/scheduler/start")
async def start_scheduler(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    """Start the pre-arrival scheduler background task."""
    from modules.messaging.pre_arrival_scheduler import get_pre_arrival_scheduler

    scheduler = get_pre_arrival_scheduler()
    if scheduler.status == "running":
        return {"success": True, "message": "Zamanlayici zaten calisiyor"}
    await scheduler.start()
    return {"success": True, "message": "Zamanlayici baslatildi"}


@router.post("/scheduler/stop")
async def stop_scheduler(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    """Stop the pre-arrival scheduler."""
    from modules.messaging.pre_arrival_scheduler import get_pre_arrival_scheduler

    scheduler = get_pre_arrival_scheduler()
    await scheduler.stop()
    return {"success": True, "message": "Zamanlayici durduruldu"}


@router.post("/scheduler/run-now")
async def run_scheduler_now(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    """Manually trigger a pre-arrival scan right now."""
    from modules.messaging.pre_arrival_scheduler import get_pre_arrival_scheduler

    scheduler = get_pre_arrival_scheduler()
    result = await scheduler.run_scan()
    return {"success": True, "result": result}


# ════════════════════════════════════════════════════════
# Activity Feed (Real-time notifications)
# ════════════════════════════════════════════════════════


def _mask_recipient(value) -> str:
    """KVKK/PII partial-mask for recipient shown in the activity feed to roles
    that lack `view_guest_list`. Email → first char + ``***@domain``; other
    (phone/handle) → only the last 2 chars remain. The domain alone is not
    identifying; the local-part / number (the PII) is masked. Privileged roles
    (view_guest_list) still see the raw recipient, matching /delivery-logs."""
    s = str(value or "").strip()
    if not s:
        return s
    if "@" in s:
        local, _, domain = s.partition("@")
        head = local[:1] if local else ""
        return f"{head}***@{domain}"
    if len(s) > 2:
        return ("*" * (len(s) - 2)) + s[-2:]
    return "***"


_FREETEXT_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Phone: optional +, then 9+ digits possibly grouped by spaces/dashes/parens.
_FREETEXT_PHONE_RE = re.compile(r"\+?\d[\d\s().\-]{8,}\d")


def _mask_freetext_pii(text) -> str:
    """KVKK/PII mask for guest contact data embedded in free-text automation
    titles/messages shown in the activity feed to roles lacking
    `view_guest_list`. Notification rows (unlike delivery-log rows whose
    recipient is a discrete field) carry the email/phone inline in the
    `title`/`message`, so the discrete `_mask_recipient` gate misses them.
    Email local-part is reduced to its first char (`a***@domain`); phone digits
    are masked to the last 2. Non-PII text is left intact so the feed stays
    usable. Privileged roles never reach this path (raw text preserved)."""
    s = str(text or "")
    if not s:
        return s

    def _mask_email(m):
        local, _, domain = m.group(0).partition("@")
        head = local[:1] if local else ""
        return f"{head}***@{domain}"

    def _mask_phone(m):
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 9:
            return raw  # too short to be a phone number; leave untouched
        return ("*" * (len(raw) - 2)) + raw[-2:]

    s = _FREETEXT_EMAIL_RE.sub(_mask_email, s)
    s = _FREETEXT_PHONE_RE.sub(_mask_phone, s)
    return s


@router.get("/activity")
async def get_messaging_activity(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Get recent messaging activity (automation events, delivery results) as notifications."""
    db = _get_db()
    # KVKK/PII (Wave 9): delivery-log entries embed the recipient (email/phone)
    # in the free-text `message`. This endpoint is only get_current_user-guarded
    # (unlike /delivery-logs which requires view_guest_list). To avoid PII
    # exposure to non-privileged roles while keeping the feed usable, mask the
    # recipient unless the caller holds view_guest_list (VIEW_REPORTS).
    _can_view_pii = RolePermissionService().check_permission(
        current_user.role,
        "view_guest_list",
        granted_permissions=getattr(current_user, "granted_permissions", None),
    )
    notifications = (
        await db.notifications.find(
            {
                "tenant_id": current_user.tenant_id,
                "type": "messaging_automation",
            },
            {"_id": 0},
        )
        .sort("created_at", -1)
        .to_list(limit)
    )

    # Also get recent delivery log events for channel push results
    recent_logs = (
        await db.messaging_delivery_logs.find(
            {"tenant_id": current_user.tenant_id},
            {"_id": 0},
        )
        .sort("created_at", -1)
        .to_list(limit)
    )

    # Combine into a unified activity feed
    activities = []
    for n in notifications:
        _title = n.get("title", "")
        _message = n.get("message", "")
        if not _can_view_pii:
            # Automation notifications embed guest email/phone inline in the
            # free-text title/message (the delivery-log branch below masks its
            # discrete `recipient`, but notifications have no such field). Mask
            # the inline PII for roles lacking view_guest_list, matching the
            # delivery-log gate so the feed never leaks contact data.
            _title = _mask_freetext_pii(_title)
            _message = _mask_freetext_pii(_message)
        activities.append(
            {
                "id": n.get("id", ""),
                "type": "automation",
                "title": _title,
                "message": _message,
                "priority": n.get("priority", "normal"),
                "created_at": n.get("created_at", ""),
                "read": n.get("read", False),
            }
        )

    for log in recent_logs[:limit]:
        status = log.get("status", "")
        channel_label = "WhatsApp" if log.get("channel") == "whatsapp" else "Email"
        if status in ("sent", "delivered"):
            title = f"{channel_label} Gonderildi"
            priority = "normal"
        elif status == "failed":
            title = f"{channel_label} Başarısız"
            priority = "high"
        else:
            title = f"{channel_label} {status.title()}"
            priority = "normal"

        recipient = reveal_recipient(log)
        if not _can_view_pii:
            recipient = _mask_recipient(recipient)
        activities.append(
            {
                "id": log.get("id", ""),
                "type": "delivery",
                "title": title,
                "message": f"{recipient} — {log.get('use_case', '')}",
                "priority": priority,
                "created_at": log.get("created_at", ""),
                "status": status,
            }
        )

    # Sort by created_at desc and limit
    activities.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    return {"activities": activities[:limit]}


@router.get("/whatsapp/meta-templates")
async def list_meta_whatsapp_templates(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """Fetch approved templates with pagination and explicit setup errors."""
    from modules.messaging.whatsapp_lifecycle import approved_templates
    return {"templates": await approved_templates(_get_db(), current_user.tenant_id)}


async def _validate_automation_rule(db, tenant_id, rule):
    from modules.messaging.automation import TRIGGER_EVENTS, _build_template_variables
    from modules.messaging.whatsapp_lifecycle import validate_mapping
    if rule.get("trigger_event") not in TRIGGER_EVENTS or rule.get("channel") not in ("email", "whatsapp"):
        raise HTTPException(400, "Geçersiz olay veya kanal.")
    delay = rule.get("delay_minutes", 0)
    if not isinstance(delay, int) or not 0 <= delay <= 10080:
        raise HTTPException(400, "Gecikme 0–10080 dakika arasında olmalıdır.")
    if not rule.get("enabled"):
        return
    if rule["channel"] == "whatsapp":
        mapping = rule.get("meta_template") or {}
        await validate_mapping(db, tenant_id, mapping)
        if rule.get("template_id") != f"meta:{mapping.get('name')}:{mapping.get('language')}":
            raise HTTPException(400, "Meta şablon kimliği eşleşmiyor.")
        available = _build_template_variables({}, None, None, None)
        if any(v not in available for v in mapping.get("variables", [])):
            raise HTTPException(400, "Bilinmeyen şablon değişkeni.")
    else:
        template = await db.messaging_templates.find_one({"id": rule.get("template_id"), "tenant_id": tenant_id, "channel": "email", "is_active": True})
        if not template:
            raise HTTPException(400, "Etkin e-posta şablonu seçin.")
        if delay:
            raise HTTPException(400, "E-posta otomasyonu için gecikme desteklenmiyor; 0 seçin.")


@router.get("/hotel-info")
async def get_messaging_hotel_info(current_user: User = Depends(get_current_user)):
    tenant = await _get_db().tenants.find_one({"id": current_user.tenant_id}, {"messaging_info": 1})
    return (tenant or {}).get("messaging_info", {})


@router.put("/hotel-info")
async def set_messaging_hotel_info(req: dict, current_user: User = Depends(get_current_user),
                                  _perm=Depends(require_op("view_system_diagnostics"))):
    allowed = {"wifi_sifre", "restoran_saatleri", "havuz_saatleri", "spa_saatleri", "harita_link", "transfer_bilgi", "degerlendirme_link"}
    if any(k not in allowed or not isinstance(v, str) or len(v) > 1000 for k, v in req.items()):
        raise HTTPException(400, "Geçersiz tesis bilgisi.")
    for key in ("harita_link", "degerlendirme_link"):
        if req.get(key) and not req[key].startswith("https://"):
            raise HTTPException(400, "Bağlantılar https:// ile başlamalıdır.")
    await _get_db().tenants.update_one({"id": current_user.tenant_id}, {"$set": {"messaging_info": req}})
    return {"success": True}
