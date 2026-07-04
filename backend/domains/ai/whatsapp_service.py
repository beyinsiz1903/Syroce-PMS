"""
WhatsApp Business AI Concierge Service
Handles Meta Webhook validation, parsing incoming messages, and generating AI responses.
"""
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from core.database import db
from domains.ai.service import get_ai_service

logger = logging.getLogger(__name__)

class WhatsAppConciergeService:
    def __init__(self):
        self.ai_service = get_ai_service()

    def verify_webhook(self, token: str, challenge: str, verify_token: str) -> str | None:
        """Verify the webhook subscription with Meta."""
        if token and token == verify_token:
            return challenge
        return None

    async def get_tenant_config(self, tenant_id: str) -> dict[str, Any] | None:
        """Fetch WhatsApp configuration for the tenant."""
        tenant = await db.tenants.find_one({"id": tenant_id})
        if not tenant:
            return None
        return tenant.get("whatsapp_config", {})

    async def process_incoming_message(self, tenant_id: str, message_data: dict) -> dict[str, Any]:
        """
        Process incoming WhatsApp message, generate AI response, and reply.
        Expected message_data structure depends on Meta's Webhook payload.
        We extract the first message.
        """
        try:
            # Parse WhatsApp Webhook Payload
            entry = message_data.get("entry", [])[0]
            changes = entry.get("changes", [])[0]
            value = changes.get("value", {})
            messages = value.get("messages", [])
            contacts = value.get("contacts", [])

            if not messages:
                return {"status": "ignored", "reason": "No messages in payload"}

            message = messages[0]
            phone = message.get("from")
            text_body = message.get("text", {}).get("body", "")

            guest_name = "Guest"
            if contacts:
                guest_name = contacts[0].get("profile", {}).get("name", "Guest")

            # Save incoming message
            conversation_id = __import__("uuid").uuid4().hex
            conversation = {
                "id": conversation_id,
                "tenant_id": tenant_id,
                "phone": phone,
                "guest_name": guest_name,
                "user_message": text_body,
                "ai_response": None,
                "action_taken": None,
                "answered": False,
                "created_at": datetime.now(UTC).isoformat(),
            }
            await db.ai_conversations.insert_one(conversation)

            # Generate AI Response
            ai_reply = await self._generate_ai_response(tenant_id, phone, guest_name, text_body)

            if ai_reply:
                # Update conversation
                await db.ai_conversations.update_one(
                    {"id": conversation_id},
                    {"$set": {"ai_response": ai_reply, "answered": True, "action_taken": "replied"}}
                )

                # Send reply via WhatsApp API
                await self._send_whatsapp_message(tenant_id, phone, ai_reply)
                return {"status": "success", "reply": ai_reply}

            return {"status": "failed", "reason": "No AI reply generated"}

        except Exception as e:
            logger.exception("[ai] Failed to process WhatsApp message")
            return {"status": "error", "message": str(e)}

    async def _generate_ai_response(self, tenant_id: str, phone: str, guest_name: str, message: str) -> str | None:
        """Generate response using AI Service."""
        try:
            # Fetch recent conversation history to provide context
            history_cursor = db.ai_conversations.find({"tenant_id": tenant_id, "phone": phone}).sort("created_at", -1).limit(5)
            history_docs = await history_cursor.to_list(length=5)
            history_docs.reverse()

            chat_history = []
            for doc in history_docs:
                if doc.get("user_message"):
                    chat_history.append({"role": "user", "content": doc["user_message"]})
                if doc.get("ai_response"):
                    chat_history.append({"role": "assistant", "content": doc["ai_response"]})

            system_message = f"""You are a professional, polite, and helpful AI concierge for a hotel.
You are chatting with a guest named {guest_name} on WhatsApp.
Provide concise, friendly answers. If you don't know the answer, politely inform them that you'll forward the request to the human reception."""

            chat = self.ai_service._create_chat(system_message=system_message, session_id=f"wa_{phone}")

            response = await chat.send_message(message, history=chat_history)
            return response
        except Exception:
            logger.exception("[ai] Error generating LLM response for WhatsApp")
            return None

    async def _send_whatsapp_message(self, tenant_id: str, phone: str, text: str) -> None:
        """Send message back to user via WhatsApp Cloud API."""
        config = await self.get_tenant_config(tenant_id)
        if not config:
            logger.warning(f"[ai] No WhatsApp config found for tenant {tenant_id}")
            return

        phone_number_id = config.get("phone_number_id")
        access_token = config.get("access_token")

        if not phone_number_id or not access_token:
            logger.warning(f"[ai] Incomplete WhatsApp config for tenant {tenant_id}")
            return

        url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": text},
        }

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[ai] Failed to send WhatsApp message to {phone}: {e}")

_whatsapp_concierge_instance = None
def get_whatsapp_concierge():
    global _whatsapp_concierge_instance
    if _whatsapp_concierge_instance is None:
        _whatsapp_concierge_instance = WhatsAppConciergeService()
    return _whatsapp_concierge_instance
