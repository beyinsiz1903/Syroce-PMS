import hashlib
import json
import logging
import threading
from collections import defaultdict, deque
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

logger = logging.getLogger("shadow_metrics")

_db_ref = None


def _get_db():
    global _db_ref
    if _db_ref is None:
        try:
            from core.database import db
            _db_ref = db
        except Exception:
            pass
    return _db_ref


class ShadowMetricsStore:
    def __init__(self, max_entries: int = 1000):
        self._lock = threading.Lock()
        self._metric_counts: dict[str, int] = defaultdict(int)
        self._recent_events = deque(maxlen=max_entries)

    def record(self, event: dict[str, Any]) -> None:
        endpoint = event.get("endpoint", "unknown")
        compare_key = f"shadow.{endpoint}.compare.total"

        with self._lock:
            self._metric_counts[compare_key] += 1
            if event.get("compare_result") == "mismatch":
                self._metric_counts[f"shadow.{endpoint}.compare.mismatch"] += 1
            if event.get("compare_result") == "error":
                self._metric_counts[f"shadow.{endpoint}.compare.error"] += 1

            for field in event.get("mismatch_fields", []):
                self._metric_counts[f"shadow.{endpoint}.field_mismatch.{field}"] += 1

            self._recent_events.append(event)

        self._persist_to_db(event)

    def _persist_to_db(self, event: dict[str, Any]) -> None:
        try:
            db = _get_db()
            if db is None:
                return
            doc = {**event, "_persisted_at": datetime.now(UTC).isoformat()}
            doc.pop("_id", None)
            import asyncio
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
            if loop and loop.is_running():
                loop.create_task(db.shadow_compare_events.insert_one(doc))
            else:
                db.delegate["shadow_compare_events"].insert_one(doc)
        except Exception as exc:
            logger.debug("Shadow metrics DB persist failed: %s", exc)

    async def load_from_db(self, tenant_id: str | None = None, limit: int = 500) -> None:
        try:
            db = _get_db()
            if db is None:
                return
            query: dict[str, Any] = {}
            if tenant_id:
                query["tenant_id"] = tenant_id
            cursor = db.shadow_compare_events.find(
                query, {"_id": 0}
            ).sort("timestamp", -1).limit(limit)
            docs = await cursor.to_list(limit)
            with self._lock:
                for doc in reversed(docs):
                    doc.pop("_persisted_at", None)
                    self._recent_events.append(doc)
        except Exception as exc:
            logger.debug("Shadow metrics DB load failed: %s", exc)

    def get_metric(self, metric_name: str) -> int:
        with self._lock:
            return self._metric_counts.get(metric_name, 0)

    def get_recent_events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._recent_events)


shadow_metrics_store = ShadowMetricsStore()


def canonicalize_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {key: canonicalize_payload(payload[key]) for key in sorted(payload.keys())}
    if isinstance(payload, list):
        normalized = [canonicalize_payload(item) for item in payload]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    if isinstance(payload, float):
        return round(payload, 4)
    return payload


def hash_payload(payload: Any) -> str:
    canonical = canonicalize_payload(payload)
    serialized = json.dumps(canonical, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _normalized_number(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    return float(value)


def normalize_availability_payload(payload: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for row in payload or []:
        room_key = row.get("id") or row.get("room_number")
        if not room_key:
            continue

        blocks = row.get("blocks") or []
        blocked_units = len([block for block in blocks if not block.get("allow_sell", False)])
        normalized[str(room_key)] = {
            "room_type_id": row.get("room_type_id") or row.get("room_type"),
            "property_id": row.get("property_id"),
            "available": bool(row.get("available")),
            "blocked": blocked_units,
            "held": int(row.get("held") or 0),
            "capacity": _normalized_number(row.get("capacity") or row.get("max_occupancy"), 0.0),
        }
    return normalized


def normalize_folio_payload(payload: dict[str, Any]) -> dict[str, Any]:
    folio = payload.get("folio") or {}
    return {
        "folio_id": folio.get("id"),
        "status": folio.get("status"),
        "currency": folio.get("currency"),
        "balance": _normalized_number(payload.get("balance"), 0.0),
        "charges_count": len(payload.get("charges") or []),
        "payments_count": len(payload.get("payments") or []),
        "guest_id": folio.get("guest_id"),
        "stay_reference": folio.get("stay_id") or folio.get("booking_id"),
    }


def compare_availability_payloads(
    semantic_payload: list[dict[str, Any]],
    legacy_payload: list[dict[str, Any]],
) -> dict[str, Any]:
    semantic_rows = normalize_availability_payload(semantic_payload)
    legacy_rows = normalize_availability_payload(legacy_payload)
    semantic_keys = set(semantic_rows.keys())
    legacy_keys = set(legacy_rows.keys())
    missing_rows = sorted(legacy_keys - semantic_keys)
    extra_rows = sorted(semantic_keys - legacy_keys)
    mismatch_fields = set()
    mismatch_count = len(missing_rows) + len(extra_rows)

    for row_key in sorted(semantic_keys & legacy_keys):
        for field in ["available", "blocked", "held", "capacity", "room_type_id", "property_id"]:
            if semantic_rows[row_key].get(field) != legacy_rows[row_key].get(field):
                mismatch_fields.add(field)
                mismatch_count += 1

    return {
        "compare_result": "mismatch" if mismatch_count else "match",
        "mismatch_count": mismatch_count,
        "mismatch_fields": sorted(mismatch_fields),
        "missing_rows": missing_rows,
        "extra_rows": extra_rows,
    }


def compare_folio_payloads(
    semantic_payload: dict[str, Any],
    legacy_payload: dict[str, Any],
) -> dict[str, Any]:
    semantic = normalize_folio_payload(semantic_payload)
    legacy = normalize_folio_payload(legacy_payload)
    mismatch_fields = [field for field in semantic.keys() if semantic.get(field) != legacy.get(field)]
    return {
        "compare_result": "mismatch" if mismatch_fields else "match",
        "mismatch_count": len(mismatch_fields),
        "mismatch_fields": mismatch_fields,
        "missing_rows": [],
        "extra_rows": [],
    }


async def run_shadow_compare(
    endpoint: str,
    tenant_id: str,
    property_id: str | None,
    correlation_id: str | None,
    semantic_payload: Any,
    legacy_loader,
    comparator,
    entity_id: str | None = None,
) -> None:
    start = perf_counter()
    try:
        legacy_payload = await legacy_loader()
        comparison = comparator(semantic_payload, legacy_payload)
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "endpoint": endpoint,
            "tenant_id": tenant_id,
            "property_id": property_id,
            "correlation_id": correlation_id,
            "entity_id": entity_id,
            "compare_result": comparison["compare_result"],
            "mismatch_fields": comparison["mismatch_fields"],
            "mismatch_count": comparison["mismatch_count"],
            "missing_rows": comparison["missing_rows"],
            "extra_rows": comparison["extra_rows"],
            "legacy_hash": hash_payload(legacy_payload),
            "semantic_hash": hash_payload(semantic_payload),
            "duration_ms": round((perf_counter() - start) * 1000, 2),
        }
        shadow_metrics_store.record(event)
        logger.info(json.dumps(event, sort_keys=True, default=str))
    except Exception as exc:
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "endpoint": endpoint,
            "tenant_id": tenant_id,
            "property_id": property_id,
            "correlation_id": correlation_id,
            "entity_id": entity_id,
            "compare_result": "error",
            "mismatch_fields": [],
            "mismatch_count": 0,
            "missing_rows": [],
            "extra_rows": [],
            "legacy_hash": None,
            "semantic_hash": hash_payload(semantic_payload),
            "duration_ms": round((perf_counter() - start) * 1000, 2),
            "error": str(exc),
        }
        shadow_metrics_store.record(event)
        logger.warning(json.dumps(event, sort_keys=True, default=str))
