"""
Timeline Router — Event Timeline API Endpoints
================================================
All /api/ops/timeline/* endpoints for tracing reservations,
ARI updates, and any entity through the entire pipeline.

Primary debug entry point: GET /api/ops/timeline/external/{external_id}
"Trace any reservation from OTA webhook to PMS booking in seconds."
"""
import logging

from fastapi import APIRouter, Query

from core.database import db

from .timeline_reader import get_timeline_reader

logger = logging.getLogger("controlplane.timeline_router")

router = APIRouter(prefix="/api/ops/timeline", tags=["Event Timeline"])


# ── Fixed routes first (before the catch-all) ──────────────────────

@router.get("/search")
async def search_timeline(
    tenant_id: str | None = Query(None),
    provider: str | None = Query(None),
    entity_type: str | None = Query(None),
    stage: str | None = Query(None),
    status: str | None = Query(None),
    from_time: str | None = Query(None, alias="from"),
    to_time: str | None = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    """Search timeline events with filters."""
    reader = get_timeline_reader()
    return await reader.search(
        tenant_id=tenant_id,
        provider=provider,
        entity_type=entity_type,
        stage=stage,
        status=status,
        from_time=from_time,
        to_time=to_time,
        limit=limit,
        skip=skip,
    )


@router.get("/gaps")
async def get_stuck_events(
    tenant_id: str | None = Query(None),
    max_age_minutes: int = Query(30, ge=5, le=1440),
    limit: int = Query(50, ge=1, le=200),
):
    """Events stuck in intermediate stages — pipeline bottleneck detection."""
    reader = get_timeline_reader()
    return await reader.get_stuck_events(
        tenant_id=tenant_id,
        max_age_minutes=max_age_minutes,
        limit=limit,
    )


@router.get("/correlation/{correlation_id}")
async def get_correlation_timeline(
    correlation_id: str,
    tenant_id: str | None = Query(None),
):
    """All events sharing a correlation ID — full flow trace."""
    reader = get_timeline_reader()
    return await reader.get_by_correlation(correlation_id, tenant_id=tenant_id)


@router.get("/external/{external_id}")
async def get_external_timeline(
    external_id: str,
    tenant_id: str | None = Query(None),
):
    """Lookup by OTA reservation ID — the #1 debug entry point.

    Example: GET /api/ops/timeline/external/12345
    Shows exactly where reservation 12345 is in the pipeline.
    """
    reader = get_timeline_reader()
    return await reader.get_by_external_id(external_id, tenant_id=tenant_id)


@router.get("/raw-payload/{correlation_id}")
async def get_raw_payload(
    correlation_id: str,
):
    """Retrieve the raw webhook payload for a given correlation_id.

    This is the exact bytes/JSON that the OTA sent, stored at webhook entry.
    Essential for debugging mapping errors, validation failures, and provider bugs.
    PII fields are masked by default — unmask requires super_admin + audit trail.
    """
    from security.pii_registry import mask_dict

    doc = await db.webhook_raw_payloads.find_one(
        {"correlation_id": correlation_id},
        {"_id": 0},
    )
    if not doc:
        return {"error": "Raw payload not found", "correlation_id": correlation_id}

    # Mask PII in raw payloads — ops context, no role-based unmask
    return mask_dict(doc, user_role="", context="api")


@router.get("/raw-payloads/by-external/{external_id}")
async def get_raw_payloads_by_external_id(
    external_id: str,
    limit: int = Query(10, ge=1, le=50),
):
    """Retrieve all raw webhook payloads for a given OTA reservation ID.

    Useful when multiple webhooks arrive for the same reservation
    (create, modify, cancel). PII fields are masked.
    """
    from security.pii_registry import mask_dict

    docs = await db.webhook_raw_payloads.find(
        {"external_id": external_id},
        {"_id": 0},
    ).sort("received_at", -1).to_list(limit)

    # Mask PII in all raw payloads
    masked_docs = [mask_dict(d, user_role="", context="api") for d in docs]
    return {"payloads": masked_docs, "count": len(masked_docs), "external_id": external_id}


# ── Catch-all route last ───────────────────────────────────────────

@router.get("/{entity_type}/{entity_id}")
async def get_entity_timeline(
    entity_type: str,
    entity_id: str,
    tenant_id: str | None = Query(None),
):
    """Full timeline for an entity (e.g., reservation/booking-uuid)."""
    reader = get_timeline_reader()
    return await reader.get_by_entity(entity_type, entity_id, tenant_id=tenant_id)
