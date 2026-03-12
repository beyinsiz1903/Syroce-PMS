"""
Guest / Messaging — Service Layer
Orchestrates guest messaging, internal messaging, and templates.
No FastAPI dependencies.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import uuid
import logging

from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)


class MessagingService:
    """Business logic for guest and internal messaging."""

    def __init__(self):
        from core.database import db
        self._db = db

    async def send_message(self, ctx: OperationContext, data: dict) -> ServiceResult:
        msg = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            "guest_id": data["guest_id"],
            "booking_id": data.get("booking_id"),
            "message_type": data["message_type"],
            "recipient": data["recipient"],
            "message_content": data["message_content"],
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._db.sent_messages.insert_one(msg)
        msg_copy = {k: v for k, v in msg.items() if k != "_id"}
        return ServiceResult.success(msg_copy)

    async def get_guest_messages(self, ctx: OperationContext, guest_id: str) -> ServiceResult:
        messages = await self._db.sent_messages.find(
            {"tenant_id": ctx.tenant_id, "guest_id": guest_id}, {"_id": 0}
        ).sort("sent_at", -1).to_list(100)
        return ServiceResult.success({"messages": messages, "count": len(messages)})

    async def get_templates(self, ctx: OperationContext, message_type: Optional[str] = None) -> ServiceResult:
        query: Dict[str, Any] = {"tenant_id": ctx.tenant_id, "active": True}
        if message_type:
            query["message_type"] = message_type
        templates = await self._db.message_templates.find(query, {"_id": 0}).to_list(100)
        return ServiceResult.success({"templates": templates, "count": len(templates)})

    async def create_template(self, ctx: OperationContext, data: dict) -> ServiceResult:
        tpl = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            **data,
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._db.message_templates.insert_one(tpl)
        tpl_copy = {k: v for k, v in tpl.items() if k != "_id"}
        return ServiceResult.success(tpl_copy)

    async def send_internal_message(self, ctx: OperationContext, data: dict) -> ServiceResult:
        msg = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            "from_user_id": ctx.actor_id,
            "from_user_name": ctx.actor_email,
            "from_department": data.get("from_department", "general"),
            "to_user_id": data.get("to_user_id"),
            "to_user_name": data.get("to_user_name"),
            "to_department": data.get("to_department"),
            "message": data["message"],
            "priority": data.get("priority", "normal"),
            "message_type": data.get("message_type", "text"),
            "attachments": data.get("attachments", []),
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._db.internal_messages.insert_one(msg)
        msg_copy = {k: v for k, v in msg.items() if k != "_id"}
        return ServiceResult.success(msg_copy)

    async def get_internal_messages(
        self, ctx: OperationContext,
        department: Optional[str] = None,
        unread_only: bool = False,
    ) -> ServiceResult:
        query: Dict[str, Any] = {
            "tenant_id": ctx.tenant_id,
            "$or": [{"to_user_id": ctx.actor_id}, {"to_department": {"$exists": True}}, {"from_user_id": ctx.actor_id}],
        }
        if department:
            query["$or"] = [{"to_department": department}, {"from_department": department}]
        if unread_only:
            query["read"] = False

        messages = await self._db.internal_messages.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
        return ServiceResult.success({"messages": messages, "count": len(messages)})


messaging_service = MessagingService()
