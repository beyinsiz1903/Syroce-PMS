"""
B2B Channel B (T004) — per-agency Redis Streams fanout for ARI (availability /
rate / stop-sale) changes, so a separate agency-automation app can consume a
real-time, resumable feed.

Why streams (not the existing pub/sub): pub/sub is fire-and-forget — a reconnecting
consumer misses everything sent while it was away. Redis Streams keep a capped
history with per-message IDs, so a consumer resumes from its last acknowledged ID
via a consumer group. This runs PARALLEL to the existing ARI outbox/coalesce
pipeline; it never alters provider push behaviour.

Isolation: one stream PER AGENCY — ``b2b:tenant:{t}:agency:{a}:ari:v1`` — never a
tenant-wide stream. Each agency reads only its own stream, so one partner can
never observe another partner's feed (cross-agency disclosure). The audience for
a tenant is the set of agencies holding an ACTIVE B2B API key (the live
integrations).

Fail-safe (additive, non-destructive): this is best-effort and MUST NEVER raise
into the ARI pipeline. When Redis is unavailable (or an XADD fails) the event is
parked in ``sysdb.b2b_stream_outbox`` (deduped per (tenant, event)) and replayed
opportunistically on the next healthy flush via ``drain_stream_outbox`` — at-least
-once delivery. Consumers MUST treat ARI as idempotent / last-write-wins (a replay
can re-deliver), which it already is (keyed by room_type + date).
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import UTC, datetime

from core.tenant_db import get_system_db

logger = logging.getLogger(__name__)

OUTBOX_COLLECTION = "b2b_stream_outbox"
STREAM_MAXLEN = 100_000  # ~ capped history per agency stream (approximate trim)
SCHEMA = "ari.v1"

# Opportunistic outbox drain budget per healthy flush.
_DRAIN_BATCH = 50

# Short per-tenant audience cache so a burst of flushes doesn't re-query the
# api-key collection each time.
_AUDIENCE_TTL = 30.0
_audience_cache: dict[str, tuple[float, list[str]]] = {}

_indexes_ready = False


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def stream_key(tenant_id: str, agency_id: str) -> str:
    """Per-agency ARI stream key. Single source of truth for the contract."""
    return f"b2b:tenant:{tenant_id}:agency:{agency_id}:ari:v1"


def _resolve_client(explicit=None):
    """Return a usable Redis client or None (never raises).

    ``explicit`` lets callers/tests inject a client; production passes None and we
    resolve the shared cluster client only when it is actually connected.
    """
    if explicit is not None:
        return explicit
    try:
        from infra.redis_cluster import redis_cluster

        if redis_cluster.connected:
            return redis_cluster.get_client()
    except Exception:  # noqa: BLE001 — resolution must never break the caller
        pass
    return None


async def _ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    try:
        sysdb = get_system_db()
        await sysdb[OUTBOX_COLLECTION].create_index([("tenant_id", 1), ("event_id", 1)], unique=True, name="uq_tenant_event")
        await sysdb[OUTBOX_COLLECTION].create_index([("created_at", 1)], name="ix_created")
        _indexes_ready = True
    except Exception:  # noqa: BLE001 — retry on the next call rather than crash
        logger.exception("[b2b_streams] index ensure failed (will retry)")


async def _agency_ids_for_tenant(tenant_id: str) -> list[str]:
    """Agencies with a live B2B integration (active API key) for this tenant."""
    now = time.monotonic()
    cached = _audience_cache.get(tenant_id)
    if cached and (now - cached[0]) < _AUDIENCE_TTL:
        return cached[1]
    try:
        sysdb = get_system_db()
        ids = await sysdb.agency_api_keys.distinct("agency_id", {"tenant_id": tenant_id, "is_active": True})
        ids = [i for i in ids if i]
        if ids:
            # Fail-closed parity with REST auth (_scope.py requires the agency
            # RECORD to be status=="active", not merely holding an un-revoked key):
            # a deactivated agency must NOT keep receiving its ARI feed just because
            # a stale key was never flipped. Intersect with active agency records.
            active_rows = await sysdb.agencies.find(
                {"id": {"$in": ids}, "tenant_id": tenant_id, "status": "active"},
                {"_id": 0, "id": 1},
            ).to_list(len(ids))
            active_ids = {r.get("id") for r in active_rows}
            ids = [i for i in ids if i in active_ids]
    except Exception:  # noqa: BLE001
        # Fail-closed: do NOT serve a (possibly stale) cached audience on a DB
        # error — a recently-deactivated agency could still receive one fanout
        # cycle. Returning [] only defers fanout (ARI is last-write-wins; the next
        # healthy flush recomputes and re-delivers the latest state).
        logger.exception("[b2b_streams] audience lookup failed for tenant %s", tenant_id)
        return []
    _audience_cache[tenant_id] = (now, ids)
    return ids


def _event_fields(event) -> dict:
    """Flatten an ARIChangeEvent into Redis-stream string fields (no agency_id;
    that is stamped per-agency at XADD time)."""

    def _iso(v):
        return v.isoformat() if hasattr(v, "isoformat") else str(v)

    return {
        "schema": SCHEMA,
        "event_id": str(event.id),
        "tenant_id": str(event.tenant_id),
        "property_id": str(event.property_id),
        "event_type": str(event.event_type),
        "room_type_code": str(event.room_type_code),
        "rate_plan_code": str(event.rate_plan_code or ""),
        "date_from": _iso(event.date_from),
        "date_to": _iso(event.date_to),
        "payload": json.dumps(event.payload, default=str, ensure_ascii=False),
        "source_service": str(event.source_service),
        "correlation_id": str(event.correlation_id or ""),
        "created_at": _iso(event.created_at),
    }


async def _xadd(client, key: str, fields: dict) -> bool:
    try:
        await client.xadd(key, fields, maxlen=STREAM_MAXLEN, approximate=True)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[b2b_streams] XADD failed for %s: %s", key, exc)
        return False


async def _outbox_record(tenant_id: str, event_id: str, fields: dict) -> None:
    """Park an undelivered event for later replay (deduped per (tenant, event))."""
    try:
        await _ensure_indexes()
        sysdb = get_system_db()
        await sysdb[OUTBOX_COLLECTION].update_one(
            {"tenant_id": tenant_id, "event_id": event_id},
            {
                "$setOnInsert": {
                    "tenant_id": tenant_id,
                    "event_id": event_id,
                    "fields": fields,
                    "created_at": _now_iso(),
                    "attempts": 0,
                }
            },
            upsert=True,
        )
    except Exception:  # noqa: BLE001 — last resort; an undeliverable event is dropped, never raised
        logger.exception("[b2b_streams] outbox record failed (event dropped): %s", event_id)


async def drain_stream_outbox(limit: int = 100, client=None) -> dict:
    """Replay parked events to their per-agency streams. No-op when Redis is down.

    A row is deleted only when delivery to ALL current audience members succeeds
    (or the audience is empty). Otherwise its attempt counter is bumped and it is
    retried later — at-least-once (consumers are idempotent on ARI)."""
    client = _resolve_client(client)
    if client is None:
        return {"drained": 0, "examined": 0, "skipped": "redis_unavailable"}
    try:
        sysdb = get_system_db()
        rows = await sysdb[OUTBOX_COLLECTION].find({}, {"_id": 0}).sort("created_at", 1).limit(limit).to_list(limit)
    except Exception:  # noqa: BLE001
        logger.exception("[b2b_streams] outbox read failed during drain")
        return {"drained": 0, "examined": 0, "skipped": "read_error"}

    drained = 0
    for row in rows:
        tenant_id = row["tenant_id"]
        fields = row.get("fields", {})
        agency_ids = await _agency_ids_for_tenant(tenant_id)
        ok_all = True
        for aid in agency_ids:
            if not await _xadd(client, stream_key(tenant_id, aid), {**fields, "agency_id": aid}):
                ok_all = False
        try:
            if ok_all:
                await sysdb[OUTBOX_COLLECTION].delete_one({"tenant_id": tenant_id, "event_id": row["event_id"]})
                drained += 1
            else:
                await sysdb[OUTBOX_COLLECTION].update_one(
                    {"tenant_id": tenant_id, "event_id": row["event_id"]},
                    {"$inc": {"attempts": 1}, "$set": {"last_attempt_at": _now_iso()}},
                )
        except Exception:  # noqa: BLE001
            logger.exception("[b2b_streams] outbox post-drain update failed: %s", row.get("event_id"))
    return {"drained": drained, "examined": len(rows)}


async def publish_ari_to_agency_streams(events: list, client=None) -> dict:
    """Best-effort per-agency XADD fanout for a batch of ARIChangeEvent.

    Never raises. When Redis is down the whole batch is parked in the outbox; when
    Redis is up, parked events are opportunistically drained first, then the live
    batch is fanned out (failed XADDs fall back to the outbox)."""
    if not events:
        return {"published": 0, "outboxed": 0}

    by_tenant: dict[str, list] = defaultdict(list)
    for e in events:
        by_tenant[e.tenant_id].append(e)

    client = _resolve_client(client)

    # Redis down → park the whole batch for later replay.
    if client is None:
        outboxed = 0
        for tenant_id, evs in by_tenant.items():
            for e in evs:
                await _outbox_record(tenant_id, str(e.id), _event_fields(e))
                outboxed += 1
        return {"published": 0, "outboxed": outboxed, "redis": "down"}

    # Redis up → first replay anything parked, then fan out the live batch.
    await drain_stream_outbox(limit=_DRAIN_BATCH, client=client)

    published = 0
    outboxed = 0
    for tenant_id, evs in by_tenant.items():
        agency_ids = await _agency_ids_for_tenant(tenant_id)
        if not agency_ids:
            continue  # no integrated agencies → nothing to fan out
        for e in evs:
            fields = _event_fields(e)
            delivered_all = True
            for aid in agency_ids:
                if await _xadd(client, stream_key(tenant_id, aid), {**fields, "agency_id": aid}):
                    published += 1
                else:
                    delivered_all = False
            if not delivered_all:
                await _outbox_record(tenant_id, str(e.id), fields)
                outboxed += 1
    return {"published": published, "outboxed": outboxed, "redis": "up"}
