"""
ARI Push Engine — Pydantic schemas for API request/response.
"""

from datetime import date

from pydantic import BaseModel


class PublishARIEventRequest(BaseModel):
    tenant_id: str
    property_id: str
    source_service: str = "manual"
    event_type: str  # availability | rate | restriction
    room_type_code: str
    rate_plan_code: str | None = None
    date_from: date
    date_to: date
    payload: dict
    actor_id: str | None = None


class PushChangeSetsRequest(BaseModel):
    tenant_id: str
    provider: str | None = None
    limit: int = 50


class ResyncRequest(BaseModel):
    tenant_id: str
    property_id: str
    provider: str
    scope: str = "all"  # all | availability | rate | restriction


class DriftCheckRequest(BaseModel):
    tenant_id: str
    property_id: str
    provider: str


class ARIStatsResponse(BaseModel):
    total_events: int = 0
    pending_changes: int = 0
    acked_changes: int = 0
    failed_changes: int = 0
    drift_count: int = 0
    total_outbound_pushes: int = 0


class EngineStatsResponse(BaseModel):
    buffer: dict = {}
    rate_limiter: dict = {}
    registered_adapters: list[str] = []
    active_tenants: dict = {}
