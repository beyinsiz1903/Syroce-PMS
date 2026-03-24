"""
Messaging Router - Provider management, template CRUD, sending, delivery logs.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/messaging-center", tags=["messaging-center"])

_db = None
_service = None


def _get_service():
    global _service, _db
    if _service is None:
        from server import db
        _db = db
        from modules.messaging.service import MessagingService
        _service = MessagingService(db)
    return _service


# ── Provider Config ──

@router.get("/providers")
async def list_providers(current_user: User = Depends(get_current_user)):
    svc = _get_service()
    configs = await svc.db.messaging_provider_configs.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0, "credentials_encrypted": 0}
    ).to_list(20)
    return {"providers": configs}


class ProviderConfigReq(BaseModel):
    provider_type: str
    credentials: dict
    is_sandbox: bool = False
    enabled: bool = True


@router.post("/providers")
async def create_provider(req: ProviderConfigReq, current_user: User = Depends(get_current_user)):
    from modules.messaging.models import new_provider_config
    doc = new_provider_config(current_user.tenant_id, req.provider_type, req.credentials, req.is_sandbox, req.enabled)
    svc = _get_service()
    await svc.db.messaging_provider_configs.insert_one(doc)
    doc.pop("_id", None)
    doc.pop("credentials_encrypted", None)
    return doc


class ProviderUpdateReq(BaseModel):
    credentials: Optional[dict] = None
    is_sandbox: Optional[bool] = None
    enabled: Optional[bool] = None


@router.put("/providers/{config_id}")
async def update_provider(config_id: str, req: ProviderUpdateReq,
                           current_user: User = Depends(get_current_user)):
    svc = _get_service()
    updates = {}
    if req.credentials is not None:
        updates["credentials_encrypted"] = req.credentials
    if req.is_sandbox is not None:
        updates["is_sandbox"] = req.is_sandbox
    if req.enabled is not None:
        updates["enabled"] = req.enabled
    from datetime import datetime, timezone
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await svc.db.messaging_provider_configs.update_one(
        {"id": config_id, "tenant_id": current_user.tenant_id},
        {"$set": updates},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Provider config not found")
    return {"success": True}


@router.post("/providers/health-check")
async def check_provider_health(current_user: User = Depends(get_current_user)):
    svc = _get_service()
    results = await svc.check_all_providers(current_user.tenant_id)
    return {"results": results}


# ── Templates ──

@router.get("/templates")
async def list_templates(current_user: User = Depends(get_current_user)):
    svc = _get_service()
    templates = await svc.db.messaging_templates.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).to_list(100)
    return {"templates": templates}


class TemplateReq(BaseModel):
    name: str
    category: str
    channel: str
    subject: Optional[str] = None
    body_template: str
    variables: List[str] = []


@router.post("/templates")
async def create_template(req: TemplateReq, current_user: User = Depends(get_current_user)):
    from modules.messaging.models import new_message_template
    doc = new_message_template(
        current_user.tenant_id, req.name, req.category, req.channel,
        req.subject, req.body_template, req.variables,
    )
    svc = _get_service()
    await svc.db.messaging_templates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/templates/{template_id}")
async def update_template(template_id: str, req: dict, current_user: User = Depends(get_current_user)):
    svc = _get_service()
    allowed = ["subject", "body_template", "variables", "is_active"]
    from datetime import datetime, timezone
    updates = {k: v for k, v in req.items() if k in allowed}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await svc.db.messaging_templates.update_one(
        {"id": template_id, "tenant_id": current_user.tenant_id}, {"$set": updates}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"success": True}


# ── Send ──

class SendReq(BaseModel):
    channel: str
    recipient: str
    template_id: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    variables: dict = {}
    booking_id: Optional[str] = None
    guest_id: Optional[str] = None
    property_id: Optional[str] = None
    use_case: Optional[str] = None


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


# ── Delivery Logs ──

@router.get("/delivery-logs")
async def get_delivery_logs(
    status: Optional[str] = None,
    channel: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    svc = _get_service()
    q = {"tenant_id": current_user.tenant_id}
    if status:
        q["status"] = status
    if channel:
        q["channel"] = channel
    logs = await svc.db.messaging_delivery_logs.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"logs": logs, "total": len(logs)}


# ── Metrics ──

@router.get("/metrics")
async def get_messaging_metrics(days: int = Query(7, ge=1, le=90),
                                 current_user: User = Depends(get_current_user)):
    svc = _get_service()
    return await svc.get_delivery_metrics(current_user.tenant_id, days)


# ── Consent ──

class ConsentReq(BaseModel):
    recipient: str
    channel: str
    status: str  # opt_in / opt_out


@router.post("/consent")
async def update_consent(req: ConsentReq, current_user: User = Depends(get_current_user)):
    svc = _get_service()
    import uuid
    from datetime import datetime, timezone
    await svc.db.messaging_consents.update_one(
        {"tenant_id": current_user.tenant_id, "recipient": req.recipient, "channel": req.channel},
        {"$set": {
            "status": req.status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": current_user.id,
        },
         "$setOnInsert": {
             "id": str(uuid.uuid4()),
             "tenant_id": current_user.tenant_id,
             "recipient": req.recipient,
             "channel": req.channel,
             "created_at": datetime.now(timezone.utc).isoformat(),
         }},
        upsert=True,
    )
    return {"success": True}


# ── Runtime Status ──

@router.get("/runtime-status")
async def get_runtime_status(current_user: User = Depends(get_current_user)):
    svc = _get_service()
    return svc.get_runtime_status()


@router.get("/retry-queue")
async def get_retry_queue_size(current_user: User = Depends(get_current_user)):
    svc = _get_service()
    size = await svc.get_retry_queue_size(current_user.tenant_id)
    return {"retry_queue_size": size}
