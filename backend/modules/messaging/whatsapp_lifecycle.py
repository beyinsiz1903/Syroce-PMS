"""Approved-template delivery with durable intent and conservative retries.

A timeout is NOT proof that Meta rejected a message. Unknown outcomes are held
for operator reconciliation rather than automatically sent a second time.
"""
import json
import re
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from modules.messaging.models import new_delivery_log
from modules.messaging.providers import PROVIDER_MAP
from modules.messaging.recipient_crypto import reveal_recipient, seal_delivery_log
from modules.messaging.service import MessagingService
from security.field_encryption import get_field_encryption_service


def normalize_phone(value):
    phone = re.sub(r"[\s().-]", "", str(value or ""))
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not re.fullmatch(r"\+?[1-9]\d{7,14}", phone):
        raise ValueError("Telefon numarası ülke koduyla girilmelidir.")
    return phone.lstrip("+")


def describe_template(template):
    """Only allow shapes this UI can completely and unambiguously populate."""
    body = next((c.get("text", "") for c in template.get("components", []) if c.get("type") == "BODY"), "")
    slots = sorted(set(re.findall(r"\{\{(\d+)\}\}", body)), key=int)
    supported = slots == [str(n) for n in range(1, len(slots) + 1)]
    if re.search(r"\{\{[^\d}][^}]*\}\}", body):
        supported = False
    for comp in template.get("components", []):
        if comp.get("type") == "HEADER" and (comp.get("format") != "TEXT" or "{{" in comp.get("text", "")):
            supported = False
        if comp.get("type") == "BUTTONS":
            for button in comp.get("buttons", []):
                if button.get("type") not in ("URL", "PHONE_NUMBER") or "{{" in button.get("url", ""):
                    supported = False
        if comp.get("type") not in ("BODY", "HEADER", "FOOTER", "BUTTONS"):
            supported = False
    return {**template, "variables_count": len(slots), "supported": supported,
            "unsupported_reason": "" if supported else "Dinamik başlık, medya, adlandırılmış değişken veya etkileşimli düğme desteklenmiyor."}


async def approved_templates(db, tenant_id):
    svc = MessagingService(db)
    config = await svc._get_provider_config(tenant_id, "whatsapp")
    if not config:
        raise HTTPException(400, "Önce etkin WhatsApp bağlantısını yapılandırın.")
    if config.get("is_sandbox"):
        return [describe_template({"name": "hello_world", "language": "en_US", "category": "UTILITY",
                                   "status": "APPROVED", "components": [{"type": "BODY", "text": "Hello World Sandbox"}]})]
    creds = await svc._load_credentials(tenant_id, config)
    waba = creds.get("waba_id")
    if not waba or not str(waba).isdigit() or not creds.get("access_token"):
        raise HTTPException(400, "WhatsApp Business hesap kimliği (WABA ID) ve erişim anahtarı gerekli.")
    result, after = [], None
    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            params = {"limit": 100}
            if after:
                params["after"] = after
            response = await client.get(f"https://graph.facebook.com/v21.0/{waba}/message_templates",
                                        headers={"Authorization": f"Bearer {creds['access_token']}"}, params=params)
            if response.status_code != 200:
                raise HTTPException(502, "Meta şablonları alınamadı. Hesap kimliği ve anahtar izinlerini kontrol edin.")
            data = response.json()
            result.extend(describe_template(t) for t in data.get("data", []) if t.get("status") == "APPROVED")
            paging = data.get("paging", {})
            cursor = paging.get("cursors", {}).get("after")
            if not paging.get("next") or not cursor or cursor == after:
                break
            after = cursor
    return result


async def validate_mapping(db, tenant_id, mapping):
    templates = await approved_templates(db, tenant_id)
    selected = next((t for t in templates if t["name"] == mapping.get("name") and t["language"] == mapping.get("language")), None)
    if not selected or not selected["supported"]:
        raise HTTPException(400, "Desteklenen, Meta onaylı bir şablon ve dil seçin.")
    params = mapping.get("variables", [])
    if not isinstance(params, list) or len(params) != selected["variables_count"] or not all(isinstance(v, str) and v.strip() for v in params):
        raise HTTPException(400, "Şablon değişkenlerinin tamamını sırasıyla eşleştirin.")
    return selected


class WhatsAppDelivery:
    def __init__(self, db):
        self.db = db
        self.service = MessagingService(db)

    async def enqueue(self, tenant_id, recipient, name, language, components, *, key=None, delay_minutes=0, **context):
        now = datetime.now(UTC)
        identity = key or str(uuid.uuid4())
        config = await self.service._get_provider_config(tenant_id, "whatsapp")
        doc = new_delivery_log(tenant_id=tenant_id, property_id=None, channel="whatsapp",
                               provider_type="whatsapp", recipient=recipient, template_id=None,
                               subject=None, body=f"[template:{name}]", booking_id=context.get("booking_id"),
                               guest_id=context.get("guest_id"), use_case=context.get("use_case"))
        doc.update({"_id": identity, "id": identity, "status": context.get("initial_status", "queued"),
                    "error_message": context.get("error_message"), "template_name": name,
                    "template_language": language, "template_components_enc": get_field_encryption_service().encrypt_value(json.dumps(components)),
                    "next_retry_at": (now + timedelta(minutes=delay_minutes)).isoformat(), "retry_count": 0,
                    "automation_rule_id": context.get("rule_id"), "required_mode": self.service._resolve_mode(config) if config else None})
        try:
            await self.db.messaging_delivery_logs.insert_one(seal_delivery_log(doc))
        except DuplicateKeyError:
            pass
        return identity

    async def deliver(self, tenant_id, delivery_id):
        query = {"tenant_id": tenant_id, "id": delivery_id}
        doc = await self.db.messaging_delivery_logs.find_one(query)
        if not doc or doc.get("status") not in ("queued", "failed") or not doc.get("template_components_enc"):
            return {"success": False, "error": "Gönderim beklemiyor; tekrar gönderilmedi."}
        if doc.get("status") == "queued" and doc.get("next_retry_at", "") > datetime.now(UTC).isoformat():
            return {"success": False, "error": "Planlanan gönderim zamanı henüz gelmedi."}
        if doc.get("retry_count", 0) >= 3:
            return {"success": False, "error": "Yeniden deneme sınırına ulaşıldı."}
        claim = await self.db.messaging_delivery_logs.update_one(
            {**query, "status": doc["status"], "retry_count": doc.get("retry_count", 0)},
            {"$set": {"status": "sending", "updated_at": datetime.now(UTC).isoformat()}, "$inc": {"retry_count": 1}})
        if claim.modified_count != 1:
            return {"success": False, "error": "Gönderim başka bir işlem tarafından alındı."}
        config = await self.service._get_provider_config(tenant_id, "whatsapp")
        # Any failure BEFORE invoking the transport is known not to have sent.
        try:
            recipient = normalize_phone(reveal_recipient(doc))
            if not config:
                raise ValueError("Etkin WhatsApp bağlantısı yok.")
            if not await self.service._check_consent(tenant_id, recipient, "whatsapp") or not await self.service._check_consent(tenant_id, "+" + recipient, "whatsapp"):
                raise ValueError("Misafir WhatsApp iletilerini reddetmiş.")
            if doc.get("required_mode") != self.service._resolve_mode(config):
                raise ValueError("Bağlantı modu değişti; eski kuyruk otomatik olarak canlıya taşınmaz.")
            if doc.get("automation_rule_id"):
                rule = await self.db.messaging_automation_rules.find_one({"tenant_id": tenant_id, "id": doc["automation_rule_id"], "enabled": True})
                booking = await self.db.bookings.find_one({"tenant_id": tenant_id, "id": doc.get("booking_id")})
                allowed_statuses = {"booking_created": ("pending", "confirmed", "guaranteed"),
                                    "booking_confirmed": ("confirmed", "guaranteed"),
                                    "pre_arrival": ("confirmed", "guaranteed"),
                                    "checked_in": ("checked_in",), "checked_out": ("checked_out",)}
                if not rule or not booking or booking.get("status") not in allowed_statuses.get(doc.get("use_case"), ()):
                    raise ValueError("Kural kapalı veya rezervasyon artık bu olay için uygun değil.")
            if not config.get("is_sandbox"):
                from modules.messaging.recipient_crypto import recipient_hash
                aliases = [recipient, "+" + recipient]
                consents = await self.db.messaging_consents.find(
                    {"tenant_id": tenant_id, "channel": "whatsapp",
                     "$or": [{"recipient_hash": {"$in": [recipient_hash(v) for v in aliases]}},
                             {"recipient": {"$in": aliases}}]}).to_list(None)
                if not any(c.get("status") == "opt_in" and c.get("source") != "wa_inbound" for c in consents):
                    raise ValueError("Misafirin WhatsApp ileti izni kaydedilmemiş.")
            creds = await self.service._load_credentials(tenant_id, config)
            components = json.loads(get_field_encryption_service().decrypt_value(doc["template_components_enc"]))
        except (ValueError, TypeError) as exc:
            await self.db.messaging_delivery_logs.update_one(query, {"$set": {"status": "rejected", "error_message": str(exc)}})
            return {"success": False, "error": str(exc)}
        try:
            result = await PROVIDER_MAP["whatsapp"].send_template(recipient=recipient, template_name=doc["template_name"],
                      language_code=doc["template_language"], components=components, credentials=creds,
                      mode=self.service._resolve_mode(config))
        except Exception:
            result = {"success": False, "error": "Gönderimin sonucu doğrulanamadı.", "outcome_unknown": True}
        now = datetime.now(UTC)
        success = result.get("success", False)
        status = ("simulated" if config.get("is_sandbox") or config.get("mode") == "test" else "sent") if success else ("unknown" if result.get("outcome_unknown") else "failed")
        updates = {"status": status, "updated_at": now.isoformat(), "error_message": result.get("error"),
                   "provider_message_id": result.get("provider_message_id"), "next_retry_at": (now + timedelta(minutes=2 ** (doc.get("retry_count", 0) + 1))).isoformat()}
        if success:
            updates["sent_at"] = now.isoformat()
        # Never downgrade an early delivery callback.
        await self.db.messaging_delivery_logs.update_one({**query, "status": "sending"}, {"$set": updates})
        return {**result, "status": status, "delivery_id": delivery_id}

    async def drain(self, limit=100):
        now = datetime.now(UTC)
        await self.db.messaging_delivery_logs.update_many(
            {"status": "sending", "template_components_enc": {"$exists": True}, "updated_at": {"$lt": (now - timedelta(minutes=5)).isoformat()}},
            {"$set": {"status": "unknown", "error_message": "İşlem kesildi; Meta sonucu kontrol edilmeden yeniden gönderilmez."}})
        docs = await self.db.messaging_delivery_logs.find(
            {"status": {"$in": ["queued", "failed"]}, "template_components_enc": {"$exists": True},
             "retry_count": {"$lt": 3}, "next_retry_at": {"$lte": now.isoformat()}}).sort("next_retry_at", 1).limit(limit).to_list(limit)
        for doc in docs:
            await self.deliver(doc["tenant_id"], doc["id"])
        return {"attempted": len(docs)}
