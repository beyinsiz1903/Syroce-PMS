from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

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


def _parse_timestamp(raw_value: Any) -> Optional[datetime]:
    if isinstance(raw_value, datetime):
        return raw_value if raw_value.tzinfo else raw_value.replace(tzinfo=timezone.utc)

    if not raw_value or not isinstance(raw_value, str):
        return None

    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _bucket_series(events: List[Dict[str, Any]], key: str, hours: int = 24) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    buckets: Dict[str, int] = {}

    for offset in range(hours - 1, -1, -1):
        bucket_start = now - timedelta(hours=offset)
        buckets[bucket_start.isoformat()] = 0

    for event in events:
        parsed = _parse_timestamp(event.get(key))
        if not parsed:
            continue
        bucket_start = parsed.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
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


def build_health_score(
    *,
    generated_at: str,
    failed_outbox_count: int,
    stale_pending_count: int,
    audit_gap_count: int,
    shadow_summary: List[Dict[str, Any]],
) -> Dict[str, Any]:
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
    reasons: List[str] = []

    if audit_gap_count > 0:
        status = "red"
        reasons.append(f"{audit_gap_count} audit gap detected")

    if failed_outbox_count > 0:
        status = "red"
        reasons.append(f"{failed_outbox_count} failed outbox event")

    if max_mismatch_rate_percent > 5.0:
        status = "red"
        reasons.append(
            f"{highest_mismatch.get('endpoint', 'shadow')} mismatch rate %{max_mismatch_rate_percent:.1f}"
        )

    if status != "red":
        if stale_pending_count > 0:
            reasons.append(f"{stale_pending_count} stale pending event")
        if 1.0 <= max_mismatch_rate_percent <= 5.0:
            reasons.append(
                f"{highest_mismatch.get('endpoint', 'shadow')} mismatch rate %{max_mismatch_rate_percent:.1f}"
            )
        if compare_error_count > 0:
            reasons.append(f"{compare_error_count} compare error")
        if reasons:
            status = "yellow"

    if status == "green":
        reasons = [
            "Failed outbox event yok",
            "Stale pending event yok",
            "Mismatch rate %1 altında ve compare error yok",
        ]

    operational_guidance = {
        "green": "Green → sıradaki dar write-path’e geçilebilir",
        "yellow": "Yellow → geçmeden önce gözlem ve inceleme gerekir",
        "red": "Red → yeni write-path açılmaz, önce sorun çözülür",
    }[status]

    return {
        "status": status,
        "display_status": status.capitalize(),
        "calculated_at": generated_at,
        "time_window": "last_24h",
        "time_window_label": "Last 24h",
        "reasons": reasons[:3],
        "operational_guidance": operational_guidance,
        "signals": {
            "failed_outbox_count": failed_outbox_count,
            "stale_pending_count": stale_pending_count,
            "audit_gap_count": audit_gap_count,
            "compare_error_count": compare_error_count,
            "max_mismatch_rate_percent": round(max_mismatch_rate_percent, 2),
        },
    }


class MigrationObservabilityService:
    async def get_dashboard(self, tenant_id: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
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
        stale_pending_count = 0
        status_counter: Counter[str] = Counter()
        event_counter: Counter[str] = Counter()
        event_pending_counter: Counter[str] = Counter()
        latest_event_at: Dict[str, str] = {}
        retry_attempts_total = 0
        retry_fields_found = False
        latency_values: List[float] = []

        for event in outbox_events:
            created_at = _parse_timestamp(event.get("created_at"))
            processed_at = _parse_timestamp(event.get("processed_at"))
            status_value = str(event.get("status") or "pending")
            event_type = str(event.get("event_type") or "unknown")

            status_counter[status_value] += 1
            event_counter[event_type] += 1
            if status_value == "pending":
                event_pending_counter[event_type] += 1

            if created_at and created_at >= twenty_four_hours_ago:
                recent_outbox.append(event)

            if created_at and status_value == "pending" and created_at <= fifteen_minutes_ago:
                stale_pending_count += 1

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
                "pending_count": event_pending_counter.get(event_type, 0),
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
            "processed": status_counter.get("processed", 0),
            "failed": status_counter.get("failed", 0),
            "dead_letter": status_counter.get("dead_letter", 0),
            "stale_pending": stale_pending_count,
        }

        audit_action_breakdown = Counter(log.get("action") or "unknown" for log in audit_logs_24h)

        endpoint_metrics: Dict[str, Dict[str, Any]] = defaultdict(
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
                "entity_id": event.get("reservation_id") or event.get("room_block_id") or event.get("folio_id"),
            }
            for event in outbox_events[:12]
        ]

        health_score = build_health_score(
            generated_at=now.isoformat(),
            failed_outbox_count=queue_depth["failed"] + queue_depth["dead_letter"],
            stale_pending_count=queue_depth["stale_pending"],
            audit_gap_count=audit_gap_count,
            shadow_summary=shadow_summary,
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
                "event_breakdown": outbox_breakdown,
                "retries": {
                    "total_attempts": retry_attempts_total,
                    "dead_letter_count": queue_depth["dead_letter"],
                    "future_ready": not retry_fields_found,
                },
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