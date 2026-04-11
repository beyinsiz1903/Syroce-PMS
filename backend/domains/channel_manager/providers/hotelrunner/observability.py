"""
HotelRunner Provider — Observability
======================================

Records provider call metrics, logs, and health indicators.
Writes to monitoring_metrics and ari_outbound_logs collections.
"""
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("hotelrunner.observability")

# In-memory counters for the current process
_metrics = {
    "success_count": 0,
    "error_count": 0,
    "auth_failure_count": 0,
    "rate_limit_count": 0,
    "total_latency_ms": 0,
    "call_count": 0,
    "last_success_at": None,
    "last_error_at": None,
    "last_error_type": None,
}


def record_provider_call(
    *,
    path: str,
    method: str,
    status_code: int,
    duration_ms: int,
    success: bool,
    connection_id: str = "",
    error_type: str = "",
    correlation_id: str = "",
) -> None:
    """Record a provider API call outcome."""
    _metrics["call_count"] += 1
    _metrics["total_latency_ms"] += duration_ms
    now = datetime.now(UTC).isoformat()

    if success:
        _metrics["success_count"] += 1
        _metrics["last_success_at"] = now
    else:
        _metrics["error_count"] += 1
        _metrics["last_error_at"] = now
        _metrics["last_error_type"] = error_type

    logger.info(
        "[HR-OBS] %s %s -> %d (%dms) success=%s conn=%s corr=%s",
        method, path, status_code, duration_ms, success,
        connection_id, correlation_id,
    )


def record_provider_failure(
    *,
    error_type: str,
    message: str,
    connection_id: str = "",
    path: str = "",
) -> None:
    """Record a provider failure for alerting."""
    _metrics["error_count"] += 1
    _metrics["last_error_at"] = datetime.now(UTC).isoformat()
    _metrics["last_error_type"] = error_type

    if error_type == "auth":
        _metrics["auth_failure_count"] += 1
    elif error_type == "rate_limit":
        _metrics["rate_limit_count"] += 1

    logger.error(
        "[HR-OBS] FAILURE %s: %s (conn=%s path=%s)",
        error_type, message, connection_id, path,
    )


def record_provider_latency(*, path: str, duration_ms: int) -> None:
    """Record latency metric for a specific endpoint."""
    _metrics["total_latency_ms"] += duration_ms
    _metrics["call_count"] += 1


def get_provider_health() -> dict[str, Any]:
    """Get current provider health snapshot for monitoring."""
    call_count = _metrics["call_count"]
    avg_latency = (
        round(_metrics["total_latency_ms"] / call_count)
        if call_count > 0 else 0
    )
    success_rate = (
        round((_metrics["success_count"] / call_count) * 100, 1)
        if call_count > 0 else 100.0
    )
    return {
        "provider": "hotelrunner",
        "call_count": call_count,
        "success_count": _metrics["success_count"],
        "error_count": _metrics["error_count"],
        "auth_failure_count": _metrics["auth_failure_count"],
        "rate_limit_count": _metrics["rate_limit_count"],
        "avg_latency_ms": avg_latency,
        "success_rate_pct": success_rate,
        "last_success_at": _metrics["last_success_at"],
        "last_error_at": _metrics["last_error_at"],
        "last_error_type": _metrics["last_error_type"],
    }


def reset_metrics() -> None:
    """Reset all counters. Useful for testing or periodic reset."""
    for key in _metrics:
        if isinstance(_metrics[key], int):
            _metrics[key] = 0
        elif isinstance(_metrics[key], float):
            _metrics[key] = 0.0
        else:
            _metrics[key] = None


async def persist_outbound_log(
    db: Any,
    *,
    connection_id: str,
    operation: str,
    path: str,
    method: str,
    request_payload: dict | None = None,
    response_payload: dict | None = None,
    status_code: int = 0,
    duration_ms: int = 0,
    success: bool = True,
    error_type: str = "",
    correlation_id: str = "",
) -> None:
    """Persist an outbound provider log to the database."""
    log_doc = {
        "provider": "hotelrunner",
        "connection_id": connection_id,
        "operation": operation,
        "path": path,
        "method": method,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "success": success,
        "error_type": error_type,
        "correlation_id": correlation_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if request_payload:
        log_doc["request_payload_summary"] = str(request_payload)[:1000]
    if response_payload:
        log_doc["response_payload_summary"] = str(response_payload)[:1000]

    try:
        await db["ari_outbound_logs"].insert_one(log_doc)
    except Exception as e:
        logger.warning("Failed to persist outbound log: %s", e)
