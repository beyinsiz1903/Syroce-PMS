"""
ARI Push Engine — MongoDB repositories.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from core.database import db

from .models import (
    COLL_ARI_CHANGE_SETS,
    COLL_ARI_DRIFT_STATE,
    COLL_ARI_EVENTS,
    COLL_ARI_OUTBOUND_LOGS,
    STATUS_PENDING,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def compute_delta_hash(payload: dict) -> str:
    """Hash payload only — used for internal coalescing/date-range merge."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def compute_outbound_delta_hash(
    provider: str,
    property_id: str,
    room_type_code: str,
    rate_plan_code: str,
    date_from: str,
    date_to: str,
    payload: dict,
) -> str:
    """
    Enriched hash for outbound idempotency, retry dedup, and drift comparison.
    Includes: provider, property_id, room_type, rate_plan, date_from, date_to, payload.
    """
    composite = {
        "provider": provider,
        "property_id": property_id,
        "room_type_code": room_type_code,
        "rate_plan_code": rate_plan_code or "",
        "date_from": str(date_from),
        "date_to": str(date_to),
        "payload": payload,
    }
    canonical = json.dumps(composite, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# ── ARI Events ───────────────────────────────────────────────────────


async def insert_ari_event(event: dict) -> str:
    event_id = event.get("id", str(uuid.uuid4()))
    doc = {
        "id": event_id,
        "tenant_id": event["tenant_id"],
        "property_id": event["property_id"],
        "source_service": event["source_service"],
        "event_type": event["event_type"],
        "room_type_code": event["room_type_code"],
        "rate_plan_code": event.get("rate_plan_code"),
        "date_from": str(event["date_from"]),
        "date_to": str(event["date_to"]),
        "payload": event["payload"],
        "actor_id": event.get("actor_id"),
        "correlation_id": event.get("correlation_id"),
        "target_provider": event.get("target_provider"),
        "created_at": event.get("created_at", _now_iso()),
    }
    await db[COLL_ARI_EVENTS].insert_one(doc)
    return event_id


async def get_ari_events(
    tenant_id: str,
    property_id: str,
    limit: int = 50,
    skip: int = 0,
    event_type: str | None = None,
) -> list[dict]:
    query: dict[str, Any] = {"tenant_id": tenant_id, "property_id": property_id}
    if event_type:
        query["event_type"] = event_type
    cursor = db[COLL_ARI_EVENTS].find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


# ── ARI Change Sets ──────────────────────────────────────────────────


async def upsert_change_set(cs: dict) -> str:
    """Upsert a change set by coalescing_key. Returns the change set id."""
    coalescing_key = cs["coalescing_key"]
    existing = await db[COLL_ARI_CHANGE_SETS].find_one(
        {"coalescing_key": coalescing_key, "status": {"$in": ["pending", "queued"]}},
        {"_id": 0, "id": 1},
    )
    now = _now_iso()
    if existing:
        await db[COLL_ARI_CHANGE_SETS].update_one(
            {"id": existing["id"]},
            {
                "$set": {
                    "compacted_payload": cs["compacted_payload"],
                    "provider_delta_hash": cs["provider_delta_hash"],
                    "date_from": cs["date_from"],
                    "date_to": cs["date_to"],
                    "updated_at": now,
                    "status": STATUS_PENDING,
                }
            },
        )
        return existing["id"]
    else:
        cs_id = str(uuid.uuid4())
        doc = {
            "id": cs_id,
            "tenant_id": cs["tenant_id"],
            "property_id": cs["property_id"],
            "provider": cs["provider"],
            "coalescing_key": coalescing_key,
            "room_type_code": cs["room_type_code"],
            "rate_plan_code": cs.get("rate_plan_code"),
            "date_from": cs["date_from"],
            "date_to": cs["date_to"],
            "change_scope": cs["change_scope"],
            "compacted_payload": cs["compacted_payload"],
            "provider_delta_hash": cs["provider_delta_hash"],
            "status": STATUS_PENDING,
            "outbound_change_id": str(uuid.uuid4()),
            "outbound_attempt_count": 0,
            "last_pushed_at": None,
            "last_provider_ack_at": None,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        }
        await db[COLL_ARI_CHANGE_SETS].insert_one(doc)
        return cs_id


async def get_pending_change_sets(
    tenant_id: str,
    provider: str | None = None,
    limit: int = 50,
) -> list[dict]:
    query: dict[str, Any] = {
        "tenant_id": tenant_id,
        "$or": [
            {"status": "pending"},
            {"status": "failed_retryable", "provider": {"$ne": "exely"}},
        ],
    }
    if provider:
        query["provider"] = provider
    cursor = db[COLL_ARI_CHANGE_SETS].find(query, {"_id": 0}).sort("created_at", 1).limit(limit)
    return await cursor.to_list(length=limit)


async def get_change_sets(
    tenant_id: str,
    property_id: str,
    status: str | None = None,
    provider: str | None = None,
    limit: int = 50,
    skip: int = 0,
) -> list[dict]:
    query: dict[str, Any] = {"tenant_id": tenant_id, "property_id": property_id}
    if status:
        query["status"] = status
    if provider:
        query["provider"] = provider
    cursor = db[COLL_ARI_CHANGE_SETS].find(query, {"_id": 0}).sort("updated_at", -1).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def update_change_set_status(
    cs_id: str,
    status: str,
    error: str | None = None,
    inc_attempt: bool = False,
) -> None:
    update: dict[str, Any] = {"$set": {"status": status, "updated_at": _now_iso()}}
    if status == "pushed":
        update["$set"]["last_pushed_at"] = _now_iso()
    if status == "acked":
        update["$set"]["last_provider_ack_at"] = _now_iso()
    if error:
        update["$set"]["last_error"] = error
    if inc_attempt:
        update.setdefault("$inc", {})["outbound_attempt_count"] = 1
    await db[COLL_ARI_CHANGE_SETS].update_one({"id": cs_id}, update)


async def ensure_current_ack_index(database) -> None:
    """Keep current-cell ACK reads bounded to one tenant/provider/room/scope."""
    await database[COLL_ARI_CHANGE_SETS].create_index(
        [("tenant_id", 1), ("provider", 1), ("property_id", 1),
         ("room_type_code", 1), ("change_scope", 1), ("last_provider_ack_at", -1)],
        partialFilterExpression={"status": "acked"},
        name="ix_ari_current_cell_ack",
    )


async def check_outbound_idempotency(
    provider: str, property_id: str, delta_hash: str, *, change_set: dict | None = None,
) -> bool:
    """Suppress an equal *current* state, never a historical A in A -> B -> A.

    Exely requires the full tenant/cell context. Its last successful overlapping
    write establishes the state; finding any matching hash in the past hour
    does not. Other providers retain their existing deduplication behavior.
    """
    from datetime import date, timedelta

    cutoff = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    if provider == "exely":
        cs = change_set or {}
        if (cs.get("provider") != provider or cs.get("property_id") != property_id
                or cs.get("provider_delta_hash") != delta_hash
                or not isinstance(cs.get("tenant_id"), str) or not cs["tenant_id"].strip()
                or not isinstance(cs.get("room_type_code"), str) or not cs["room_type_code"].strip()
                or cs.get("change_scope") not in {"availability", "rate", "restriction"}):
            raise ValueError("Exely deduplication requires an exact tenant-scoped change set")
        start, end = str(cs.get("date_from", "")), str(cs.get("date_to", ""))
        if date.fromisoformat(start) > date.fromisoformat(end):
            raise ValueError("Exely deduplication requires an ordered date interval")
        query = {
            "tenant_id": cs["tenant_id"], "provider": provider, "property_id": property_id,
            "room_type_code": cs["room_type_code"], "change_scope": cs["change_scope"],
            "date_from": {"$lte": end}, "date_to": {"$gte": start},
            "status": "acked", "last_provider_ack_at": {"$gte": cutoff},
        }
        # Availability is room inventory, even if published under another rate.
        # Prices and restrictions belong to their own mapped rate plan.
        if cs["change_scope"] != "availability":
            if not isinstance(cs.get("rate_plan_code"), str) or not cs["rate_plan_code"].strip():
                raise ValueError("Exely rate/restriction deduplication requires a rate plan")
            query["rate_plan_code"] = cs["rate_plan_code"]
        if cs["change_scope"] == "restriction":
            operation = (cs.get("compacted_payload") or {}).get("operation")
            if operation not in {"stop_sell", "min_los", "min_los_arrival", "max_los", "cta", "ctd"}:
                raise ValueError("Exely restriction deduplication requires an explicit operation")
            query["$or"] = [
                {"compacted_payload.operation": operation},
                {"compacted_payload.operation": {"$exists": False}},
            ]
        latest = await db[COLL_ARI_CHANGE_SETS].find_one(
            query, {"_id": 0}, sort=[("last_provider_ack_at", -1)],
        )
        if not latest or latest.get("provider_delta_hash") != delta_hash:
            return False
        # Tied ACK timestamps do not establish an order between different values.
        conflict = await db[COLL_ARI_CHANGE_SETS].find_one({
            **query, "provider_delta_hash": {"$ne": delta_hash},
            "last_provider_ack_at": {"$gte": latest["last_provider_ack_at"]},
        }, {"_id": 0, "id": 1})
        return conflict is None
    existing = await db[COLL_ARI_CHANGE_SETS].find_one(
        {
            "provider": provider,
            "property_id": property_id,
            "provider_delta_hash": delta_hash,
            "status": "acked",
            "last_provider_ack_at": {"$gte": cutoff},
        }
    )
    return existing is not None


# ── Outbound Logs ────────────────────────────────────────────────────


async def insert_outbound_log(log: dict) -> str:
    log_id = str(uuid.uuid4())
    doc = {
        "id": log_id,
        "tenant_id": log["tenant_id"],
        "property_id": log["property_id"],
        "provider": log["provider"],
        "outbound_change_id": log["outbound_change_id"],
        "provider_delta_hash": log.get("provider_delta_hash", ""),
        "endpoint_or_action": log.get("endpoint_or_action", ""),
        "request_payload": log.get("request_payload"),
        "response_payload": log.get("response_payload"),
        "status_code": log.get("status_code"),
        "success": log.get("success", False),
        "duration_ms": log.get("duration_ms", 0),
        "pushed_at": _now_iso(),
    }
    await db[COLL_ARI_OUTBOUND_LOGS].insert_one(doc)
    return log_id


async def get_outbound_logs(
    tenant_id: str,
    property_id: str,
    provider: str | None = None,
    limit: int = 50,
    skip: int = 0,
) -> list[dict]:
    query: dict[str, Any] = {"tenant_id": tenant_id, "property_id": property_id}
    if provider:
        query["provider"] = provider
    cursor = db[COLL_ARI_OUTBOUND_LOGS].find(query, {"_id": 0}).sort("pushed_at", -1).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


# ── Drift State ──────────────────────────────────────────────────────


async def upsert_drift_state(ds: dict) -> None:
    key = {
        "tenant_id": ds["tenant_id"],
        "property_id": ds["property_id"],
        "provider": ds["provider"],
        "room_type_code": ds["room_type_code"],
        "rate_plan_code": ds.get("rate_plan_code", ""),
        "date_from": ds["date_from"],
        "date_to": ds["date_to"],
    }
    now = _now_iso()
    await db[COLL_ARI_DRIFT_STATE].update_one(
        key,
        {
            "$set": {
                **ds,
                "last_checked_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
    )


async def clear_system_drift_state(tenant_id: str, property_id: str, provider: str) -> None:
    """Clear any SYSTEM level errors for this provider."""
    await db[COLL_ARI_DRIFT_STATE].delete_many({"tenant_id": tenant_id, "property_id": property_id, "provider": provider, "room_type_code": "SYSTEM"})


async def get_drift_states(
    tenant_id: str,
    property_id: str,
    provider: str | None = None,
    drift_only: bool = False,
    limit: int = 50,
    skip: int = 0,
) -> tuple[list[dict], int]:
    query: dict[str, Any] = {"tenant_id": tenant_id, "property_id": property_id}
    if provider:
        query["provider"] = provider
    if drift_only:
        query["drift_detected"] = True

    total = await db[COLL_ARI_DRIFT_STATE].count_documents(query)
    cursor = db[COLL_ARI_DRIFT_STATE].find(query, {"_id": 0}).sort("last_checked_at", -1).skip(skip).limit(limit)
    states = await cursor.to_list(length=limit)
    return states, total


# ── Per-Tenant Drift Mode ────────────────────────────────────────────

COLL_ARI_DRIFT_MODES = "ari_drift_modes"

DRIFT_MODE_NORMAL = "normal"
DRIFT_MODE_RECOVERY = "recovery"

DRIFT_CONFIG = {
    DRIFT_MODE_NORMAL: {"interval": 120, "scope": "changed"},
    DRIFT_MODE_RECOVERY: {"interval": 30, "scope": "full"},
}


async def get_tenant_drift_mode(tenant_id: str) -> dict:
    """Return tenant-scoped drift mode config. Defaults to normal."""
    doc = await db[COLL_ARI_DRIFT_MODES].find_one(
        {"tenant_id": tenant_id},
        {"_id": 0},
    )
    mode = (doc or {}).get("mode") or DRIFT_MODE_NORMAL
    if mode not in DRIFT_CONFIG:
        mode = DRIFT_MODE_NORMAL
    cfg = DRIFT_CONFIG[mode]
    return {"mode": mode, "interval": cfg["interval"], "scope": cfg["scope"]}


async def set_tenant_drift_mode(tenant_id: str, mode: str, actor_id: str | None = None) -> dict:
    """Persist tenant-scoped drift mode. Returns the new config."""
    if mode not in DRIFT_CONFIG:
        return {"error": f"Invalid mode: {mode}. Valid: {list(DRIFT_CONFIG.keys())}"}
    now = _now_iso()
    prev = await db[COLL_ARI_DRIFT_MODES].find_one({"tenant_id": tenant_id}, {"_id": 0, "mode": 1})
    await db[COLL_ARI_DRIFT_MODES].update_one(
        {"tenant_id": tenant_id},
        {
            "$set": {
                "tenant_id": tenant_id,
                "mode": mode,
                "actor_id": actor_id,
                "updated_at": now,
            }
        },
        upsert=True,
    )
    cfg = DRIFT_CONFIG[mode]
    return {
        "previous_mode": (prev or {}).get("mode") or DRIFT_MODE_NORMAL,
        "current_mode": mode,
        "mode": mode,
        "interval": cfg["interval"],
        "scope": cfg["scope"],
    }


async def get_ari_stats(tenant_id: str, property_id: str) -> dict:
    """Get aggregate ARI push stats."""
    pipeline_pending = [
        {"$match": {"tenant_id": tenant_id, "property_id": property_id, "status": {"$in": ["pending", "queued"]}}},
        {"$count": "count"},
    ]
    pipeline_acked = [
        {"$match": {"tenant_id": tenant_id, "property_id": property_id, "status": "acked"}},
        {"$count": "count"},
    ]
    pipeline_failed = [
        {"$match": {"tenant_id": tenant_id, "property_id": property_id, "status": {"$in": ["failed_retryable", "manual_review"]}}},
        {"$count": "count"},
    ]
    pipeline_drift = [
        {"$match": {"tenant_id": tenant_id, "property_id": property_id, "drift_detected": True}},
        {"$count": "count"},
    ]

    pending = await db[COLL_ARI_CHANGE_SETS].aggregate(pipeline_pending).to_list(1)
    acked = await db[COLL_ARI_CHANGE_SETS].aggregate(pipeline_acked).to_list(1)
    failed = await db[COLL_ARI_CHANGE_SETS].aggregate(pipeline_failed).to_list(1)
    drift = await db[COLL_ARI_DRIFT_STATE].aggregate(pipeline_drift).to_list(1)

    total_events = await db[COLL_ARI_EVENTS].count_documents({"tenant_id": tenant_id, "property_id": property_id})
    total_outbound = await db[COLL_ARI_OUTBOUND_LOGS].count_documents({"tenant_id": tenant_id, "property_id": property_id})

    return {
        "total_events": total_events,
        "pending_changes": pending[0]["count"] if pending else 0,
        "acked_changes": acked[0]["count"] if acked else 0,
        "failed_changes": failed[0]["count"] if failed else 0,
        "drift_count": drift[0]["count"] if drift else 0,
        "total_outbound_pushes": total_outbound,
    }


async def get_operational_metrics(tenant_id: str, property_id: str) -> dict:
    """
    Get operational metrics for the dashboard:
    - Provider health: ack_rate, error_rate, retry_rate
    - Performance: p50, p95, p99 push latency
    - Queue: queue depth, retry backlog, dead letter count
    """
    # Provider health metrics per provider
    provider_health = {}
    providers = await db[COLL_ARI_OUTBOUND_LOGS].distinct("provider", {"tenant_id": tenant_id, "property_id": property_id})

    for prov in providers:
        base_query = {"tenant_id": tenant_id, "property_id": property_id, "provider": prov}
        total = await db[COLL_ARI_OUTBOUND_LOGS].count_documents(base_query)
        success = await db[COLL_ARI_OUTBOUND_LOGS].count_documents({**base_query, "success": True})
        failed = total - success

        # Retry count from change sets
        retry_count = await db[COLL_ARI_CHANGE_SETS].count_documents(
            {
                "tenant_id": tenant_id,
                "property_id": property_id,
                "provider": prov,
                "status": "failed_retryable",
            }
        )

        provider_health[prov] = {
            "total_pushes": total,
            "ack_rate": round(success / total * 100, 1) if total > 0 else 0,
            "error_rate": round(failed / total * 100, 1) if total > 0 else 0,
            "retry_rate": round(retry_count / max(total, 1) * 100, 1),
        }

    # Performance metrics: latency percentiles
    latency_pipeline = [
        {"$match": {"tenant_id": tenant_id, "property_id": property_id, "duration_ms": {"$gt": 0}}},
        {"$sort": {"duration_ms": 1}},
        {
            "$group": {
                "_id": "$provider",
                "durations": {"$push": "$duration_ms"},
                "count": {"$sum": 1},
            }
        },
    ]
    latency_data = await db[COLL_ARI_OUTBOUND_LOGS].aggregate(latency_pipeline).to_list(10)

    performance = {}
    for ld in latency_data:
        prov = ld["_id"]
        durations = ld["durations"]
        count = ld["count"]
        performance[prov] = {
            "p50": durations[int(count * 0.5)] if count > 0 else 0,
            "p95": durations[int(count * 0.95)] if count > 1 else (durations[-1] if durations else 0),
            "p99": durations[int(count * 0.99)] if count > 1 else (durations[-1] if durations else 0),
            "sample_count": count,
        }

    # Queue stats
    queue_depth = await db[COLL_ARI_CHANGE_SETS].count_documents(
        {
            "tenant_id": tenant_id,
            "property_id": property_id,
            "status": {"$in": ["pending", "queued"]},
        }
    )
    retry_backlog = await db[COLL_ARI_CHANGE_SETS].count_documents(
        {
            "tenant_id": tenant_id,
            "property_id": property_id,
            "status": "failed_retryable",
        }
    )
    dead_letter_count = await db[COLL_ARI_CHANGE_SETS].count_documents(
        {
            "tenant_id": tenant_id,
            "property_id": property_id,
            "status": "manual_review",
        }
    )

    return {
        "provider_health": provider_health,
        "performance": performance,
        "queue": {
            "queue_depth": queue_depth,
            "retry_backlog": retry_backlog,
            "dead_letter_count": dead_letter_count,
        },
    }
