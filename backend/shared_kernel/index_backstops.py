"""Self-healing registry for best-effort unique-index "backstops".

A uniqueness index is the only race-safe enforcement behind the read-then-insert
duplicate guards for suppliers/customers (``mice_accounts``) and corporate
contracts (``corporate_contracts``). These indexes are built best-effort: if
legacy duplicate rows already exist — and the index is *global* across tenants,
so duplicates in ANY hotel count — the build fails and the safeguard is silently
OFF for everyone. Worse, the old code cached an "indexes ready" flag even when a
unique build failed, so the build was never retried until a restart against
clean data.

This module makes that failure observable and self-healing:

  * ``attempt_backstop`` records each build as ACTIVE or DEFERRED, logs a clear
    warning + bumps a Prometheus metric on deferral, and throttles retries so a
    still-deferred backstop does not trigger a ``create_index`` attempt on every
    single request.
  * Callers retry on every relevant request (subject to the throttle) instead of
    caching "ready" after a failed build, so cleaning the duplicate data
    re-enables the safeguard on the next attempt — no restart required.
  * ``list_status`` powers an ops/admin health check so operators can see which
    backstops are active vs off.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("index_backstops")

# Minimum seconds between retries of a still-deferred backstop, so a deferred
# index does not trigger a create_index attempt on every single request while
# still self-healing promptly once the duplicate data is cleaned.
_RETRY_THROTTLE_SECONDS = 60.0

# name -> {name, collection, fields, active, error, deferred_count, last_attempt}
_registry: dict[str, dict[str, Any]] = {}

try:  # pragma: no cover - prometheus is always present in prod
    from prometheus_client import Counter, Gauge

    _backstop_active_gauge = Gauge(
        "hotel_pms_unique_index_backstop_active",
        "Whether a unique-index duplicate-prevention backstop is built (1) or deferred/off (0)",
        ["backstop"],
    )
    _backstop_deferred_total = Counter(
        "hotel_pms_unique_index_backstop_deferred_total",
        "Times a unique-index backstop build was deferred (existing duplicate data) leaving the duplicate-prevention safeguard off",
        ["backstop"],
    )
except Exception:  # pragma: no cover
    _backstop_active_gauge = None
    _backstop_deferred_total = None


def _set_gauge(name: str, active: bool) -> None:
    if _backstop_active_gauge is not None:
        try:
            _backstop_active_gauge.labels(backstop=name).set(1 if active else 0)
        except Exception:  # noqa: BLE001
            pass


def register_expected(name: str, *, collection: str, fields: list[str]) -> None:
    """Pre-register a backstop so ops reporting lists it before its first build.

    Records an UNKNOWN (not-yet-attempted) entry. Idempotent — never clobbers an
    entry that has already been attempted.
    """
    if name in _registry:
        return
    _registry[name] = {
        "name": name,
        "collection": collection,
        "fields": list(fields),
        "active": None,  # None = not yet attempted
        "error": None,
        "deferred_count": 0,
        "last_attempt": None,
    }
    _set_gauge(name, False)


def record_active(name: str, *, collection: str, fields: list[str]) -> None:
    prev = _registry.get(name, {})
    _registry[name] = {
        "name": name,
        "collection": collection,
        "fields": list(fields),
        "active": True,
        "error": None,
        "deferred_count": prev.get("deferred_count", 0),
        "last_attempt": time.time(),
    }
    _set_gauge(name, True)


def record_deferred(
    name: str,
    *,
    collection: str,
    fields: list[str],
    error: BaseException | str,
) -> None:
    prev = _registry.get(name, {})
    _registry[name] = {
        "name": name,
        "collection": collection,
        "fields": list(fields),
        "active": False,
        "error": str(error),
        "deferred_count": prev.get("deferred_count", 0) + 1,
        "last_attempt": time.time(),
    }
    _set_gauge(name, False)
    if _backstop_deferred_total is not None:
        try:
            _backstop_deferred_total.labels(backstop=name).inc()
        except Exception:  # noqa: BLE001
            pass
    logger.warning(
        "UNIQUE_INDEX_BACKSTOP_DEFERRED backstop=%s collection=%s fields=%s — "
        "duplicate-prevention safeguard is OFF (existing duplicate data?). It "
        "will self-heal once the duplicate rows are cleaned: %s",
        name,
        collection,
        fields,
        error,
    )


def is_active(name: str) -> bool:
    return bool(_registry.get(name, {}).get("active"))


def _should_attempt(name: str) -> bool:
    entry = _registry.get(name)
    if entry is None or entry.get("last_attempt") is None:
        return True
    if entry.get("active"):
        return False
    return (time.time() - entry["last_attempt"]) >= _RETRY_THROTTLE_SECONDS


async def attempt_backstop(
    name: str,
    *,
    collection: str,
    fields: list[str],
    build: Callable[[], Awaitable[Any]],
    force: bool = False,
) -> bool:
    """Best-effort build of a unique-index backstop with self-heal + observability.

    Returns ``True`` if the backstop is active after this call. Skips the DB work
    when the backstop is already active, or when it is deferred but still inside
    the retry-throttle window (unless ``force`` is set, e.g. for an ops re-check).
    """
    if is_active(name):
        return True
    if not force and not _should_attempt(name):
        return False
    try:
        await build()
    except Exception as exc:  # noqa: BLE001
        record_deferred(name, collection=collection, fields=fields, error=exc)
        return False
    record_active(name, collection=collection, fields=fields)
    logger.info("UNIQUE_INDEX_BACKSTOP_ACTIVE backstop=%s collection=%s — duplicate-prevention safeguard enforced", name, collection)
    return True


def _status_label(active: Any) -> str:
    if active is True:
        return "active"
    if active is False:
        return "deferred"
    return "unknown"


def list_status() -> list[dict[str, Any]]:
    """Snapshot of all known backstops for ops/admin reporting."""
    out: list[dict[str, Any]] = []
    for entry in _registry.values():
        e = dict(entry)
        last = e.get("last_attempt")
        e["status"] = _status_label(e.get("active"))
        e["last_attempt_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(last)) if last else None
        out.append(e)
    return sorted(out, key=lambda x: x["name"])


def all_active() -> bool:
    """True only if every registered backstop has been built (none deferred)."""
    if not _registry:
        return False
    return all(e.get("active") is True for e in _registry.values())


def any_deferred() -> bool:
    """True if at least one registered backstop is currently OFF."""
    return any(e.get("active") is False for e in _registry.values())
