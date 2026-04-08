"""
Messaging Router — SMTP Email + WhatsApp Business API.
Provider settings, template CRUD, sending, delivery logs, metrics.
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta
import random

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/messaging-center", tags=["messaging-center"])

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
    smtp_password: str
    from_email: str
    from_name: str = "Otel"
    use_tls: bool = True
    is_sandbox: bool = False
    enabled: bool = True


class WhatsAppSettingsReq(BaseModel):
    access_token: str
    phone_number_id: str
    business_name: str = ""
    is_sandbox: bool = False
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
        creds = cfg.get("credentials_encrypted", {})
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
async def save_email_settings(req: SMTPSettingsReq, current_user: User = Depends(get_current_user)):
    """Save or update SMTP email configuration."""
    db = _get_db()
    creds = {
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
        await db.messaging_provider_configs.update_one(
            {"id": existing["id"]},
            {"$set": {
                "credentials_encrypted": creds,
                "is_sandbox": req.is_sandbox,
                "enabled": req.enabled,
                "updated_at": now,
            }},
        )
        return {"success": True, "action": "updated", "id": existing["id"]}
    else:
        from modules.messaging.models import new_provider_config
        doc = new_provider_config(current_user.tenant_id, "smtp_email", creds, req.is_sandbox, req.enabled)
        await db.messaging_provider_configs.insert_one(doc)
        doc.pop("_id", None)
        return {"success": True, "action": "created", "id": doc["id"]}


@router.post("/settings/whatsapp")
async def save_whatsapp_settings(req: WhatsAppSettingsReq, current_user: User = Depends(get_current_user)):
    """Save or update WhatsApp Business API configuration."""
    db = _get_db()
    creds = {
        "access_token": req.access_token,
        "phone_number_id": req.phone_number_id,
        "business_name": req.business_name,
    }
    existing = await db.messaging_provider_configs.find_one(
        {"tenant_id": current_user.tenant_id, "provider_type": "whatsapp"}, {"_id": 0}
    )
    now = datetime.now(UTC).isoformat()
    if existing:
        await db.messaging_provider_configs.update_one(
            {"id": existing["id"]},
            {"$set": {
                "credentials_encrypted": creds,
                "is_sandbox": req.is_sandbox,
                "enabled": req.enabled,
                "updated_at": now,
            }},
        )
        return {"success": True, "action": "updated", "id": existing["id"]}
    else:
        from modules.messaging.models import new_provider_config
        doc = new_provider_config(current_user.tenant_id, "whatsapp", creds, req.is_sandbox, req.enabled)
        await db.messaging_provider_configs.insert_one(doc)
        doc.pop("_id", None)
        return {"success": True, "action": "created", "id": doc["id"]}


@router.post("/settings/test-connection")
async def test_connection(current_user: User = Depends(get_current_user)):
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
async def check_provider_health(current_user: User = Depends(get_current_user)):
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
async def create_template(req: TemplateReq, current_user: User = Depends(get_current_user)):
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
async def update_template(template_id: str, req: dict, current_user: User = Depends(get_current_user)):
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
async def delete_template(template_id: str, current_user: User = Depends(get_current_user)):
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
async def send_message(req: SendReq, current_user: User = Depends(get_current_user)):
    svc = _get_service()
    result = await svc.send_message(
        tenant_id=current_user.tenant_id, channel=req.channel, recipient=req.recipient,
        body=req.body, subject=req.subject, template_id=req.template_id,
        variables=req.variables, booking_id=req.booking_id, guest_id=req.guest_id,
        property_id=req.property_id, use_case=req.use_case,
    )
    return result


@router.post("/retry/{delivery_id}")
async def retry_delivery(delivery_id: str, current_user: User = Depends(get_current_user)):
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
async def create_automation_rule(req: AutomationRuleReq, current_user: User = Depends(get_current_user)):
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
async def update_automation_rule(rule_id: str, req: dict, current_user: User = Depends(get_current_user)):
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
async def delete_automation_rule(rule_id: str, current_user: User = Depends(get_current_user)):
    db = _get_db()
    result = await db.messaging_automation_rules.delete_one(
        {"id": rule_id, "tenant_id": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kural bulunamadi")
    return {"success": True}


@router.post("/automation/test/{rule_id}")
async def test_automation_rule(rule_id: str, current_user: User = Depends(get_current_user)):
    """Simulate a rule trigger with a fake booking for testing."""
    db = _get_db()
    rule = await db.messaging_automation_rules.find_one(
        {"id": rule_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Kural bulunamadi")

    fake_booking = {
        "id": "test-" + str(uuid.uuid4())[:8],
        "guest_name": "Test Misafir",
        "guest_id": None,
        "room_id": None,
        "room_number": "101",
        "check_in": datetime.now(UTC).isoformat(),
        "check_out": datetime.now(UTC).isoformat(),
        "total_amount": 1500,
    }
    from modules.messaging.automation import process_booking_event
    await process_booking_event(current_user.tenant_id, rule["trigger_event"], fake_booking)
    return {"success": True, "message": f"Test tetiklendi: {rule['name']}"}


# ════════════════════════════════════════════════════════
# Seed Demo Data (for sandbox mode)
# ════════════════════════════════════════════════════════

@router.post("/seed-demo")
async def seed_demo_data(current_user: User = Depends(get_current_user)):
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
async def start_scheduler(current_user: User = Depends(get_current_user)):
    """Start the pre-arrival scheduler background task."""
    from modules.messaging.pre_arrival_scheduler import get_pre_arrival_scheduler
    scheduler = get_pre_arrival_scheduler()
    if scheduler.status == "running":
        return {"success": True, "message": "Zamanlayici zaten calisiyor"}
    await scheduler.start()
    return {"success": True, "message": "Zamanlayici baslatildi"}


@router.post("/scheduler/stop")
async def stop_scheduler(current_user: User = Depends(get_current_user)):
    """Stop the pre-arrival scheduler."""
    from modules.messaging.pre_arrival_scheduler import get_pre_arrival_scheduler
    scheduler = get_pre_arrival_scheduler()
    await scheduler.stop()
    return {"success": True, "message": "Zamanlayici durduruldu"}


@router.post("/scheduler/run-now")
async def run_scheduler_now(current_user: User = Depends(get_current_user)):
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
            title = f"{channel_label} Basarisiz"
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
