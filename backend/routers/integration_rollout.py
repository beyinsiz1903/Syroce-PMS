from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from domains.channel_manager.ari.repositories import COLL_ARI_DRIFT_STATE
from domains.channel_manager.credential_vault import get_masked_credentials
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/integration-rollout", tags=["integration-rollout"])


class RolloutConfig(BaseModel):
    finance_erp_enabled: bool = False
    channel_ari_enabled: bool = False
    drift_monitoring_enabled: bool = False


async def get_tenant_rollout_config(tenant_id: str) -> dict:
    doc = await db.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0, "integration_rollout": 1})
    return (doc or {}).get(
        "integration_rollout",
        {
            "finance_erp_enabled": False,
            "channel_ari_enabled": False,
            "drift_monitoring_enabled": False,
        },
    )


@router.get("/readiness")
async def get_readiness_status(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_system_settings")),
):
    tenant_id = current_user.tenant_id

    # 1. Check existing config
    config = await get_tenant_rollout_config(tenant_id)

    # 2. Check Finance credentials
    # Finance ERP property_id is "finance"
    finance_configured = False
    for provider in ["logo", "netsis"]:
        masked = await get_masked_credentials(tenant_id, provider, "finance")
        if masked:
            finance_configured = True
            break

    finance_status = "Ready" if finance_configured else "Blocked"

    # 3. Check Channel Manager credentials
    # Channel managers might use "" or "default"
    channel_configured = False
    for provider in ["hotelrunner", "exely"]:
        masked = await get_masked_credentials(tenant_id, provider, "")
        if not masked:
            masked = await get_masked_credentials(tenant_id, provider, "default")
        if masked:
            channel_configured = True
            break

    # 4. Check for SYSTEM drift states (Failures)
    system_drifts = await db[COLL_ARI_DRIFT_STATE].find({"tenant_id": tenant_id, "room_type_code": "SYSTEM"}, {"_id": 0, "provider": 1, "drift_type": 1}).to_list(100)

    channel_status = "Ready"
    if not channel_configured:
        channel_status = "Blocked"
    elif any(d["drift_type"] in ["provider_unavailable", "credentials_missing"] for d in system_drifts):
        channel_status = "Warning"

    return {
        "config": config,
        "finance": {
            "status": finance_status,
            "configured": finance_configured,
        },
        "channel": {"status": channel_status, "configured": channel_configured, "system_errors": system_drifts},
    }


@router.post("/config")
async def update_rollout_config(
    req: RolloutConfig,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_system_settings")),
):
    tenant_id = current_user.tenant_id

    await db.tenant_settings.update_one({"tenant_id": tenant_id}, {"$set": {"integration_rollout": req.model_dump()}}, upsert=True)

    return {"success": True, "config": req.model_dump()}
