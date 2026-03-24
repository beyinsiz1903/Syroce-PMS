"""
Channel Manager — Unified Data Model API Router
================================================

REST endpoints for the optimized 9-collection model.
Prefix: /api/channel-manager/model/

Replaces the over-abstracted v2 connector/mapping/reconciliation endpoints
with a simpler, 2-provider-optimized API surface.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.security import get_current_user
from models.schemas import User

from . import unified_repository as repo
from .data_model import (
    CaseSeverity,
    CaseStatus,
    CaseType,
    ConnectionStatus,
    ConnectorProvider,
    ProviderConnection,
    RatePlanMapping,
    ReconciliationCase,
    RoomMapping,
)

logger = logging.getLogger("channel_manager.model_router")

router = APIRouter(
    prefix="/api/channel-manager/model",
    tags=["Channel Manager — Data Model"],
)


# ── Request Models ────────────────────────────────────────────────────

class CreateConnectionRequest(BaseModel):
    provider: str  # hotelrunner | exely
    property_id: str
    display_name: str = ""
    credentials: dict = Field(default_factory=dict)


class UpdateConnectionRequest(BaseModel):
    display_name: Optional[str] = None
    credentials: Optional[dict] = None
    status: Optional[str] = None


class CreateRoomMappingRequest(BaseModel):
    property_id: str
    provider: str
    pms_room_type_id: str
    pms_room_type_name: str = ""
    provider_room_code: str
    provider_room_id: str = ""


class CreateRatePlanMappingRequest(BaseModel):
    property_id: str
    provider: str
    pms_rate_plan_id: str
    pms_rate_plan_name: str = ""
    provider_rate_code: str
    provider_rate_id: str = ""


class CreateReconciliationCaseRequest(BaseModel):
    property_id: str
    provider: str
    case_type: str
    severity: str
    description: str = ""
    external_reservation_id: Optional[str] = None
    reservation_id: Optional[str] = None


class ResolveCaseRequest(BaseModel):
    resolution: str


class DismissCaseRequest(BaseModel):
    reason: str = ""


# ── Provider Connections ──────────────────────────────────────────────

@router.get("/connections")
async def list_connections(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    connections = await repo.get_connections_by_tenant(
        current_user.tenant_id, status,
    )
    return {"connections": connections, "count": len(connections)}


@router.post("/connections")
async def create_connection(
    req: CreateConnectionRequest,
    current_user: User = Depends(get_current_user),
):
    # Validate provider
    try:
        provider_enum = ConnectorProvider(req.provider)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider: {req.provider}. Must be 'hotelrunner' or 'exely'",
        )

    # Check for existing connection
    existing = await repo.get_connection_by_provider(
        current_user.tenant_id, req.property_id, req.provider,
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Connection for {req.provider} already exists for this property",
        )

    conn = ProviderConnection(
        tenant_id=current_user.tenant_id,
        property_id=req.property_id,
        provider=provider_enum,
        display_name=req.display_name or f"{req.provider.title()} Connection",
        credentials=req.credentials,
        created_by=current_user.id,
    )
    await repo.upsert_connection(conn.to_doc())
    return {"message": "Connection created", "connection": conn.to_doc()}


@router.get("/connections/{connection_id}")
async def get_connection(
    connection_id: str,
    current_user: User = Depends(get_current_user),
):
    conn = await repo.get_connection(current_user.tenant_id, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    # Mask credentials
    if "credentials" in conn:
        conn["credentials"] = {k: "***" for k in conn["credentials"]}
    return conn


@router.put("/connections/{connection_id}")
async def update_connection(
    connection_id: str,
    req: UpdateConnectionRequest,
    current_user: User = Depends(get_current_user),
):
    conn = await repo.get_connection(current_user.tenant_id, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    if req.display_name is not None:
        conn["display_name"] = req.display_name
    if req.credentials is not None:
        conn["credentials"] = req.credentials
    if req.status is not None:
        conn["status"] = req.status
    conn["updated_by"] = current_user.id
    await repo.upsert_connection(conn)
    return {"message": "Connection updated"}


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: str,
    current_user: User = Depends(get_current_user),
):
    deleted = await repo.delete_connection(current_user.tenant_id, connection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"message": "Connection deleted"}


@router.post("/connections/{connection_id}/activate")
async def activate_connection(
    connection_id: str,
    current_user: User = Depends(get_current_user),
):
    conn = await repo.get_connection(current_user.tenant_id, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    conn["status"] = ConnectionStatus.ACTIVE.value
    conn["updated_by"] = current_user.id
    await repo.upsert_connection(conn)
    return {"message": "Connection activated"}


@router.post("/connections/{connection_id}/pause")
async def pause_connection(
    connection_id: str,
    current_user: User = Depends(get_current_user),
):
    conn = await repo.get_connection(current_user.tenant_id, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    conn["status"] = ConnectionStatus.PAUSED.value
    conn["updated_by"] = current_user.id
    await repo.upsert_connection(conn)
    return {"message": "Connection paused"}


# ── Room Mappings ─────────────────────────────────────────────────────

@router.get("/room-mappings")
async def list_room_mappings(
    property_id: str,
    provider: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    mappings = await repo.get_room_mappings(
        current_user.tenant_id, property_id, provider,
    )
    return {"mappings": mappings, "count": len(mappings)}


@router.post("/room-mappings")
async def create_room_mapping(
    req: CreateRoomMappingRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        provider_enum = ConnectorProvider(req.provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {req.provider}")

    mapping = RoomMapping(
        tenant_id=current_user.tenant_id,
        property_id=req.property_id,
        provider=provider_enum,
        pms_room_type_id=req.pms_room_type_id,
        pms_room_type_name=req.pms_room_type_name,
        provider_room_code=req.provider_room_code,
        provider_room_id=req.provider_room_id,
    )
    await repo.upsert_room_mapping(mapping.to_doc())
    return {"message": "Room mapping created", "mapping": mapping.to_doc()}


@router.delete("/room-mappings/{mapping_id}")
async def delete_room_mapping(
    mapping_id: str,
    current_user: User = Depends(get_current_user),
):
    deleted = await repo.delete_room_mapping(current_user.tenant_id, mapping_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Room mapping not found")
    return {"message": "Room mapping deleted"}


# ── Rate Plan Mappings ────────────────────────────────────────────────

@router.get("/rate-plan-mappings")
async def list_rate_plan_mappings(
    property_id: str,
    provider: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    mappings = await repo.get_rate_plan_mappings(
        current_user.tenant_id, property_id, provider,
    )
    return {"mappings": mappings, "count": len(mappings)}


@router.post("/rate-plan-mappings")
async def create_rate_plan_mapping(
    req: CreateRatePlanMappingRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        provider_enum = ConnectorProvider(req.provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {req.provider}")

    mapping = RatePlanMapping(
        tenant_id=current_user.tenant_id,
        property_id=req.property_id,
        provider=provider_enum,
        pms_rate_plan_id=req.pms_rate_plan_id,
        pms_rate_plan_name=req.pms_rate_plan_name,
        provider_rate_code=req.provider_rate_code,
        provider_rate_id=req.provider_rate_id,
    )
    await repo.upsert_rate_plan_mapping(mapping.to_doc())
    return {"message": "Rate plan mapping created", "mapping": mapping.to_doc()}


@router.delete("/rate-plan-mappings/{mapping_id}")
async def delete_rate_plan_mapping(
    mapping_id: str,
    current_user: User = Depends(get_current_user),
):
    deleted = await repo.delete_rate_plan_mapping(current_user.tenant_id, mapping_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rate plan mapping not found")
    return {"message": "Rate plan mapping deleted"}


# ── Raw Channel Events ────────────────────────────────────────────────

@router.get("/raw-events")
async def list_raw_events(
    property_id: str,
    provider: Optional[str] = None,
    processed: Optional[bool] = None,
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
):
    events = await repo.get_raw_events(
        current_user.tenant_id, property_id, provider, processed, limit,
    )
    return {"events": events, "count": len(events)}


# ── Reservation Lineage ──────────────────────────────────────────────

@router.get("/lineage")
async def list_reservation_lineages(
    property_id: str,
    provider: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    lineages = await repo.get_reservation_lineages(
        current_user.tenant_id, property_id, provider, status, limit,
    )
    return {"lineages": lineages, "count": len(lineages)}


@router.get("/lineage/{lineage_id}")
async def get_reservation_lineage_detail(
    lineage_id: str,
    current_user: User = Depends(get_current_user),
):
    lineage = await repo.get_reservation_lineage(current_user.tenant_id, lineage_id)
    if not lineage:
        raise HTTPException(status_code=404, detail="Lineage record not found")
    return lineage


@router.get("/lineage/stats")
async def get_lineage_stats(
    property_id: str,
    provider: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    stats = await repo.get_lineage_stats(
        current_user.tenant_id, property_id, provider,
    )
    return stats


# ── Reconciliation Cases ─────────────────────────────────────────────

@router.get("/reconciliation/cases")
async def list_reconciliation_cases(
    property_id: Optional[str] = None,
    provider: Optional[str] = None,
    status: str = Query("open"),
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    cases = await repo.get_reconciliation_cases(
        current_user.tenant_id, property_id, provider, status, limit,
    )
    return {"cases": cases, "count": len(cases)}


@router.post("/reconciliation/cases")
async def create_case(
    req: CreateReconciliationCaseRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        provider_enum = ConnectorProvider(req.provider)
        case_type_enum = CaseType(req.case_type)
        severity_enum = CaseSeverity(req.severity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    case = ReconciliationCase(
        tenant_id=current_user.tenant_id,
        property_id=req.property_id,
        provider=provider_enum,
        case_type=case_type_enum,
        severity=severity_enum,
        description=req.description,
        external_reservation_id=req.external_reservation_id,
        reservation_id=req.reservation_id,
    )
    await repo.create_reconciliation_case(case.to_doc())
    return {"message": "Case created", "case": case.to_doc()}


@router.get("/reconciliation/cases/{case_id}")
async def get_case(
    case_id: str,
    current_user: User = Depends(get_current_user),
):
    case = await repo.get_reconciliation_case(current_user.tenant_id, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.post("/reconciliation/cases/{case_id}/resolve")
async def resolve_case(
    case_id: str,
    req: ResolveCaseRequest,
    current_user: User = Depends(get_current_user),
):
    case = await repo.get_reconciliation_case(current_user.tenant_id, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    await repo.update_reconciliation_case(case_id, {
        "status": CaseStatus.RESOLVED.value,
        "resolution": req.resolution,
        "resolved_by": current_user.id,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"message": "Case resolved"}


@router.post("/reconciliation/cases/{case_id}/dismiss")
async def dismiss_case(
    case_id: str,
    req: DismissCaseRequest,
    current_user: User = Depends(get_current_user),
):
    case = await repo.get_reconciliation_case(current_user.tenant_id, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    await repo.update_reconciliation_case(case_id, {
        "status": CaseStatus.DISMISSED.value,
        "dismiss_reason": req.reason,
        "resolved_by": current_user.id,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"message": "Case dismissed"}


@router.get("/reconciliation/summary")
async def get_summary(
    provider: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    summary = await repo.get_reconciliation_summary(
        current_user.tenant_id, provider,
    )
    return summary


# ── Data Model Overview ───────────────────────────────────────────────

@router.get("/schema")
async def get_data_model_schema():
    """Return the data model schema for documentation/debugging."""
    return {
        "model_version": "2.0",
        "providers": ["hotelrunner", "exely"],
        "collections": [
            {
                "name": "provider_connections",
                "description": "Provider credentials & connection config",
                "key_fields": ["tenant_id", "property_id", "provider"],
            },
            {
                "name": "room_mappings",
                "description": "PMS room type → provider room code mapping",
                "key_fields": ["tenant_id", "property_id", "provider", "pms_room_type_id"],
            },
            {
                "name": "rate_plan_mappings",
                "description": "PMS rate plan → provider rate code mapping",
                "key_fields": ["tenant_id", "property_id", "provider", "pms_rate_plan_id"],
            },
            {
                "name": "raw_channel_events",
                "description": "Immutable event store for webhook/pull/replay",
                "key_fields": ["tenant_id", "provider", "payload_hash"],
            },
            {
                "name": "reservation_lineage",
                "description": "Gold table: reservation tracking, versioning, reconciliation",
                "key_fields": ["tenant_id", "provider", "external_reservation_id"],
            },
            {
                "name": "ari_change_sets",
                "description": "ARI push pipeline state (coalesced changes)",
                "key_fields": ["tenant_id", "property_id", "provider", "coalescing_key"],
            },
            {
                "name": "ari_outbound_logs",
                "description": "Provider communication audit log",
                "key_fields": ["tenant_id", "property_id", "provider"],
            },
            {
                "name": "ari_drift_state",
                "description": "ARI parity / consistency tracking",
                "key_fields": ["tenant_id", "property_id", "provider", "room_type_code"],
            },
            {
                "name": "channel_reconciliation_cases",
                "description": "Discrepancy tracking between PMS and provider",
                "key_fields": ["tenant_id", "provider", "case_type", "status"],
            },
        ],
        "total_collections": 9,
    }
