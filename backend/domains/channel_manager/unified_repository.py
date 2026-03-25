"""
Channel Manager — Unified Repository for 9-Collection Data Model
================================================================

Single repository that handles all CRUD for the optimized model.
All queries enforce tenant isolation. All responses exclude _id.
"""
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from core.database import db

from .data_model import (
    COLL_PROVIDER_CONNECTIONS,
    COLL_RATE_PLAN_MAPPINGS,
    COLL_RAW_CHANNEL_EVENTS,
    COLL_RECONCILIATION_CASES,
    COLL_RESERVATION_LINEAGE,
    COLL_ROOM_MAPPINGS,
)

logger = logging.getLogger("channel_manager.unified_repository")

_NO_ID = {"_id": 0}


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ══════════════════════════════════════════════════════════════════════
# 1. PROVIDER CONNECTIONS
# ══════════════════════════════════════════════════════════════════════

async def get_connection(tenant_id: str, connection_id: str) -> dict | None:
    return await db[COLL_PROVIDER_CONNECTIONS].find_one(
        {"tenant_id": tenant_id, "id": connection_id}, _NO_ID,
    )


async def get_connections_by_tenant(
    tenant_id: str, status: str | None = None,
) -> list[dict]:
    q: dict[str, Any] = {"tenant_id": tenant_id}
    if status:
        q["status"] = status
    return await db[COLL_PROVIDER_CONNECTIONS].find(q, _NO_ID).to_list(100)


async def get_active_connections(
    tenant_id: str, property_id: str,
) -> list[dict]:
    return await db[COLL_PROVIDER_CONNECTIONS].find(
        {"tenant_id": tenant_id, "property_id": property_id, "status": "active"},
        _NO_ID,
    ).to_list(10)


async def upsert_connection(doc: dict) -> None:
    doc["updated_at"] = _now()
    await db[COLL_PROVIDER_CONNECTIONS].replace_one(
        {"tenant_id": doc["tenant_id"], "id": doc["id"]},
        doc, upsert=True,
    )


async def delete_connection(tenant_id: str, connection_id: str) -> bool:
    r = await db[COLL_PROVIDER_CONNECTIONS].delete_one(
        {"tenant_id": tenant_id, "id": connection_id},
    )
    return r.deleted_count > 0


async def get_connection_by_provider(
    tenant_id: str, property_id: str, provider: str,
) -> dict | None:
    return await db[COLL_PROVIDER_CONNECTIONS].find_one(
        {"tenant_id": tenant_id, "property_id": property_id, "provider": provider},
        _NO_ID,
    )


# ══════════════════════════════════════════════════════════════════════
# 2. ROOM MAPPINGS
# ══════════════════════════════════════════════════════════════════════

async def get_room_mappings(
    tenant_id: str, property_id: str, provider: str | None = None,
) -> list[dict]:
    q: dict[str, Any] = {"tenant_id": tenant_id, "property_id": property_id}
    if provider:
        q["provider"] = provider
    return await db[COLL_ROOM_MAPPINGS].find(q, _NO_ID).to_list(500)


async def get_room_mapping(tenant_id: str, mapping_id: str) -> dict | None:
    return await db[COLL_ROOM_MAPPINGS].find_one(
        {"tenant_id": tenant_id, "id": mapping_id}, _NO_ID,
    )


async def upsert_room_mapping(doc: dict) -> None:
    doc["updated_at"] = _now()
    await db[COLL_ROOM_MAPPINGS].replace_one(
        {"tenant_id": doc["tenant_id"], "id": doc["id"]},
        doc, upsert=True,
    )


async def delete_room_mapping(tenant_id: str, mapping_id: str) -> bool:
    r = await db[COLL_ROOM_MAPPINGS].delete_one(
        {"tenant_id": tenant_id, "id": mapping_id},
    )
    return r.deleted_count > 0


async def find_room_mapping_by_pms(
    tenant_id: str, property_id: str, provider: str, pms_room_type_id: str,
) -> dict | None:
    return await db[COLL_ROOM_MAPPINGS].find_one(
        {
            "tenant_id": tenant_id,
            "property_id": property_id,
            "provider": provider,
            "pms_room_type_id": pms_room_type_id,
            "is_active": True,
        },
        _NO_ID,
    )


async def find_room_mapping_by_provider(
    tenant_id: str, property_id: str, provider: str, provider_room_code: str,
) -> dict | None:
    return await db[COLL_ROOM_MAPPINGS].find_one(
        {
            "tenant_id": tenant_id,
            "property_id": property_id,
            "provider": provider,
            "provider_room_code": provider_room_code,
            "is_active": True,
        },
        _NO_ID,
    )


# ══════════════════════════════════════════════════════════════════════
# 3. RATE PLAN MAPPINGS
# ══════════════════════════════════════════════════════════════════════

async def get_rate_plan_mappings(
    tenant_id: str, property_id: str, provider: str | None = None,
) -> list[dict]:
    q: dict[str, Any] = {"tenant_id": tenant_id, "property_id": property_id}
    if provider:
        q["provider"] = provider
    return await db[COLL_RATE_PLAN_MAPPINGS].find(q, _NO_ID).to_list(500)


async def get_rate_plan_mapping(tenant_id: str, mapping_id: str) -> dict | None:
    return await db[COLL_RATE_PLAN_MAPPINGS].find_one(
        {"tenant_id": tenant_id, "id": mapping_id}, _NO_ID,
    )


async def upsert_rate_plan_mapping(doc: dict) -> None:
    doc["updated_at"] = _now()
    await db[COLL_RATE_PLAN_MAPPINGS].replace_one(
        {"tenant_id": doc["tenant_id"], "id": doc["id"]},
        doc, upsert=True,
    )


async def delete_rate_plan_mapping(tenant_id: str, mapping_id: str) -> bool:
    r = await db[COLL_RATE_PLAN_MAPPINGS].delete_one(
        {"tenant_id": tenant_id, "id": mapping_id},
    )
    return r.deleted_count > 0


async def find_rate_plan_mapping_by_pms(
    tenant_id: str, property_id: str, provider: str, pms_rate_plan_id: str,
) -> dict | None:
    return await db[COLL_RATE_PLAN_MAPPINGS].find_one(
        {
            "tenant_id": tenant_id,
            "property_id": property_id,
            "provider": provider,
            "pms_rate_plan_id": pms_rate_plan_id,
            "is_active": True,
        },
        _NO_ID,
    )


async def find_rate_plan_mapping_by_provider(
    tenant_id: str, property_id: str, provider: str, provider_rate_code: str,
) -> dict | None:
    return await db[COLL_RATE_PLAN_MAPPINGS].find_one(
        {
            "tenant_id": tenant_id,
            "property_id": property_id,
            "provider": provider,
            "provider_rate_code": provider_rate_code,
            "is_active": True,
        },
        _NO_ID,
    )


# ══════════════════════════════════════════════════════════════════════
# 4. RAW CHANNEL EVENTS (Ingest Pipeline)
# ══════════════════════════════════════════════════════════════════════

async def insert_raw_event(doc: dict) -> str:
    event_id = doc.get("id", str(uuid.uuid4()))
    doc["id"] = event_id
    await db[COLL_RAW_CHANNEL_EVENTS].insert_one(doc)
    return event_id


async def get_raw_events(
    tenant_id: str, property_id: str,
    provider: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    q: dict[str, Any] = {"tenant_id": tenant_id, "property_id": property_id}
    if provider:
        q["provider"] = provider
    if status:
        q["processing_status"] = status
    return await db[COLL_RAW_CHANNEL_EVENTS].find(
        q, _NO_ID,
    ).sort("received_at", -1).limit(limit).to_list(limit)


async def get_pending_raw_events(limit: int = 100) -> list[dict]:
    """Get all pending events across all tenants for the ingest processor."""
    return await db[COLL_RAW_CHANNEL_EVENTS].find(
        {"processing_status": "pending"},
        _NO_ID,
    ).sort("received_at", 1).limit(limit).to_list(limit)


async def update_raw_event_status(
    event_id: str, status: str, error: str | None = None,
) -> None:
    update: dict[str, Any] = {
        "processing_status": status,
        "processed_at": _now(),
    }
    if error:
        update["processing_error"] = error
    await db[COLL_RAW_CHANNEL_EVENTS].update_one(
        {"id": event_id}, {"$set": update},
    )


async def check_provider_event_exists(
    tenant_id: str, provider: str, provider_event_id: str,
) -> bool:
    """Duplicate detection: check if this provider_event_id already processed."""
    existing = await db[COLL_RAW_CHANNEL_EVENTS].find_one(
        {
            "tenant_id": tenant_id,
            "provider": provider,
            "provider_event_id": provider_event_id,
            "processing_status": {"$in": ["processed", "duplicate"]},
        },
    )
    return existing is not None


async def check_payload_hash_exists(
    tenant_id: str, provider: str, external_reservation_id: str, payload_hash: str,
) -> bool:
    """Check if we already have a processed event with same hash for same reservation."""
    existing = await db[COLL_RAW_CHANNEL_EVENTS].find_one(
        {
            "tenant_id": tenant_id,
            "provider": provider,
            "external_reservation_id": external_reservation_id,
            "payload_hash": payload_hash,
            "processing_status": "processed",
        },
    )
    return existing is not None


async def get_failed_events(tenant_id: str | None = None, limit: int = 50) -> list[dict]:
    """Get failed events for replay."""
    q: dict[str, Any] = {"processing_status": "failed"}
    if tenant_id:
        q["tenant_id"] = tenant_id
    return await db[COLL_RAW_CHANNEL_EVENTS].find(
        q, _NO_ID,
    ).sort("received_at", 1).limit(limit).to_list(limit)


async def get_raw_event_stats(tenant_id: str, property_id: str) -> dict[str, Any]:
    """Get event processing statistics."""
    pipeline = [
        {"$match": {"tenant_id": tenant_id, "property_id": property_id}},
        {"$group": {"_id": "$processing_status", "count": {"$sum": 1}}},
    ]
    stats: dict[str, int] = {}
    async for doc in db[COLL_RAW_CHANNEL_EVENTS].aggregate(pipeline):
        stats[doc["_id"]] = doc["count"]
    return {
        "total": sum(stats.values()),
        "pending": stats.get("pending", 0),
        "processed": stats.get("processed", 0),
        "failed": stats.get("failed", 0),
        "duplicate": stats.get("duplicate", 0),
        "stale": stats.get("stale", 0),
    }


# ══════════════════════════════════════════════════════════════════════
# 5. RESERVATION LINEAGE
# ══════════════════════════════════════════════════════════════════════

async def upsert_reservation_lineage(doc: dict) -> str:
    doc["updated_at"] = _now()
    existing = await db[COLL_RESERVATION_LINEAGE].find_one(
        {
            "tenant_id": doc["tenant_id"],
            "provider": doc["provider"],
            "external_reservation_id": doc["external_reservation_id"],
        },
        {"_id": 0, "id": 1, "version": 1},
    )
    if existing:
        doc["version"] = existing.get("version", 1) + 1
        await db[COLL_RESERVATION_LINEAGE].update_one(
            {"id": existing["id"]}, {"$set": doc},
        )
        return existing["id"]
    else:
        lineage_id = doc.get("id", str(uuid.uuid4()))
        doc["id"] = lineage_id
        doc["version"] = 1
        await db[COLL_RESERVATION_LINEAGE].insert_one(doc)
        return lineage_id


async def get_reservation_lineage(
    tenant_id: str, lineage_id: str,
) -> dict | None:
    return await db[COLL_RESERVATION_LINEAGE].find_one(
        {"tenant_id": tenant_id, "id": lineage_id}, _NO_ID,
    )


async def get_lineage_by_external_id(
    tenant_id: str, provider: str, external_reservation_id: str,
) -> dict | None:
    return await db[COLL_RESERVATION_LINEAGE].find_one(
        {
            "tenant_id": tenant_id,
            "provider": provider,
            "external_reservation_id": external_reservation_id,
        },
        _NO_ID,
    )


async def get_reservation_lineages(
    tenant_id: str, property_id: str,
    provider: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    q: dict[str, Any] = {"tenant_id": tenant_id, "property_id": property_id}
    if provider:
        q["provider"] = provider
    if status:
        q["status"] = status
    return await db[COLL_RESERVATION_LINEAGE].find(
        q, _NO_ID,
    ).sort("updated_at", -1).limit(limit).to_list(limit)


async def get_unreconciled_lineages(
    tenant_id: str, property_id: str, provider: str | None = None,
) -> list[dict]:
    q: dict[str, Any] = {
        "tenant_id": tenant_id,
        "property_id": property_id,
        "reconciled": False,
    }
    if provider:
        q["provider"] = provider
    return await db[COLL_RESERVATION_LINEAGE].find(
        q, _NO_ID,
    ).sort("created_at", -1).to_list(500)


async def get_lineage_stats(
    tenant_id: str, property_id: str, provider: str | None = None,
) -> dict[str, Any]:
    q: dict[str, Any] = {"tenant_id": tenant_id, "property_id": property_id}
    if provider:
        q["provider"] = provider
    pipeline = [
        {"$match": q},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    stats: dict[str, int] = {}
    async for doc in db[COLL_RESERVATION_LINEAGE].aggregate(pipeline):
        stats[doc["_id"]] = doc["count"]
    total = sum(stats.values())
    return {"total": total, "by_status": stats}


# ══════════════════════════════════════════════════════════════════════
# 9. CHANNEL RECONCILIATION CASES
# ══════════════════════════════════════════════════════════════════════

async def create_reconciliation_case(doc: dict) -> str:
    case_id = doc.get("id", str(uuid.uuid4()))
    doc["id"] = case_id
    await db[COLL_RECONCILIATION_CASES].insert_one(doc)
    return case_id


async def get_reconciliation_cases(
    tenant_id: str, property_id: str | None = None,
    provider: str | None = None,
    status: str | None = "open",
    limit: int = 100,
) -> list[dict]:
    q: dict[str, Any] = {"tenant_id": tenant_id}
    if property_id:
        q["property_id"] = property_id
    if provider:
        q["provider"] = provider
    if status:
        q["status"] = status
    return await db[COLL_RECONCILIATION_CASES].find(
        q, _NO_ID,
    ).sort("created_at", -1).limit(limit).to_list(limit)


async def get_reconciliation_case(
    tenant_id: str, case_id: str,
) -> dict | None:
    return await db[COLL_RECONCILIATION_CASES].find_one(
        {"tenant_id": tenant_id, "id": case_id}, _NO_ID,
    )


async def update_reconciliation_case(case_id: str, updates: dict) -> None:
    updates["updated_at"] = _now()
    await db[COLL_RECONCILIATION_CASES].update_one(
        {"id": case_id}, {"$set": updates},
    )


async def get_reconciliation_summary(
    tenant_id: str, provider: str | None = None,
) -> dict[str, Any]:
    q: dict[str, Any] = {
        "tenant_id": tenant_id,
        "status": {"$in": ["open", "investigating"]},
    }
    if provider:
        q["provider"] = provider
    pipeline = [
        {"$match": q},
        {"$group": {
            "_id": {"case_type": "$case_type", "severity": "$severity"},
            "count": {"$sum": 1},
        }},
    ]
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    total = 0
    async for doc in db[COLL_RECONCILIATION_CASES].aggregate(pipeline):
        ct = doc["_id"]["case_type"]
        sev = doc["_id"]["severity"]
        cnt = doc["count"]
        by_type[ct] = by_type.get(ct, 0) + cnt
        by_severity[sev] = by_severity.get(sev, 0) + cnt
        total += cnt
    return {"total_open": total, "by_type": by_type, "by_severity": by_severity}


# ══════════════════════════════════════════════════════════════════════
# INDEX SETUP
# ══════════════════════════════════════════════════════════════════════

async def ensure_indexes() -> None:
    """Create optimal indexes for the 9-collection model."""
    # Provider connections
    await db[COLL_PROVIDER_CONNECTIONS].create_index(
        [("tenant_id", 1), ("property_id", 1), ("provider", 1)], unique=True,
    )
    await db[COLL_PROVIDER_CONNECTIONS].create_index([("tenant_id", 1), ("status", 1)])

    # Room mappings
    await db[COLL_ROOM_MAPPINGS].create_index(
        [("tenant_id", 1), ("property_id", 1), ("provider", 1), ("pms_room_type_id", 1)],
        unique=True,
    )
    await db[COLL_ROOM_MAPPINGS].create_index(
        [("tenant_id", 1), ("property_id", 1), ("provider", 1), ("provider_room_code", 1)],
    )

    # Rate plan mappings
    await db[COLL_RATE_PLAN_MAPPINGS].create_index(
        [("tenant_id", 1), ("property_id", 1), ("provider", 1), ("pms_rate_plan_id", 1)],
        unique=True,
    )

    # Raw channel events (ingest pipeline)
    await db[COLL_RAW_CHANNEL_EVENTS].create_index(
        [("tenant_id", 1), ("provider", 1), ("provider_event_id", 1)],
    )
    await db[COLL_RAW_CHANNEL_EVENTS].create_index(
        [("processing_status", 1), ("received_at", 1)],
    )
    await db[COLL_RAW_CHANNEL_EVENTS].create_index(
        [("tenant_id", 1), ("provider", 1), ("external_reservation_id", 1), ("payload_hash", 1)],
    )
    await db[COLL_RAW_CHANNEL_EVENTS].create_index(
        [("tenant_id", 1), ("property_id", 1), ("received_at", -1)],
    )

    # Reservation lineage
    await db[COLL_RESERVATION_LINEAGE].create_index(
        [("tenant_id", 1), ("provider", 1), ("external_reservation_id", 1)],
        unique=True,
    )
    await db[COLL_RESERVATION_LINEAGE].create_index(
        [("tenant_id", 1), ("property_id", 1), ("status", 1)],
    )
    await db[COLL_RESERVATION_LINEAGE].create_index(
        [("tenant_id", 1), ("reconciled", 1)],
    )

    # Reconciliation cases
    await db[COLL_RECONCILIATION_CASES].create_index(
        [("tenant_id", 1), ("provider", 1), ("status", 1)],
    )
    await db[COLL_RECONCILIATION_CASES].create_index(
        [("tenant_id", 1), ("severity", 1), ("created_at", -1)],
    )
    await db[COLL_RECONCILIATION_CASES].create_index(
        [("tenant_id", 1), ("provider", 1), ("external_reservation_id", 1), ("case_type", 1), ("status", 1)],
    )
    await db[COLL_RECONCILIATION_CASES].create_index(
        [("tenant_id", 1), ("case_type", 1), ("status", 1)],
    )

    # Monitoring alerts
    from domains.channel_manager.monitoring.models import COLL_MONITORING_ALERTS
    await db[COLL_MONITORING_ALERTS].create_index(
        [("alert_type", 1), ("provider", 1), ("status", 1)],
    )
    await db[COLL_MONITORING_ALERTS].create_index(
        [("status", 1), ("severity", 1), ("created_at", -1)],
    )

    logger.info("9-collection indexes created successfully")
