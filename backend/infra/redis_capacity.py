"""Safe Redis capacity and failure classification helpers."""

from __future__ import annotations

import asyncio
from typing import Any


def classify_redis_failure(exc: BaseException) -> str:
    """Return a bounded, non-sensitive failure class for telemetry."""
    message = str(exc).lower()
    if "maxmemory" in message or "oom command not allowed" in message:
        return "REDIS_MAXMEMORY"
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or "timeout" in message:
        return "REDIS_TIMEOUT"
    if (
        isinstance(exc, ConnectionError)
        or "connection" in message
        or "closed=true" in message
        or "transport closed" in message
    ):
        return "REDIS_CONNECTION"
    if "command not allowed" in message:
        return "REDIS_COMMAND_DENIED"
    return f"REDIS_{type(exc).__name__.upper()[:40]}"


def redis_memory_capacity(info: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize INFO memory fields without returning arbitrary provider data."""
    info = info or {}
    used_memory = _safe_int(info.get("used_memory"))
    maxmemory = _safe_int(info.get("maxmemory"))
    policy = str(info.get("maxmemory_policy") or "unknown")[:40]

    if maxmemory <= 0:
        return {
            "state": "unbounded",
            "used_memory_bytes": used_memory,
            "maxmemory_bytes": 0,
            "usage_ratio": None,
            "policy": policy,
        }

    ratio = used_memory / maxmemory
    if ratio >= 1:
        state = "exhausted"
    elif ratio >= 0.9:
        state = "warning"
    else:
        state = "ok"

    return {
        "state": state,
        "used_memory_bytes": used_memory,
        "maxmemory_bytes": maxmemory,
        "usage_ratio": round(ratio, 4),
        "policy": policy,
    }


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
