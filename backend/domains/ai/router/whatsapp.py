from fastapi import APIRouter, Query, HTTPException, Request
from fastapi.responses import PlainTextResponse
from domains.ai.whatsapp_service import get_whatsapp_concierge
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

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
