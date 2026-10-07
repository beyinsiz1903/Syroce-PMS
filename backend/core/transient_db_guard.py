"""Shared helpers for background workers to handle transient MongoDB errors.

Background workers (room-type inventory reconciliation, import retry,
KVKK id-photo alert, ARI push, ...) hit transient Atlas hiccups —
`AutoReconnect`, `ServerSelectionTimeoutError` ("No primary"), SSL handshake
timeouts, connection drops. A single hiccup is operational noise: the next
tick will retry. But the previous worker code logged every occurrence at
ERROR level, which flooded Sentry with non-actionable alerts.

This module exposes two primitives:

  * `is_transient_db_error(exc)` — classification helper. Treats
    pymongo's `AutoReconnect`, `NetworkTimeout`, `ServerSelectionTimeoutError`
    plus low-level `ConnectionError` and `OSError` as transient.

  * `TransientFailureTracker(name, threshold=5)` — per-worker, in-memory
    streak counter keyed by an arbitrary string (typically tenant id, or a
    reserved key like "__loop__" for outer-loop ticks). Provides a single
    `log_exception(logger, exc, key, context=...)` method that:
      - logs WARNING when the streak is below threshold,
      - logs ERROR once the streak reaches threshold (so a sustained Atlas
        outage is not silenced),
      - re-raises nothing — callers decide control flow.
    A successful tick should call `reset(key)`; `prune(active_keys)` drops
    counters for keys no longer in the active set (memory hygiene over
    long uptimes with tenant churn).

Concurrency model: each worker runs as a single asyncio task in one
process, so plain dict mutations under the event-loop thread are safe.
If a worker is ever sharded across tasks, wrap mutations in an
`asyncio.Lock` or move state into an instance attribute.
"""

from __future__ import annotations

import logging
from typing import Iterable

from pymongo.errors import AutoReconnect, NetworkTimeout, OperationFailure, ServerSelectionTimeoutError

_TRANSIENT_DB_ERRORS: tuple[type[BaseException], ...] = (
    AutoReconnect,
    NetworkTimeout,
    ServerSelectionTimeoutError,
    ConnectionError,
    OSError,
)

# MongoDB can report a replica-set election during a write as an
# ``OperationFailure``/``WriteError`` instead of ``NotPrimaryError``.  These
# server codes are explicitly retryable topology transitions, not bad input
# or a broken write contract.  In particular Atlas currently emits code 189
# (PrimarySteppedDown), which otherwise gets sent to Sentry as a product bug.
_TRANSIENT_OPERATION_CODES = frozenset(
    {
        6,      # HostUnreachable
        7,      # HostNotFound
        89,     # NetworkTimeout
        91,     # ShutdownInProgress
        189,    # PrimarySteppedDown
        9001,   # SocketException
        10107,  # NotWritablePrimary / legacy NotMaster
        11600,  # InterruptedAtShutdown
        11602,  # InterruptedDueToReplStateChange
        13435,  # NotPrimaryNoSecondaryOk
        13436,  # NotPrimaryOrSecondary
    }
)


def is_transient_db_error(exc: BaseException) -> bool:
    """True if `exc` looks like a recoverable MongoDB / network hiccup."""
    if isinstance(exc, _TRANSIENT_DB_ERRORS):
        return True
    if isinstance(exc, OperationFailure):
        if getattr(exc, "code", None) in _TRANSIENT_OPERATION_CODES:
            return True
        has_error_label = getattr(exc, "has_error_label", None)
        if callable(has_error_label) and (
            has_error_label("RetryableWriteError")
            or has_error_label("RetryableReadError")
        ):
            return True
    return False


class TransientFailureTracker:
    """Per-worker streak tracker that demotes transient errors to WARNING
    while preserving Sentry visibility for sustained outages.

    The reserved key `OUTER_LOOP_KEY` is the conventional key for an
    "outer loop tick failed" counter and is always preserved by `prune`.
    """

    OUTER_LOOP_KEY = "__loop__"

    def __init__(self, name: str, threshold: int = 5) -> None:
        self.name = name
        self.threshold = max(1, int(threshold))
        self._counts: dict[str, int] = {}

    # --- state mutation -------------------------------------------------

    def _record(self, key: str) -> int:
        n = self._counts.get(key, 0) + 1
        self._counts[key] = n
        return n

    def reset(self, key: str) -> None:
        self._counts.pop(key, None)

    def prune(self, active_keys: Iterable[str]) -> None:
        keep = set(active_keys) | {self.OUTER_LOOP_KEY}
        for k in [k for k in self._counts if k not in keep]:
            self._counts.pop(k, None)

    # --- introspection (used by tests + metrics) ------------------------

    def streak(self, key: str) -> int:
        return self._counts.get(key, 0)

    def snapshot(self) -> dict[str, int]:
        return dict(self._counts)

    # --- logging --------------------------------------------------------

    def log_exception(
        self,
        logger: logging.Logger,
        exc: BaseException,
        key: str,
        *,
        context: str = "",
        non_transient_level: int = logging.ERROR,
        non_transient_msg: str | None = None,
    ) -> None:
        """Route an exception to WARNING / ERROR based on transience + streak.

        Non-transient errors (real bugs) always use `non_transient_level`
        (default ERROR) so Sentry sees them on the first occurrence.
        """
        prefix = f"[{self.name}]" + (f" {context}" if context else "")
        if not is_transient_db_error(exc):
            msg = non_transient_msg or "%s non-transient error: %s"
            # Preserve full traceback for real bugs — equivalent to the
            # previous `logger.exception(...)` call sites that this
            # tracker replaces. Without `exc_info=True` Sentry would lose
            # stack frames it had before this refactor.
            logger.log(non_transient_level, msg, prefix, exc, exc_info=exc)
            return

        streak = self._record(key)
        if streak >= self.threshold:
            logger.error(
                "%s sustained transient db error (key=%s streak=%d): %s",
                prefix,
                key,
                streak,
                exc.__class__.__name__,
            )
        else:
            logger.warning(
                "%s transient db error (key=%s streak=%d, will retry next tick): %s",
                prefix,
                key,
                streak,
                exc.__class__.__name__,
            )
