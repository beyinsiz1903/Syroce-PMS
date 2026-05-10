from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db
from shared_kernel.shadow_metrics import shadow_metrics_store

MIGRATION_EVENT_TYPES = [
    "reservation.created.v1",
    "inventory.blocked.v1",
    "inventory.released.v1",
    "folio.opened.v1",
    "reservation.modified.v1",
    "reservation.cancelled.v1",
    "folio.charge_posted.v1",
]

MIGRATION_AUDIT_ACTIONS = [
    "reservation_created",
    "room_block_created",
    "room_block_released",
    "folio_opened",
    "reservation_modified",
    "reservation_cancelled",
    "folio_charge_posted",
]

MIGRATION_EVENT_AUDIT_MAP = {
    "reservation.created.v1": {
        "action": "reservation_created",
        "entity_key": "reservation_id",
    },
    "inventory.blocked.v1": {
        "action": "room_block_created",
        "entity_key": "room_block_id",
    },
    "inventory.released.v1": {
        "action": "room_block_released",
        "entity_key": "room_block_id",
    },
    "folio.opened.v1": {
        "action": "folio_opened",
        "entity_key": "folio_id",
    },
    "reservation.modified.v1": {
        "action": "reservation_modified",
        "entity_key": "reservation_id",
    },
    "reservation.cancelled.v1": {
        "action": "reservation_cancelled",
        "entity_key": "reservation_id",
    },
    "folio.charge_posted.v1": {
        "action": "folio_charge_posted",
        "entity_key": "folio_charge_id",
    },
}

EVENT_SOURCE_HINTS = {
    "reservation.created.v1": {
        "source": "semantic_reservations_service",
        "origin": "semantic",
    },
    "inventory.blocked.v1": {
        "source": "semantic_inventory_service",
        "origin": "semantic",
    },
    "inventory.released.v1": {
        "source": "semantic_inventory_service",
        "origin": "semantic",
    },
    "folio.opened.v1": {
        "source": "semantic_folio_service",
        "origin": "semantic",
    },
    "reservation.modified.v1": {
        "source": "semantic_reservations_service",
        "origin": "semantic",
    },
    "reservation.cancelled.v1": {
        "source": "semantic_reservations_service",
        "origin": "semantic",
    },
    "folio.charge_posted.v1": {
        "source": "semantic_folio_service",
        "origin": "semantic",
    },
}


def _parse_timestamp(raw_value: Any) -> datetime | None:
    if isinstance(raw_value, datetime):
        return raw_value if raw_value.tzinfo else raw_value.replace(tzinfo=UTC)

    if not raw_value or not isinstance(raw_value, str):
        return None

    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _bucket_series(events: list[dict[str, Any]], key: str, hours: int = 24) -> list[dict[str, Any]]:
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    buckets: dict[str, int] = {}

    for offset in range(hours - 1, -1, -1):
        bucket_start = now - timedelta(hours=offset)
        buckets[bucket_start.isoformat()] = 0

    for event in events:
        parsed = _parse_timestamp(event.get(key))
        if not parsed:
            continue
        bucket_start = parsed.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        bucket_key = bucket_start.isoformat()
        if bucket_key in buckets:
            buckets[bucket_key] += 1

    return [
        {
            "timestamp": timestamp,
            "count": count,
            "label": datetime.fromisoformat(timestamp).strftime("%H:%M"),
        }
        for timestamp, count in buckets.items()
    ]


def _derive_event_source(event: dict[str, Any]) -> dict[str, str]:
    event_type = str(event.get("event_type") or "unknown")
    payload = event.get("payload") or {}
    hint = EVENT_SOURCE_HINTS.get(event_type, {})

    source = (
        payload.get("source")
        or payload.get("origin")
        or event.get("source")
        or hint.get("source")
        or "unknown"
    )
    source_lower = str(source).lower()

    if "legacy" in source_lower:
        origin = "legacy"
    elif event_type in MIGRATION_EVENT_TYPES or source_lower.startswith("semantic_"):
        origin = "semantic"
    else:
        origin = hint.get("origin") or "unknown"

    return {
        "source": str(source),
        "origin": origin,
    }


def build_stale_pending_triage(
    *,
    generated_at: str,
    stale_events: list[dict[str, Any]],
) -> dict[str, Any]:
    if not stale_events:
        return {
            "generated_at": generated_at,
            "total_stale_pending": 0,
            "oldest_pending_at": None,
            "oldest_pending_age_minutes": None,
            "newest_pending_at": None,
            "newest_pending_age_minutes": None,
            "event_type_breakdown": [],
            "tenant_breakdown": [],
            "property_breakdown": [],
            "source_breakdown": [],
            "origin_breakdown": [],
            "delivery_signals": {
                "processed_count": 0,
                "retry_metadata_count": 0,
                "has_delivery_lifecycle": False,
            },
            "assessment": {
                "backlog_shape": "clear",
                "source_scope_key": "no_stale_pending",
                "source_scope": "No stale pending events",
                "source_scope_params": {"count": 0, "total": 0},
                "likely_root_cause_key": "triage_not_needed",
                "likely_root_cause": "Triage not needed",
                "recommended_action_key": "continue_with_health",
                "recommended_action": "Can continue with current health score signal",
            },
            "sample_events": [],
        }

    now = _parse_timestamp(generated_at) or datetime.now(UTC)
    event_type_counter: Counter[str] = Counter()
    tenant_counter: Counter[str] = Counter()
    property_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    origin_counter: Counter[str] = Counter()
    source_origin_map: dict[str, str] = {}
    processed_count = 0
    retry_metadata_count = 0
    samples: list[dict[str, Any]] = []

    sorted_events = sorted(
        stale_events,
        key=lambda event: _parse_timestamp(event.get("created_at")) or now,
    )

    oldest_pending_at = _parse_timestamp(sorted_events[0].get("created_at"))
    newest_pending_at = _parse_timestamp(sorted_events[-1].get("created_at"))

    for event in sorted_events:
        event_type = str(event.get("event_type") or "unknown")
        tenant_id = str(event.get("tenant_id") or "missing")
        property_id = str(event.get("property_id") or "missing")
        source_info = _derive_event_source(event)
        source = source_info["source"]
        origin = source_info["origin"]

        event_type_counter[event_type] += 1
        tenant_counter[tenant_id] += 1
        property_counter[property_id] += 1
        source_counter[source] += 1
        origin_counter[origin] += 1
        source_origin_map[source] = origin

        if event.get("processed_at"):
            processed_count += 1
        if any(event.get(field) is not None for field in ["retry_attempts", "retry_count", "attempt_count"]):
            retry_metadata_count += 1

        if len(samples) < 8:
            samples.append(
                {
                    "event_id": event.get("event_id") or event.get("id"),
                    "event_type": event_type,
                    "created_at": event.get("created_at"),
                    "status": event.get("status") or "pending",
                    "tenant_id": tenant_id,
                    "property_id": property_id,
                    "entity_id": event.get("reservation_id") or event.get("room_block_id") or event.get("folio_id") or event.get("folio_charge_id"),
                    "source": source,
                    "origin": origin,
                }
            )

    total_stale = len(sorted_events)
    oldest_age_minutes = round((now - oldest_pending_at).total_seconds() / 60, 2) if oldest_pending_at else None
    newest_age_minutes = round((now - newest_pending_at).total_seconds() / 60, 2) if newest_pending_at else None

    if oldest_age_minutes is not None and oldest_age_minutes <= 360:
        backlog_shape = "same_day_backlog"
    elif oldest_age_minutes is not None and oldest_age_minutes <= 1440:
        backlog_shape = "last_24h_backlog"
    else:
        backlog_shape = "historical_backlog"

    semantic_count = origin_counter.get("semantic", 0)
    if semantic_count == total_stale:
        source_scope_key = "all_semantic"
        source_scope = "All stale pending records are from semantic write-path"
    elif semantic_count == 0:
        source_scope_key = "no_semantic"
        source_scope = "No semantic source detected in stale pending records"
    else:
        source_scope_key = "partial_semantic"
        source_scope = f"{semantic_count}/{total_stale} stale pending records are from semantic source"

    source_scope_params = {"count": semantic_count, "total": total_stale}

    if processed_count == 0 and retry_metadata_count == 0:
        likely_root_cause_key = "worker_not_connected"
        likely_root_cause = "Worker/consumer not connected or outbox state transition lifecycle not yet active"
    elif processed_count == 0:
        likely_root_cause_key = "no_consumer_signal"
        likely_root_cause = "No consumer attempt visible; queue backlog active but no processing signal"
    else:
        likely_root_cause_key = "consumer_partial"
        likely_root_cause = "Consumer partially active; state transition or retry behavior needs further investigation"

    recommended_action_key = "clarify_worker_strategy"
    recommended_action = (
        "Clarify consumer/worker strategy before opening new write-path, define outbox cleanup or explicit park policy if needed"
    )

    return {
        "generated_at": generated_at,
        "total_stale_pending": total_stale,
        "oldest_pending_at": oldest_pending_at.isoformat() if oldest_pending_at else None,
        "oldest_pending_age_minutes": oldest_age_minutes,
        "newest_pending_at": newest_pending_at.isoformat() if newest_pending_at else None,
        "newest_pending_age_minutes": newest_age_minutes,
        "event_type_breakdown": [
            {
                "event_type": event_type,
                "count": count,
                "share_percent": round((count / total_stale) * 100, 2),
            }
            for event_type, count in event_type_counter.most_common()
        ],
        "tenant_breakdown": [
            {
                "tenant_id": tenant_id,
                "count": count,
                "share_percent": round((count / total_stale) * 100, 2),
            }
            for tenant_id, count in tenant_counter.most_common()
        ],
        "property_breakdown": [
            {
                "property_id": property_id,
                "count": count,
                "share_percent": round((count / total_stale) * 100, 2),
            }
            for property_id, count in property_counter.most_common()
        ],
        "source_breakdown": [
            {
                "source": source,
                "origin": source_origin_map.get(source, "unknown"),
                "count": count,
                "share_percent": round((count / total_stale) * 100, 2),
            }
            for source, count in source_counter.most_common()
        ],
        "origin_breakdown": [
            {
                "origin": origin,
                "count": count,
                "share_percent": round((count / total_stale) * 100, 2),
            }
            for origin, count in origin_counter.most_common()
        ],
        "delivery_signals": {
            "processed_count": processed_count,
            "retry_metadata_count": retry_metadata_count,
            "has_delivery_lifecycle": processed_count > 0 or retry_metadata_count > 0,
        },
        "assessment": {
            "backlog_shape": backlog_shape,
            "source_scope_key": source_scope_key,
            "source_scope": source_scope,
            "source_scope_params": source_scope_params,
            "likely_root_cause_key": likely_root_cause_key,
            "likely_root_cause": likely_root_cause,
            "recommended_action_key": recommended_action_key,
            "recommended_action": recommended_action,
        },
        "sample_events": samples,
    }


def build_health_score(
    *,
    generated_at: str,
    failed_outbox_count: int,
    stale_pending_count: int,
    audit_gap_count: int,
    shadow_summary: list[dict[str, Any]],
) -> dict[str, Any]:
    compare_error_count = sum(int(item.get("errors") or 0) for item in shadow_summary)
    max_mismatch_rate_percent = max(
        [float(item.get("mismatch_rate_percent") or 0.0) for item in shadow_summary] or [0.0]
    )
    highest_mismatch = max(
        shadow_summary,
        key=lambda item: float(item.get("mismatch_rate_percent") or 0.0),
        default={"endpoint": "shadow", "mismatch_rate_percent": 0.0},
    )

    status = "green"
    reasons: list[str] = []

    reason_params: dict[str, Any] = {}

    if audit_gap_count > 0:
        status = "red"
        reasons.append("audit_gap_detected")
        reason_params["audit_gap_count"] = audit_gap_count

    if failed_outbox_count > 0:
        status = "red"
        reasons.append("failed_outbox_event")
        reason_params["failed_outbox_count"] = failed_outbox_count

    if max_mismatch_rate_percent > 5.0:
        status = "red"
        reasons.append("mismatch_rate_critical")
        reason_params["mismatch_endpoint"] = highest_mismatch.get("endpoint", "shadow")
        reason_params["mismatch_rate"] = round(max_mismatch_rate_percent, 1)

    if status != "red":
        if stale_pending_count > 0:
            reasons.append("stale_pending_event")
            reason_params["stale_pending_count"] = stale_pending_count
        if 1.0 <= max_mismatch_rate_percent <= 5.0:
            reasons.append("mismatch_rate_warning")
            reason_params["mismatch_endpoint"] = highest_mismatch.get("endpoint", "shadow")
            reason_params["mismatch_rate"] = round(max_mismatch_rate_percent, 1)
        if compare_error_count > 0:
            reasons.append("compare_error")
            reason_params["compare_error_count"] = compare_error_count
        if reasons:
            status = "yellow"

    if status == "green":
        reasons = [
            "no_failed_outbox",
            "no_stale_pending",
            "mismatch_below_1",
        ]

    operational_guidance_key = status

    return {
        "status": status,
        "display_status": status.capitalize(),
        "calculated_at": generated_at,
        "time_window": "last_24h",
        "time_window_label": "Last 24h",
        "reasons": reasons[:3],
        "reason_params": reason_params,
        "operational_guidance_key": operational_guidance_key,
        "signals": {
            "failed_outbox_count": failed_outbox_count,
            "stale_pending_count": stale_pending_count,
            "audit_gap_count": audit_gap_count,
            "compare_error_count": compare_error_count,
            "max_mismatch_rate_percent": round(max_mismatch_rate_percent, 2),
        },
    }


class MigrationObservabilityService:
    _shadow_loaded: set[str] = set()

    async def _ensure_shadow_loaded(self, tenant_id: str) -> None:
        if tenant_id not in self._shadow_loaded:
            await shadow_metrics_store.load_from_db(tenant_id=tenant_id, limit=500)
            self._shadow_loaded.add(tenant_id)

    async def get_dashboard(self, tenant_id: str) -> dict[str, Any]:
        await self._ensure_shadow_loaded(tenant_id)
        now = datetime.now(UTC)
        twenty_four_hours_ago = now - timedelta(hours=24)
        five_minutes_ago = now - timedelta(minutes=5)
        fifteen_minutes_ago = now - timedelta(minutes=15)

        outbox_events = await db.outbox_events.find(
            {
                "tenant_id": tenant_id,
                "event_type": {"$in": MIGRATION_EVENT_TYPES},
            },
            {"_id": 0},
        ).sort("created_at", -1).to_list(500)

        audit_logs_24h = await db.audit_logs.find(
            {
                "tenant_id": tenant_id,
                "action": {"$in": MIGRATION_AUDIT_ACTIONS},
                "timestamp": {"$gte": twenty_four_hours_ago.isoformat()},
            },
            {
                "_id": 0,
                "id": 1,
                "actor_id": 1,
                "entity_type": 1,
                "entity_id": 1,
                "action": 1,
                "property_id": 1,
                "correlation_id": 1,
                "timestamp": 1,
                "metadata": 1,
            },
        ).sort("timestamp", -1).to_list(500)

        audit_logs = audit_logs_24h[:20]

        shadow_events = [
            event
            for event in shadow_metrics_store.get_recent_events()
            if (
                event.get("tenant_id") == tenant_id
                and event.get("endpoint") in {"availability", "folio"}
                and (_parse_timestamp(event.get("timestamp")) or now) >= twenty_four_hours_ago
            )
        ]

        recent_outbox = []
        stale_pending_events: list[dict[str, Any]] = []
        stale_pending_count = 0
        status_counter: Counter[str] = Counter()
        event_counter: Counter[str] = Counter()
        event_status_breakdown: dict[str, Counter[str]] = defaultdict(Counter)
        latest_event_at: dict[str, str] = {}
        retry_attempts_total = 0
        retry_fields_found = False
        latency_values: list[float] = []
        oldest_pending_at: datetime | None = None
        oldest_failed_at: datetime | None = None

        for event in outbox_events:
            created_at = _parse_timestamp(event.get("created_at"))
            processed_at = _parse_timestamp(event.get("processed_at"))
            status_value = str(event.get("status") or "pending")
            event_type = str(event.get("event_type") or "unknown")

            status_counter[status_value] += 1
            event_counter[event_type] += 1
            event_status_breakdown[event_type][status_value] += 1

            if created_at and created_at >= twenty_four_hours_ago:
                recent_outbox.append(event)

            if created_at and status_value == "pending" and created_at <= fifteen_minutes_ago:
                stale_pending_count += 1
                stale_pending_events.append(event)
            if created_at and status_value == "pending":
                if oldest_pending_at is None or created_at < oldest_pending_at:
                    oldest_pending_at = created_at
            if created_at and status_value == "failed":
                if oldest_failed_at is None or created_at < oldest_failed_at:
                    oldest_failed_at = created_at

            if created_at and processed_at:
                latency_values.append(max((processed_at - created_at).total_seconds() * 1000, 0.0))

            retry_value = event.get("retry_attempts")
            if retry_value is None:
                retry_value = event.get("retry_count")
            if retry_value is None and event.get("attempt_count") is not None:
                retry_value = max(int(event.get("attempt_count") or 1) - 1, 0)

            if retry_value is not None:
                retry_fields_found = True
                retry_attempts_total += int(retry_value or 0)

            created_raw = event.get("created_at")
            if event_type not in latest_event_at and created_raw:
                latest_event_at[event_type] = created_raw

        outbox_breakdown = [
            {
                "event_type": event_type,
                "total_count": count,
                "pending_count": event_status_breakdown[event_type].get("pending", 0),
                "processing_count": event_status_breakdown[event_type].get("processing", 0),
                "processed_count": event_status_breakdown[event_type].get("processed", 0),
                "failed_count": event_status_breakdown[event_type].get("failed", 0),
                "parked_count": event_status_breakdown[event_type].get("parked", 0),
                "last_seen_at": latest_event_at.get(event_type),
            }
            for event_type, count in event_counter.most_common()
        ]

        recent_5m_count = 0
        for event in recent_outbox:
            created_at = _parse_timestamp(event.get("created_at"))
            if created_at and created_at >= five_minutes_ago:
                recent_5m_count += 1

        avg_latency_ms = round(sum(latency_values) / len(latency_values), 2) if latency_values else None
        p95_latency_ms = None
        if latency_values:
            sorted_values = sorted(latency_values)
            index = max(int(len(sorted_values) * 0.95) - 1, 0)
            p95_latency_ms = round(sorted_values[index], 2)

        queue_depth = {
            "pending": status_counter.get("pending", 0),
            "processing": status_counter.get("processing", 0),
            "processed": status_counter.get("processed", 0),
            "failed": status_counter.get("failed", 0),
            "parked": status_counter.get("parked", 0),
            "dead_letter": status_counter.get("dead_letter", 0),
            "stale_pending": stale_pending_count,
        }
        oldest_pending_age_minutes = round((now - oldest_pending_at).total_seconds() / 60, 2) if oldest_pending_at else None
        oldest_failed_age_minutes = round((now - oldest_failed_at).total_seconds() / 60, 2) if oldest_failed_at else None
        lifecycle = {
            "pending_count": queue_depth["pending"],
            "processing_count": queue_depth["processing"],
            "processed_count": queue_depth["processed"],
            "failed_count": queue_depth["failed"],
            "parked_count": queue_depth["parked"],
            "retry_attempts_total": retry_attempts_total,
            "oldest_pending_at": oldest_pending_at.isoformat() if oldest_pending_at else None,
            "oldest_pending_age_minutes": oldest_pending_age_minutes,
            "oldest_failed_at": oldest_failed_at.isoformat() if oldest_failed_at else None,
            "oldest_failed_age_minutes": oldest_failed_age_minutes,
        }

        audit_action_breakdown = Counter(log.get("action") or "unknown" for log in audit_logs_24h)

        endpoint_metrics: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "endpoint": "unknown",
                "total_compares": 0,
                "mismatches": 0,
                "errors": 0,
                "last_compare_at": None,
            }
        )

        for event in shadow_events:
            endpoint = str(event.get("endpoint") or "unknown")
            endpoint_metrics[endpoint]["endpoint"] = endpoint
            endpoint_metrics[endpoint]["total_compares"] += 1
            if event.get("compare_result") == "mismatch":
                endpoint_metrics[endpoint]["mismatches"] += 1
            if event.get("compare_result") == "error":
                endpoint_metrics[endpoint]["errors"] += 1
            if not endpoint_metrics[endpoint]["last_compare_at"] and event.get("timestamp"):
                endpoint_metrics[endpoint]["last_compare_at"] = event.get("timestamp")

        shadow_summary = []
        for endpoint in ["availability", "folio"]:
            metric = endpoint_metrics[endpoint]
            total_compares = metric["total_compares"]
            mismatch_rate = round((metric["mismatches"] / total_compares) * 100, 2) if total_compares else 0.0
            shadow_summary.append(
                {
                    **metric,
                    "mismatch_rate_percent": mismatch_rate,
                }
            )

        recent_shadow_events = sorted(
            shadow_events,
            key=lambda event: event.get("timestamp") or "",
            reverse=True,
        )[:12]

        audit_lookup = {
            (
                str(log.get("action") or ""),
                str(log.get("entity_id") or ""),
            )
            for log in audit_logs_24h
        }
        audit_gap_count = 0
        for event in recent_outbox:
            event_type = str(event.get("event_type") or "")
            expected = MIGRATION_EVENT_AUDIT_MAP.get(event_type)
            if not expected:
                continue
            entity_key = expected["entity_key"]
            entity_id = event.get(entity_key) or (event.get("payload") or {}).get(entity_key)
            if not entity_id:
                continue
            if (expected["action"], str(entity_id)) not in audit_lookup:
                audit_gap_count += 1

        recent_outbox_events = [
            {
                "event_type": event.get("event_type"),
                "status": event.get("status") or "pending",
                "correlation_id": event.get("correlation_id"),
                "created_at": event.get("created_at"),
                "processed_at": event.get("processed_at"),
                "entity_id": event.get("reservation_id") or event.get("room_block_id") or event.get("folio_id"),
                "retry_count": event.get("retry_count") or 0,
                "last_error": event.get("last_error"),
            }
            for event in outbox_events[:12]
        ]

        health_score = build_health_score(
            generated_at=now.isoformat(),
            failed_outbox_count=queue_depth["failed"] + queue_depth["parked"] + queue_depth["dead_letter"],
            stale_pending_count=queue_depth["stale_pending"],
            audit_gap_count=audit_gap_count,
            shadow_summary=shadow_summary,
        )
        stale_triage = build_stale_pending_triage(
            generated_at=now.isoformat(),
            stale_events=stale_pending_events,
        )

        return {
            "generated_at": now.isoformat(),
            "health_score": health_score,
            "outbox": {
                "total_events": len(outbox_events),
                "throughput": {
                    "events_last_24h": len(recent_outbox),
                    "events_last_5m": recent_5m_count,
                    "events_per_second_24h": round(len(recent_outbox) / 86400, 6),
                    "events_per_minute_last_5m": round(recent_5m_count / 5, 2),
                    "hourly_series": _bucket_series(recent_outbox, "created_at", hours=24),
                },
                "queue_depth": queue_depth,
                "lifecycle": lifecycle,
                "event_breakdown": outbox_breakdown,
                "retries": {
                    "total_attempts": retry_attempts_total,
                    "dead_letter_count": queue_depth["dead_letter"],
                    "active_failed_count": queue_depth["failed"],
                    "parked_count": queue_depth["parked"],
                    "future_ready": not retry_fields_found,
                },
                "stale_triage": stale_triage,
                "lag": {
                    "avg_ms": avg_latency_ms,
                    "p95_ms": p95_latency_ms,
                    "future_ready": len(latency_values) == 0,
                },
                "recent_events": recent_outbox_events,
            },
            "audit": {
                "recent_count": len(audit_logs),
                "audit_gap_count": audit_gap_count,
                "actions_breakdown": [
                    {"action": action, "count": count}
                    for action, count in audit_action_breakdown.most_common()
                ],
                "recent_stream": audit_logs,
            },
            "shadow": {
                "summary": shadow_summary,
                "recent_events": recent_shadow_events,
            },
        }


# Module-level singleton — used by routers/reports_pkg/flash_email.py
# (Sentry PYTHON-FASTAPI-3F: NameError 'migration_observability_service'
# is not defined — 9 events). Class was defined but no instance exposed.
migration_observability_service = MigrationObservabilityService()
