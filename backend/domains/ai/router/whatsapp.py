from fastapi import APIRouter, Query, HTTPException, Request, Depends
from fastapi.responses import PlainTextResponse
from core.security import get_current_user
from models.schemas import User
from core.database import db
from pydantic import BaseModel
from domains.ai.whatsapp_service import get_whatsapp_concierge
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

class WhatsAppConfig(BaseModel):
    phone_number_id: str
    access_token: str
    verify_token: str

@router.get("/config")
async def get_whatsapp_config(current_user: User = Depends(get_current_user)):
    tenant = await db.tenants.find_one({"id": current_user.tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    config = tenant.get("whatsapp_config", {})
    # For security, we might mask the tokens in a real scenario, but we return them for the setup UI
    return {"config": config}

@router.post("/config")
async def save_whatsapp_config(
    payload: WhatsAppConfig,
    current_user: User = Depends(get_current_user)
):
    await db.tenants.update_one(
        {"id": current_user.tenant_id},
        {"$set": {"whatsapp_config": payload.dict()}}
    )
    return {"message": "WhatsApp configuration saved successfully"}

@router.get("/{tenant_id}/webhook")
async def verify_webhook(
    tenant_id: str,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    """
    Verify the Meta Webhook setup.
    """
    if hub_mode != "subscribe":
        raise HTTPException(status_code=400, detail="Invalid hub.mode")

    concierge = get_whatsapp_concierge()
    config = await concierge.get_tenant_config(tenant_id)
    if not config:
        raise HTTPException(status_code=404, detail="Tenant WhatsApp config not found")
        
    expected_token = config.get("verify_token")
    if not expected_token:
        raise HTTPException(status_code=500, detail="WhatsApp verify token not configured for tenant")

    challenge = concierge.verify_webhook(hub_verify_token, hub_challenge, expected_token)
    if challenge:
        return PlainTextResponse(content=challenge)
        
    raise HTTPException(status_code=403, detail="Invalid verify token")


@router.post("/{tenant_id}/webhook")
async def receive_message(tenant_id: str, payload: dict, request: Request):
    """
    Receive incoming messages from Meta WhatsApp webhook.
    """
    concierge = get_whatsapp_concierge()
    
    result = await concierge.process_incoming_message(tenant_id, payload)
    return result
