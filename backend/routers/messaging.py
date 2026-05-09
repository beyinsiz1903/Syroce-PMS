"""
Messaging Router — SMTP Email + WhatsApp Business API.
Provider settings, template CRUD, sending, delivery logs, metrics.
"""
import logging
import random
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v90 DW
from security.field_encryption import get_field_encryption_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/messaging-center", tags=["messaging-center"])

# Sensitive credential keys that MUST be encrypted at rest (PCI/PII).
_SMTP_SECRET_KEYS = {"smtp_password"}
_WHATSAPP_SECRET_KEYS = {"access_token", "webhook_verify_token", "app_secret"}


def _encrypt_secrets(creds: dict, secret_keys: set[str]) -> dict:
    """Encrypt sensitive credential values in-place (envelope format).

    Empty / already-encrypted values are passed through. Returns a new dict.
    """
    try:
        svc = get_field_encryption_service()
    except Exception:
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
    smtp_host: str
    smtp_port: int = 587
    smtp_username: str
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
    webhook_verify_token: str = ""  # Meta verification handshake (GET /api/whatsapp/webhook)
    app_secret: str = ""  # HMAC-SHA256 secret for X-Hub-Signature-256 verification
    # Bug #6 fix: default fail-safe → sandbox
    is_sandbox: bool = True
    enabled: bool = True


@router.get("/settings")
async def get_messaging_settings(current_user: User = Depends(get_current_user)):
    """Get current email and WhatsApp configuration (credentials masked)."""
    db = _get_db()
    configs = await db.messaging_provider_configs.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).to_list(10)

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
async def save_email_settings(req: SMTPSettingsReq, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v95 DW
):
    """Save or update SMTP email configuration.

    Bug #2 fix: Empty/masked smtp_password preserves the existing one rather
    than wiping it (frontend never sees the real value due to _mask).
    Bug #15 fix: smtp_password is encrypted at-rest via field_encryption.
    """
    db = _get_db()
    incoming = {
        "smtp_host": req.smtp_host,
        "smtp_port": req.smtp_port,
        "smtp_username": req.smtp_username,
        "smtp_password": req.smtp_password,
        "from_email": req.from_email,
        "from_name": req.from_name,
        "use_tls": req.use_tls,
    }
    existing = await db.messaging_provider_configs.find_one(
        {"tenant_id": current_user.tenant_id, "provider_type": "smtp_email"}, {"_id": 0}
    )
    now = datetime.now(UTC).isoformat()
    if existing:
        existing_creds_dec = _decrypt_secrets(
            existing.get("credentials_encrypted", {}) or {}, _SMTP_SECRET_KEYS
        )
        merged = _merge_partial_creds(existing_creds_dec, incoming, _SMTP_SECRET_KEYS)
        creds_encrypted = _encrypt_secrets(merged, _SMTP_SECRET_KEYS)
        await db.messaging_provider_configs.update_one(
            {"id": existing["id"]},
            {"$set": {
                "credentials_encrypted": creds_encrypted,
                "is_sandbox": req.is_sandbox,
                "enabled": req.enabled,
                "updated_at": now,
            }},
        )
        return {"success": True, "action": "updated", "id": existing["id"]}
    else:
        from modules.messaging.models import new_provider_config
        creds_encrypted = _encrypt_secrets(incoming, _SMTP_SECRET_KEYS)
        doc = new_provider_config(current_user.tenant_id, "smtp_email", creds_encrypted, req.is_sandbox, req.enabled)
        await db.messaging_provider_configs.insert_one(doc)
        doc.pop("_id", None)
        return {"success": True, "action": "created", "id": doc["id"]}


@router.post("/settings/whatsapp")
async def save_whatsapp_settings(req: WhatsAppSettingsReq, current_user: User = Depends(get_current_user),
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
        "webhook_verify_token": req.webhook_verify_token,
        "app_secret": req.app_secret,
    }
    existing = await db.messaging_provider_configs.find_one(
        {"tenant_id": current_user.tenant_id, "provider_type": "whatsapp"}, {"_id": 0}
    )
    now = datetime.now(UTC).isoformat()
    if existing:
        existing_creds_dec = _decrypt_secrets(
            existing.get("credentials_encrypted", {}) or {}, _WHATSAPP_SECRET_KEYS
        )
        merged = _merge_partial_creds(existing_creds_dec, incoming, _WHATSAPP_SECRET_KEYS)
        creds_encrypted = _encrypt_secrets(merged, _WHATSAPP_SECRET_KEYS)
        await db.messaging_provider_configs.update_one(
            {"id": existing["id"]},
            {"$set": {
                "credentials_encrypted": creds_encrypted,
                "is_sandbox": req.is_sandbox,
                "enabled": req.enabled,
                "updated_at": now,
            }},
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
async def test_connection(current_user: User = Depends(get_current_user),
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
    configs = await db.messaging_provider_configs.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0, "credentials_encrypted": 0}
    ).to_list(20)
    return {"providers": configs}


@router.post("/providers/health-check")
async def check_provider_health(current_user: User = Depends(get_current_user),
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
async def create_template(req: TemplateReq, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    from modules.messaging.models import new_message_template
    doc = new_message_template(
        current_user.tenant_id, req.name, req.category, req.channel,
        req.subject, req.body_template, req.variables,
    )
    db = _get_db()
    await db.messaging_templates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/templates/{template_id}")
async def update_template(template_id: str, req: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v96 DW
):
    db = _get_db()
    allowed = ["name", "subject", "body_template", "variables", "is_active", "category"]
    updates = {k: v for k, v in req.items() if k in allowed}
    updates["updated_at"] = datetime.now(UTC).isoformat()
    result = await db.messaging_templates.update_one(
        {"id": template_id, "tenant_id": current_user.tenant_id}, {"$set": updates}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Sablon bulunamadi")
    return {"success": True}


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v96 DW
):
    db = _get_db()
    result = await db.messaging_templates.delete_one(
        {"id": template_id, "tenant_id": current_user.tenant_id}
    )
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
async def send_message(req: SendReq, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    svc = _get_service()
    result = await svc.send_message(
        tenant_id=current_user.tenant_id, channel=req.channel, recipient=req.recipient,
        body=req.body, subject=req.subject, template_id=req.template_id,
        variables=req.variables, booking_id=req.booking_id, guest_id=req.guest_id,
        property_id=req.property_id, use_case=req.use_case,
    )
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
    db = _get_db()
    cfg = await db.messaging_provider_configs.find_one(
        {
            "tenant_id": current_user.tenant_id,
            "provider_type": "whatsapp",
            "enabled": True,
        },
        {"_id": 0},
    )
    if not cfg:
        raise HTTPException(
            status_code=400,
            detail="WhatsApp yapılandırılmamış (önce /settings/whatsapp ile credentials ekleyin)",
        )

    from modules.messaging.models import ProviderType, new_delivery_log
    from modules.messaging.providers import PROVIDER_MAP, ProviderMode

    provider = PROVIDER_MAP[ProviderType.WHATSAPP.value]
    creds = cfg.get("credentials_encrypted", {}) or {}
    mode = ProviderMode.SANDBOX if cfg.get("is_sandbox") else ProviderMode.LIVE

    result = await provider.send_template(
        recipient=req.recipient,
        template_name=req.template_name,
        language_code=req.language_code,
        components=req.components,
        credentials=creds,
        mode=mode,
    )

    # delivery log
    try:
        log = new_delivery_log(
            tenant_id=current_user.tenant_id,
            property_id=None,
            channel="whatsapp",
            provider_type=ProviderType.WHATSAPP.value,
            recipient=req.recipient,
            template_id=None,
            subject=None,
            body=f"[template:{req.template_name}]",
            booking_id=req.booking_id,
            guest_id=req.guest_id,
            use_case="template",
        )
        log["status"] = "sent" if result.get("success") else "failed"
        log["provider_message_id"] = result.get("provider_message_id")
        log["error_message"] = result.get("error")
        log["template_name"] = req.template_name
        log["template_language"] = req.language_code
        await db.messaging_delivery_logs.insert_one(log)
    except Exception:
        logger.exception("template send delivery log insert failed")

    return result


@router.post("/retry/{delivery_id}")
async def retry_delivery(delivery_id: str, current_user: User = Depends(get_current_user),
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
    logs = await db.messaging_delivery_logs.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"logs": logs, "total": len(logs)}


# ════════════════════════════════════════════════════════
# Metrics
# ════════════════════════════════════════════════════════

@router.get("/metrics")
async def get_messaging_metrics(days: int = Query(7, ge=1, le=90),
                                 current_user: User = Depends(get_current_user)):
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


@router.get("/automation/triggers")
async def list_trigger_events(current_user: User = Depends(get_current_user)):
    """List available trigger events with defaults."""
    from modules.messaging.automation import TRIGGER_EVENTS
    return {"triggers": TRIGGER_EVENTS}


@router.get("/automation/rules")
async def list_automation_rules(current_user: User = Depends(get_current_user)):
    db = _get_db()
    rules = await db.messaging_automation_rules.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).to_list(50)
    return {"rules": rules}


@router.post("/automation/rules")
async def create_automation_rule(req: AutomationRuleReq, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    from modules.messaging.automation import TRIGGER_EVENTS, new_automation_rule
    if req.trigger_event not in TRIGGER_EVENTS:
        raise HTTPException(status_code=400, detail=f"Gecersiz tetikleme olayi: {req.trigger_event}")
    db = _get_db()
    doc = new_automation_rule(
        current_user.tenant_id, req.trigger_event, req.template_id,
        req.channel, req.name, req.enabled, req.delay_minutes,
    )
    await db.messaging_automation_rules.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/automation/rules/{rule_id}")
async def update_automation_rule(rule_id: str, req: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    db = _get_db()
    allowed = ["name", "template_id", "channel", "enabled", "delay_minutes", "trigger_event"]
    updates = {k: v for k, v in req.items() if k in allowed}
    updates["updated_at"] = datetime.now(UTC).isoformat()
    result = await db.messaging_automation_rules.update_one(
        {"id": rule_id, "tenant_id": current_user.tenant_id}, {"$set": updates}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Kural bulunamadi")
    return {"success": True}


@router.delete("/automation/rules/{rule_id}")
async def delete_automation_rule(rule_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    db = _get_db()
    result = await db.messaging_automation_rules.delete_one(
        {"id": rule_id, "tenant_id": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kural bulunamadi")
    return {"success": True}


@router.post("/automation/test/{rule_id}")
async def test_automation_rule(rule_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Simulate a rule trigger with a fake booking for testing."""
    db = _get_db()
    rule = await db.messaging_automation_rules.find_one(
        {"id": rule_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Kural bulunamadi")

    # Bug #11 fix: Try to use a real recent booking with a guest_id so that
    # automation flow's recipient resolution actually exercises end-to-end.
    # Fallback to a labeled fake only if no real bookings exist.
    real = await db.bookings.find_one(
        {"tenant_id": current_user.tenant_id, "guest_id": {"$ne": None}},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if real:
        booking_for_test = {
            **real,
            "id": "test-" + str(real.get("id", uuid.uuid4().hex[:8])),
            "_test_mode": True,
        }
    else:
        booking_for_test = {
            "id": "test-" + str(uuid.uuid4())[:8],
            "guest_name": "Test Misafir",
            "guest_id": None,
            "room_id": None,
            "room_number": "101",
            "check_in": datetime.now(UTC).isoformat(),
            "check_out": datetime.now(UTC).isoformat(),
            "total_amount": 1500,
            "_test_mode": True,
        }
    from modules.messaging.automation import process_booking_event
    try:
        await process_booking_event(current_user.tenant_id, rule["trigger_event"], booking_for_test)
    except Exception as e:
        logger.exception("automation test failed")
        return {
            "success": False,
            "message": f"Test calistirildi ama hata: {e}",
            "used_real_booking": bool(real),
        }
    return {
        "success": True,
        "message": f"Test tetiklendi: {rule['name']}"
                   + (" (gercek rezervasyon kullanildi)" if real else " (gercek rezervasyon yok, sahte booking ile)"),
        "used_real_booking": bool(real),
    }


# ════════════════════════════════════════════════════════
# Seed Demo Data (for sandbox mode)
# ════════════════════════════════════════════════════════

@router.post("/seed-demo")
async def seed_demo_data(current_user: User = Depends(get_current_user),
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
        email_cfg = new_provider_config(tenant_id, "smtp_email", {
            "smtp_host": "sandbox.smtp.demo",
            "smtp_port": 587,
            "smtp_username": "demo",
            "smtp_password": "demo",
            "from_email": "info@demo-otel.com",
            "from_name": "Demo Otel",
            "use_tls": True,
        }, is_sandbox=True, enabled=True)
        email_cfg["health_status"] = "healthy"
        wa_cfg = new_provider_config(tenant_id, "whatsapp", {
            "access_token": "demo_sandbox_token",
            "phone_number_id": "000000000000",
            "business_name": "Demo Otel WhatsApp",
        }, is_sandbox=True, enabled=True)
        wa_cfg["health_status"] = "healthy"
        await db.messaging_provider_configs.insert_many([email_cfg, wa_cfg])

    # ── Seed delivery logs ──
    existing_logs = await db.messaging_delivery_logs.count_documents({"tenant_id": tenant_id})
    if existing_logs == 0:
        logs = _get_demo_delivery_logs(tenant_id)
        if logs:
            await db.messaging_delivery_logs.insert_many(logs)
            logs_seeded = len(logs)

    # ── Seed automation rules ──
    rules_count = await db.messaging_automation_rules.count_documents({"tenant_id": tenant_id})
    if rules_count == 0:
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
                auto_rules.append(new_automation_rule(
                    tenant_id, trigger, tmpl["id"], channel, name, enabled=True,
                ))
        if auto_rules:
            await db.messaging_automation_rules.insert_many(auto_rules)
            rules_seeded = len(auto_rules)

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
            tenant_id, t["name"], t["category"], t["channel"],
            t["subject"], t["body_template"], t["variables"],
        )
        for t in templates_data
    ]


def _get_demo_delivery_logs(tenant_id: str) -> list[dict]:
    """Generate sample delivery logs for demo."""
    from modules.messaging.models import new_delivery_log
    logs = []
    now = datetime.now(UTC)
    names = ["Ahmet Yilmaz", "Mehmet Demir", "Ayse Kaya", "Fatma Ozturk", "Ali Celik",
             "Zeynep Arslan", "Mustafa Sahin", "Elif Dogan", "Hasan Kilic", "Merve Aydin"]
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
            tenant_id=tenant_id, property_id=None, channel=channel,
            provider_type=provider_type, recipient=recipient,
            template_id=None, subject=subject,
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


@router.post("/consent")
async def update_consent(req: ConsentReq, current_user: User = Depends(get_current_user)):
    db = _get_db()
    await db.messaging_consents.update_one(
        {"tenant_id": current_user.tenant_id, "recipient": req.recipient, "channel": req.channel},
        {"$set": {
            "status": req.status,
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": current_user.id,
        },
         "$setOnInsert": {
             "id": str(uuid.uuid4()),
             "tenant_id": current_user.tenant_id,
             "recipient": req.recipient,
             "channel": req.channel,
             "created_at": datetime.now(UTC).isoformat(),
         }},
        upsert=True,
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
async def start_scheduler(current_user: User = Depends(get_current_user),
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
async def stop_scheduler(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    """Stop the pre-arrival scheduler."""
    from modules.messaging.pre_arrival_scheduler import get_pre_arrival_scheduler
    scheduler = get_pre_arrival_scheduler()
    await scheduler.stop()
    return {"success": True, "message": "Zamanlayici durduruldu"}


@router.post("/scheduler/run-now")
async def run_scheduler_now(current_user: User = Depends(get_current_user),
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

@router.get("/activity")
async def get_messaging_activity(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Get recent messaging activity (automation events, delivery results) as notifications."""
    db = _get_db()
    notifications = await db.notifications.find(
        {
            "tenant_id": current_user.tenant_id,
            "type": "messaging_automation",
        },
        {"_id": 0},
    ).sort("created_at", -1).to_list(limit)

    # Also get recent delivery log events for channel push results
    recent_logs = await db.messaging_delivery_logs.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0},
    ).sort("created_at", -1).to_list(limit)

    # Combine into a unified activity feed
    activities = []
    for n in notifications:
        activities.append({
            "id": n.get("id", ""),
            "type": "automation",
            "title": n.get("title", ""),
            "message": n.get("message", ""),
            "priority": n.get("priority", "normal"),
            "created_at": n.get("created_at", ""),
            "read": n.get("read", False),
        })

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

        activities.append({
            "id": log.get("id", ""),
            "type": "delivery",
            "title": title,
            "message": f"{log.get('recipient', '')} — {log.get('use_case', '')}",
            "priority": priority,
            "created_at": log.get("created_at", ""),
            "status": status,
        })

    # Sort by created_at desc and limit
    activities.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    return {"activities": activities[:limit]}
