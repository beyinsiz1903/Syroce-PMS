"""Connector CRUD, connection test, credential management endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.security import get_current_user
from models.schemas import User

from ...application.connector_service import ConnectorService
from ...infrastructure.credential_vault import CredentialVault
from ...infrastructure.rbac import enforce_credential_access
from ...domain.models.audit import IntegrationAuditLog, AuditAction

logger = logging.getLogger("channel_manager.routers.connector")

router = APIRouter(tags=["CM Connectors"])


class CreateConnectorRequest(BaseModel):
    provider: str = "hotelrunner"
    display_name: str
    property_id: str = ""
    credentials: dict = Field(default_factory=dict)
    sync_config: Optional[dict] = None


class UpdateCredentialsRequest(BaseModel):
    credentials: dict


class RotateCredentialsRequest(BaseModel):
    credentials: dict


class ConnectionTestStepResult(BaseModel):
    status: str
    latency_ms: int = 0
    error_code: Optional[str] = None
    message: str = ""


class ConnectionTestResponse(BaseModel):
    success: bool
    connector_id: str = ""
    provider: str = ""
    display_name: str = ""
    tested_at: str = ""
    total_latency_ms: int = 0
    summary: str = ""
    auth_status: Optional[ConnectionTestStepResult] = None
    property_access_status: Optional[ConnectionTestStepResult] = None
    inventory_read_status: Optional[ConnectionTestStepResult] = None
    rate_read_status: Optional[ConnectionTestStepResult] = None
    xml_connectivity_status: Optional[ConnectionTestStepResult] = None
    message: Optional[str] = None


# ─── Connector CRUD ──────────────────────────────────────────────

@router.get("/connectors")
async def list_connectors(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    connectors = await svc.list_connectors(current_user.tenant_id, status)
    return {"connectors": connectors, "count": len(connectors)}


@router.post("/connectors")
async def create_connector(
    req: CreateConnectorRequest,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    property_id = req.property_id or getattr(current_user, "property_id", "")
    try:
        result = await svc.create_connector(
            tenant_id=current_user.tenant_id,
            property_id=property_id,
            provider=req.provider,
            display_name=req.display_name,
            credentials=req.credentials,
            actor_id=current_user.id,
            sync_config=req.sync_config,
        )
        return {"message": "Connector created", "connector": result}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/connectors/{connector_id}")
async def get_connector(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    connector = await svc.get_connector(current_user.tenant_id, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    if "credentials" in connector:
        connector["credentials"] = {k: "***" for k in connector["credentials"]}
    return connector


@router.post("/connectors/{connector_id}/test", response_model=ConnectionTestResponse)
async def test_connector(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    result = await svc.test_connection(current_user.tenant_id, connector_id)
    return result


@router.post("/connectors/{connector_id}/activate")
async def activate_connector(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    result = await svc.activate_connector(current_user.tenant_id, connector_id, current_user.id)
    return {"message": "Connector activated", "connector": result}


@router.post("/connectors/{connector_id}/pause")
async def pause_connector(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    result = await svc.pause_connector(current_user.tenant_id, connector_id, current_user.id)
    return {"message": "Connector paused", "connector": result}


@router.put("/connectors/{connector_id}/credentials")
async def update_credentials(
    connector_id: str,
    req: UpdateCredentialsRequest,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    await svc.update_credentials(
        current_user.tenant_id, connector_id, req.credentials, current_user.id,
    )
    return {"message": "Credentials updated"}


@router.delete("/connectors/{connector_id}")
async def delete_connector(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    deleted = await svc.delete_connector(current_user.tenant_id, connector_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Connector not found")
    return {"message": "Connector deleted"}


# ─── Secure Credential Management ──────────────────────────────────

@router.put("/connectors/{connector_id}/credentials/secure")
async def update_credentials_secure(
    connector_id: str,
    req: UpdateCredentialsRequest,
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    await enforce_credential_access(
        current_user, "credential_update", connector_id, repo, require_write=True,
    )
    vault = CredentialVault()
    try:
        await vault.store_credentials(
            current_user.tenant_id, connector_id,
            req.credentials, current_user.id,
        )
        return {"message": "Credentials securely updated (AES-256-GCM)"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/connectors/{connector_id}/credentials/rotate")
async def rotate_credentials(
    connector_id: str,
    req: RotateCredentialsRequest,
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    await enforce_credential_access(
        current_user, "credential_rotation", connector_id, repo, require_write=True,
    )
    vault = CredentialVault()
    try:
        await vault.rotate_credentials(
            current_user.tenant_id, connector_id,
            req.credentials, current_user.id,
        )
        return {"message": "Credentials rotated successfully (AES-256-GCM)"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/connectors/{connector_id}/credentials/masked")
async def get_masked_credentials(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    await enforce_credential_access(
        current_user, "credential_view", connector_id, repo, require_write=False,
    )
    svc = ConnectorService()
    connector = await svc.get_connector(current_user.tenant_id, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    log = IntegrationAuditLog(
        tenant_id=current_user.tenant_id,
        connector_id=connector_id,
        action=AuditAction.CREDENTIAL_ACCESSED,
        actor_id=current_user.id,
        metadata={"action": "credential_view"},
    )
    await repo.create_audit_log(log.to_doc())

    vault = CredentialVault()
    masked = vault.mask_credentials(connector.get("credentials", {}))
    return {
        "connector_id": connector_id,
        "credentials": masked,
        "encrypted": connector.get("credentials_encrypted", False),
        "algorithm": connector.get("encryption_algorithm", "unknown"),
        "last_updated": connector.get("credentials_updated_at"),
        "last_rotated": connector.get("credentials_rotated_at"),
    }


@router.post("/connectors/{connector_id}/credentials/migrate")
async def migrate_credentials(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    await enforce_credential_access(
        current_user, "credential_update", connector_id, repo, require_write=True,
    )
    vault = CredentialVault()
    try:
        result = await vault.migrate_legacy_credentials(
            current_user.tenant_id, connector_id, current_user.id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
