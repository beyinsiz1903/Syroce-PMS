"""
ARI Push Engine — MongoDB repositories.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import db
from .models import (
    COLL_ARI_EVENTS, COLL_ARI_CHANGE_SETS,
    COLL_ARI_OUTBOUND_LOGS, COLL_ARI_DRIFT_STATE,
    STATUS_PENDING,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_delta_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
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
        "created_at": event.get("created_at", _now_iso()),
    }
    await db[COLL_ARI_EVENTS].insert_one(doc)
    return event_id


async def get_ari_events(
    tenant_id: str, property_id: str,
    limit: int = 50, skip: int = 0,
    event_type: Optional[str] = None,
) -> List[dict]:
    query: Dict[str, Any] = {"tenant_id": tenant_id, "property_id": property_id}
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
            {"$set": {
                "compacted_payload": cs["compacted_payload"],
                "provider_delta_hash": cs["provider_delta_hash"],
                "date_from": cs["date_from"],
                "date_to": cs["date_to"],
                "updated_at": now,
                "status": STATUS_PENDING,
            }},
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
    tenant_id: str, provider: Optional[str] = None, limit: int = 50,
) -> List[dict]:
    query: Dict[str, Any] = {"tenant_id": tenant_id, "status": {"$in": ["pending", "failed_retryable"]}}
    if provider:
        query["provider"] = provider
    cursor = db[COLL_ARI_CHANGE_SETS].find(query, {"_id": 0}).sort("created_at", 1).limit(limit)
    return await cursor.to_list(length=limit)


async def get_change_sets(
    tenant_id: str, property_id: str,
    status: Optional[str] = None, provider: Optional[str] = None,
    limit: int = 50, skip: int = 0,
) -> List[dict]:
    query: Dict[str, Any] = {"tenant_id": tenant_id, "property_id": property_id}
    if status:
        query["status"] = status
    if provider:
        query["provider"] = provider
    cursor = db[COLL_ARI_CHANGE_SETS].find(query, {"_id": 0}).sort("updated_at", -1).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def update_change_set_status(
    cs_id: str, status: str,
    error: Optional[str] = None,
    inc_attempt: bool = False,
) -> None:
    update: Dict[str, Any] = {"$set": {"status": status, "updated_at": _now_iso()}}
    if status == "pushed":
        update["$set"]["last_pushed_at"] = _now_iso()
    if status == "acked":
        update["$set"]["last_provider_ack_at"] = _now_iso()
    if error:
        update["$set"]["last_error"] = error
    if inc_attempt:
        update.setdefault("$inc", {})["outbound_attempt_count"] = 1
    await db[COLL_ARI_CHANGE_SETS].update_one({"id": cs_id}, update)


async def check_outbound_idempotency(provider: str, property_id: str, delta_hash: str) -> bool:
    """Return True if this exact delta was already pushed recently (within last hour)."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    existing = await db[COLL_ARI_CHANGE_SETS].find_one({
        "provider": provider,
        "property_id": property_id,
        "provider_delta_hash": delta_hash,
        "status": "acked",
        "last_provider_ack_at": {"$gte": cutoff},
    })
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
    tenant_id: str, property_id: str,
    provider: Optional[str] = None,
    limit: int = 50, skip: int = 0,
) -> List[dict]:
    query: Dict[str, Any] = {"tenant_id": tenant_id, "property_id": property_id}
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
        {"$set": {
            **ds,
            "last_checked_at": now,
            "updated_at": now,
        }},
        upsert=True,
    )


async def get_drift_states(
    tenant_id: str, property_id: str,
    provider: Optional[str] = None,
    drift_only: bool = False,
    limit: int = 50,
) -> List[dict]:
    query: Dict[str, Any] = {"tenant_id": tenant_id, "property_id": property_id}
    if provider:
        query["provider"] = provider
    if drift_only:
        query["drift_detected"] = True
    cursor = db[COLL_ARI_DRIFT_STATE].find(query, {"_id": 0}).sort("last_checked_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


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
