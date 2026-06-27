"""Connector-facing lock-bridge API (on-prem connector <-> Syroce cloud).

The on-prem Brassco connector authenticates with its registered key
(``X-Lock-Bridge-Key``), pulls pending lock commands for its tenant, drives the
vendor DLL, then acknowledges each command. Auth is fail-closed: an unknown /
inactive / missing key is rejected with 401 and the tenant is resolved from the
stored connector record, never from client input. Responses carry no guest PII.
"""
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from core.database import db

from .service import ack_command, claim_commands, resolve_connector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal/lock-bridge", tags=["Lock Bridge"])


async def _require_connector(
    x_lock_bridge_key: str | None = Header(default=None, alias="X-Lock-Bridge-Key"),
) -> dict:
    record = await resolve_connector(db, x_lock_bridge_key)
    if not record:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"tenant_id": record.get("tenant_id"), "connector_id": record.get("id")}


class AckRequest(BaseModel):
    success: bool = Field(..., description="True if the physical card action succeeded")
    detail: str | None = Field(default=None, max_length=500, description="Result detail (no PII)")


@router.get("/commands")
async def pull_commands(
    limit: int = 20,
    connector: dict = Depends(_require_connector),
):
    """Claim and return up to ``limit`` claimable lock commands for this tenant."""
    commands = await claim_commands(
        db,
        tenant_id=connector["tenant_id"],
        connector_id=connector["connector_id"],
        limit=limit,
    )
    return {"commands": commands, "count": len(commands)}


@router.post("/commands/{command_id}/ack")
async def ack(
    command_id: str,
    payload: AckRequest,
    connector: dict = Depends(_require_connector),
):
    """Acknowledge a claimed command (done on success, re-queued on failure)."""
    ok = await ack_command(
        db,
        tenant_id=connector["tenant_id"],
        command_id=command_id,
        success=payload.success,
        detail=payload.detail,
        connector_id=connector["connector_id"],
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Command not found or already finalized")
    return {"acknowledged": True, "command_id": command_id, "success": payload.success}
