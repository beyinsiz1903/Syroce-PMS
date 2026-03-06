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


class MigrationObservabilityService:
    async def get_dashboard(self, tenant_id: str) -> Dict[str, Any]:
        outbox_events = await db.outbox_events.find(
            {
                "tenant_id": tenant_id,
                "event_type": {"$in": MIGRATION_EVENT_TYPES},
            },
            {"_id": 0},
        ).sort("created_at", -1).to_list(500)

        audit_logs = await db.audit_logs.find(
            {
                "tenant_id": tenant_id,
                "action": {"$in": MIGRATION_AUDIT_ACTIONS},
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
        ).sort("timestamp", -1).limit(20).to_list(20)

        shadow_events = [
            event
            for event in shadow_metrics_store.get_recent_events()
            if event.get("tenant_id") == tenant_id and event.get("endpoint") in {"availability", "folio"}
        ]

        now = datetime.now(timezone.utc)
        twenty_four_hours_ago = now - timedelta(hours=24)
        five_minutes_ago = now - timedelta(minutes=5)
        fifteen_minutes_ago = now - timedelta(minutes=15)

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

        audit_action_breakdown = Counter(log.get("action") or "unknown" for log in audit_logs)

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

        return {
            "generated_at": now.isoformat(),
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