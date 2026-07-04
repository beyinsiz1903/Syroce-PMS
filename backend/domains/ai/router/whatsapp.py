import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from domains.ai.whatsapp_service import get_whatsapp_concierge
from models.schemas import User

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

class WhatsAppOAuthRequest(BaseModel):
    access_token: str
    phone_number_id: str = None

@router.post("/oauth")
async def whatsapp_oauth_exchange(
    payload: WhatsAppOAuthRequest,
    current_user: User = Depends(get_current_user)
):
    import os
    import httpx
    import secrets
    
    app_id = os.getenv("FACEBOOK_APP_ID")
    app_secret = os.getenv("FACEBOOK_APP_SECRET")
    
    if not app_id or not app_secret:
        # Dev/Mock fallback
        mock_verify = "mock_verify_token_" + secrets.token_hex(8)
        mock_phone = payload.phone_number_id or "mock_phone_id"
        return {
            "message": "Mock OAuth successful, missing FACEBOOK_APP_ID in env",
            "access_token": payload.access_token,
            "verify_token": mock_verify,
            "phone_numbers": [
                {"id": mock_phone, "display_phone_number": "+90 555 123 4567", "verified_name": "Mock Hotel"}
            ]
        }
        
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://graph.facebook.com/v19.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": payload.access_token
            }
        )
        if response.status_code != 200:
            logger.error(f"Failed to exchange FB token: {response.text}")
            raise HTTPException(status_code=400, detail="Failed to authenticate with Facebook")
            
        data = response.json()
        long_lived_token = data.get("access_token")
        verify_token = "syroce_wh_" + secrets.token_urlsafe(16)
        
        # Now query for phone numbers:
        phone_numbers = []
        try:
            # 1. Get Businesses
            biz_res = await client.get(
                "https://graph.facebook.com/v19.0/me/businesses",
                params={"access_token": long_lived_token}
            )
            biz_data = biz_res.json()
            businesses = biz_data.get("data", [])
            
            for biz in businesses:
                biz_id = biz["id"]
                # 2. Get WABAs for business
                waba_res = await client.get(
                    f"https://graph.facebook.com/v19.0/{biz_id}/owned_whatsapp_business_accounts",
                    params={"access_token": long_lived_token}
                )
                waba_data = waba_res.json()
                wabas = waba_data.get("data", [])
                
                for waba in wabas:
                    waba_id = waba["id"]
                    # 3. Get Phone Numbers for WABA
                    pn_res = await client.get(
                        f"https://graph.facebook.com/v19.0/{waba_id}/phone_numbers",
                        params={"access_token": long_lived_token}
                    )
                    pn_data = pn_res.json()
                    for pn in pn_data.get("data", []):
                        phone_numbers.append({
                            "id": pn["id"],
                            "display_phone_number": pn.get("display_phone_number"),
                            "verified_name": pn.get("verified_name"),
                            "quality_rating": pn.get("quality_rating")
                        })
        except Exception as e:
            logger.error(f"Error fetching phone numbers: {e}")

        # Note: We do not save it to DB yet, we let frontend choose the phone number.
        return {
            "message": "Token exchanged successfully",
            "access_token": long_lived_token,
            "verify_token": verify_token,
            "phone_numbers": phone_numbers
        }

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
