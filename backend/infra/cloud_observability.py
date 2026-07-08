"""
Cloud Observability Stack — OpenTelemetry tracing, Sentry error tracking,
enhanced Prometheus metrics, and Grafana dashboard configs.

Environment:
    OTEL_EXPORTER_ENDPOINT — OpenTelemetry collector endpoint
    OTEL_SERVICE_NAME      — Service name (default: syroce-pms)
    SENTRY_DSN             — Sentry DSN for error tracking
    SENTRY_ENVIRONMENT     — Sentry environment tag (development/pilot/production)
"""

import logging
import os
import re
from collections import defaultdict
from typing import Any

logger = logging.getLogger("infra.observability")


# ── Sentry PII Scrub ───────────────────────────────────────────────
# Defense-in-depth: even though `send_default_pii=False` strips the most
# common PII (cookies, request bodies, IP), tenant-specific identifiers
# can still leak via:
#   • exception messages ("invalid token=eyJ...", "tenant 7a3f... not found")
#   • breadcrumb URLs (?token=..., ?email=...)
#   • custom tags / extras a developer might have added ad-hoc
# `_pii_scrubber()` runs on every Sentry event before it leaves the
# process. Keep this list narrow — over-scrubbing destroys debuggability.
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # JWTs: 3 base64url segments separated by dots, ≥20 chars total.
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\b"), "<JWT>"),
    # Bearer tokens & ?token=… / ?api_key=… query params.
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.=]{12,}"), r"\1<TOKEN>"),
    (re.compile(r"(?i)([?&](?:token|api[_-]?key|secret|password|access[_-]?token)=)[^&\s\"']+"), r"\1<REDACTED>"),
    # Email addresses.
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "<EMAIL>"),
    # IPv4 (third octet masked, like the Exely whitelist redactor pattern).
    (re.compile(r"\b(\d{1,3}\.\d{1,3}\.)\d{1,3}(\.\d{1,3})\b"), r"\1x\2"),
    # MongoDB ObjectId (24 hex chars) — common tenant_id surrogate in messages.
    (re.compile(r"\b[a-f0-9]{24}\b"), "<OID>"),
]


def _scrub_str(s: str) -> str:
    if not isinstance(s, str) or not s:
        return s
    out = s
    for pat, repl in _PII_PATTERNS:
        out = pat.sub(repl, out)
    return out


def _scrub_event_inplace(event: Any) -> None:
    """Recursive PII scrub for Sentry event dicts.

    Bounded to depth 6 + container size 200 to avoid pathological
    recursion on malformed events. Errors are swallowed — a partial scrub
    is always safer than dropping the event entirely (we still want to
    see the error class / stack frame).
    """

    def _walk(node: Any, depth: int = 0) -> Any:
        if depth > 6:
            return node
        if isinstance(node, str):
            return _scrub_str(node)
        if isinstance(node, dict):
            keys = list(node.keys())[:200]
            for k in keys:
                try:
                    node[k] = _walk(node[k], depth + 1)
                except Exception:
                    pass
            return node
        if isinstance(node, list):
            for i in range(min(len(node), 200)):
                try:
                    node[i] = _walk(node[i], depth + 1)
                except Exception:
                    pass
            return node
        return node

    try:
        _walk(event)
    except Exception:
        # Never let scrubber raise — Sentry would drop the event entirely
        pass


import time as _time

# Process boot time — used to bound the restart-noise drop window.
_PROCESS_BOOT_TS = _time.monotonic()

# Only drop EADDRINUSE noise during the first N seconds after boot. A
# persistent rogue process holding the port will keep raising after this
# window and reach Sentry normally.
_RESTART_DROP_WINDOW_SECONDS = 30

# Managed ports: dev workflow (8000) and DigitalOcean deployment (5000).
# Other ports (e.g. mock_server 9999) are NOT in scope.
_MANAGED_BIND_PORTS = (8000, 5000)


def _is_workflow_restart_port_bind(event: dict, hint: dict) -> bool:
    """Detect transient port-bind failures during workflow restarts.

    Drop predicate (all must hold):
      1. ``hint['exc_info']`` exception is an ``OSError`` (or subclass).
      2. ``exc.errno == 98`` (EADDRINUSE) — strict, not a substring match.
      3. The exception message references one of the managed ports
         (8000 dev workflow / 5000 deploy).
      4. We are within ``_RESTART_DROP_WINDOW_SECONDS`` of process boot —
         after that, persistent bind conflicts are real incidents.

    Any other bind failure (different port, different errno, late-cycle
    occurrence) still flows through to Sentry. No event-only fallback —
    we refuse to drop solely on message text, to avoid collisions with
    unrelated errors that happen to mention "8000".
    """
    try:
        # Boot-window guard first (cheapest, also bounds the blast radius).
        if (_time.monotonic() - _PROCESS_BOOT_TS) > _RESTART_DROP_WINDOW_SECONDS:
            return False
        exc_info = (hint or {}).get("exc_info")
        if not exc_info or len(exc_info) < 2:
            return False
        exc = exc_info[1]
        if not isinstance(exc, OSError):
            return False
        if getattr(exc, "errno", None) != 98:
            return False
        msg = str(exc) if exc else ""
        for p in _MANAGED_BIND_PORTS:
            if f"', {p})" in msg or f":{p})" in msg or f"port {p}" in msg.lower():
                return True
    except Exception:
        return False
    return False


# Counter for filtered restart-bind events. Exposed via
# ``get_sentry_filter_stats()`` so ops can sanity-check noise volume
# without paging the on-call channel.
_RESTART_BIND_DROP_COUNT = 0


def get_sentry_filter_stats() -> dict[str, int]:
    """Return cumulative count of events dropped by the restart filter.

    Useful for ops dashboards / smoke tests. Resets only on process
    restart.
    """
    return {
        "restart_bind_drops": _RESTART_BIND_DROP_COUNT,
        "nonprod_transient_db_drops": _TRANSIENT_DB_NONPROD_DROP_COUNT,
        "graphql_introspection_denied_drops": _GRAPHQL_INTROSPECTION_DENIED_DROP_COUNT,
        "graphql_field_validation_drops": _GRAPHQL_FIELD_VALIDATION_DROP_COUNT,
        "hotelrunner_pull_rate_limit_drops": _HOTELRUNNER_PULL_RATE_LIMIT_DROP_COUNT,
        "hotelrunner_obs_rate_limit_drops": _HOTELRUNNER_OBS_RATE_LIMIT_DROP_COUNT,
        "static_client_disconnect_drops": _STATIC_CLIENT_DISCONNECT_DROP_COUNT,
        "asgi_incomplete_response_drops": _ASGI_INCOMPLETE_RESPONSE_DROP_COUNT,
    }


# Environments where a SUSTAINED transient-DB escalation is a real incident and
# must still page Sentry. Everywhere else (dev / digitalocean-dev / stress) the
# workflow console already carries the WARNING/ERROR streak, so the Sentry page
# is pure noise from inherently flaky non-prod Atlas connectivity.
_TRANSIENT_DB_ALERT_ENVS = frozenset({"production", "prod", "pilot"})
_TRANSIENT_DB_NONPROD_DROP_COUNT = 0


def _is_nonprod_sustained_transient_db(event: dict) -> bool:
    """Drop predicate for the ``TransientFailureTracker`` sustained-streak ERROR
    in non-production environments.

    The transient_db_guard escalates a *sustained* Atlas outage
    (``streak >= threshold``) to ERROR via the log template
    ``"... sustained transient db error ..."``. In production/pilot that
    escalation is a real, actionable incident and must page. In
    dev/digitalocean-dev/stress the Atlas link is inherently flaky and the workflow
    console already carries the WARNING/ERROR streak, so the Sentry page is pure
    noise. We require BOTH a non-prod environment AND the literal log-template
    substring — we never drop on environment alone, so every other event
    (including non-transient/real-bug ERRORs) still flows to Sentry.
    """
    try:
        env = (os.environ.get("SENTRY_ENVIRONMENT", "development") or "").strip().lower()
        if env in _TRANSIENT_DB_ALERT_ENVS:
            return False
        le = event.get("logentry") or {}
        ev_msg = event.get("message")
        candidates = (
            le.get("message"),
            le.get("formatted"),
            ev_msg if isinstance(ev_msg, str) else None,
        )
        return any(c and "sustained transient db error" in c for c in candidates)
    except Exception:
        return False


# Counter for filtered GraphQL introspection-denied events. Exposed via
# ``get_sentry_filter_stats()`` so ops can confirm the noise is gone without
# paging the on-call channel.
_GRAPHQL_INTROSPECTION_DENIED_DROP_COUNT = 0

# Exact denial template emitted by graphql-core's NoSchemaIntrospectionCustomRule:
#   "GraphQL introspection has been disabled, but the requested query contained
#    the field '<field>'."
# We anchor on the FULL template (not the bare substring) so a genuine error
# that merely mentions the phrase is never dropped. ``search`` (not ``match``)
# tolerates a logger prefix while still requiring the complete denial structure.
_GRAPHQL_INTROSPECTION_DENIED_RE = re.compile(
    r"GraphQL introspection has been disabled, but the requested query "
    r"contained the field '[^']*'\."
)


def _is_graphql_introspection_denied(event: dict) -> bool:
    """Drop predicate for the EXPECTED GraphQL introspection-disabled rejection.

    When ``GRAPHQL_INTROSPECTION`` is off (production/pilot/stress default), the
    ``NoSchemaIntrospectionCustomRule`` validation rule rejects any query that
    touches ``__schema``/``__type`` with a ``GraphQLError`` whose message reads
    ``"GraphQL introspection has been disabled, but the requested query
    contained the field '...'."``. Strawberry logs that validation error at
    ERROR on the ``strawberry.execution`` logger, so the default Sentry logging
    integration turns every such *expected policy denial* into a paging event.

    This is a client-side denial (the security control working as intended), not
    a server fault, so it must never page in ANY environment — dropping it does
    NOT weaken the control: introspection stays disabled and the query is still
    rejected. We match ONLY the full graphql-core denial template
    (``_GRAPHQL_INTROSPECTION_DENIED_RE``), so a genuine GraphQL error that
    merely mentions the phrase still flows to Sentry.
    """
    try:
        le = event.get("logentry") or {}
        ev_msg = event.get("message")
        candidates = [
            le.get("message"),
            le.get("formatted"),
            ev_msg if isinstance(ev_msg, str) else None,
        ]
        exc = event.get("exception") or {}
        for val in exc.get("values") or []:
            if isinstance(val, dict):
                candidates.append(val.get("value"))
        return any(isinstance(c, str) and _GRAPHQL_INTROSPECTION_DENIED_RE.search(c) for c in candidates)
    except Exception:
        return False


# ── GraphQL field-validation (bad client query) noise ──────────────
# Counter for filtered GraphQL field-validation events. Exposed via
# ``get_sentry_filter_stats()`` so ops can confirm the noise is gone.
_GRAPHQL_FIELD_VALIDATION_DROP_COUNT = 0

# graphql-core emits this EXACT template when a client query references a field
# that does not exist on the queried type:
#   "Cannot query field '<field>' on type '<Type>'."
# Strawberry logs that validation error at ERROR on the ``strawberry.execution``
# logger, so the default Sentry logging integration turns every malformed client
# query into a paging event. This is a CLIENT input error (a stale frontend, a
# scanner, or a bad integration), not a server fault — it must never page in ANY
# environment. We anchor on the FULL graphql-core template so a genuine error
# that merely mentions a field name is never dropped.
_GRAPHQL_FIELD_VALIDATION_RE = re.compile(r"Cannot query field '[^']*' on type '[^']*'\.")


def _is_graphql_field_validation_error(event: dict) -> bool:
    """Drop predicate for the EXPECTED GraphQL bad-field client query error."""
    try:
        le = event.get("logentry") or {}
        ev_msg = event.get("message")
        candidates = [
            le.get("message"),
            le.get("formatted"),
            ev_msg if isinstance(ev_msg, str) else None,
        ]
        exc = event.get("exception") or {}
        for val in exc.get("values") or []:
            if isinstance(val, dict):
                candidates.append(val.get("value"))
        return any(isinstance(c, str) and _GRAPHQL_FIELD_VALIDATION_RE.search(c) for c in candidates)
    except Exception:
        return False


# ── HotelRunner PULL expected noise ────────────────────────
# Counter for filtered HotelRunner PULL recoverable events. Exposed via
# ``get_sentry_filter_stats()`` so ops can confirm the noise is gone.
_HOTELRUNNER_PULL_RATE_LIMIT_DROP_COUNT = 0

# The sync engine logs an ERROR for every PULL page that fails. When that
# failure is an EXTERNAL HotelRunner 429 (rate limit) or a transient network
# error (timeout/5xx), the client layer has ALREADY exhausted its retries 
# and the scheduler backs off — the per-attempt ERROR is expected operational
# backpressure, not a server fault. The real "sync is behind" signal is the
# separate channel-manager backlog alert, so this per-page ERROR is pure
# Sentry noise. We anchor on the FULL log template AND the recoverable signatures
# in sequence (``re.search`` tolerates a logger prefix) so a genuine unrecoverable
# PULL failure (auth / parse) still pages. We never lower the source log level
# — the ERROR stays visible in the workflow console.
_HOTELRUNNER_PULL_RECOVERABLE_RE = re.compile(r"\[PULL\] Failed for tenant .+ page \d+:.*(?:Rate limit exceeded|timeout|Server error|Temporary provider error)", re.IGNORECASE)


def _is_hotelrunner_pull_rate_limited(event: dict) -> bool:
    """Drop predicate for the EXPECTED HotelRunner PULL backpressure/transient log."""
    try:
        le = event.get("logentry") or {}
        ev_msg = event.get("message")
        candidates = [
            le.get("message"),
            le.get("formatted"),
            ev_msg if isinstance(ev_msg, str) else None,
        ]
        exc = event.get("exception") or {}
        for val in exc.get("values") or []:
            if isinstance(val, dict):
                candidates.append(val.get("value"))
        return any(isinstance(c, str) and _HOTELRUNNER_PULL_RECOVERABLE_RE.search(c) for c in candidates)
    except Exception:
        return False


# ── HotelRunner provider-observability rate-limit (429) noise ──────
# Counter for filtered HotelRunner [HR-OBS] 429 events. Exposed via
# ``get_sentry_filter_stats()`` so ops can confirm the noise is gone.
_HOTELRUNNER_OBS_RATE_LIMIT_DROP_COUNT = 0

# The provider observability layer logs an ERROR for EVERY failed provider call
# via the template ``"[HR-OBS] FAILURE <ErrorType>: <msg> (conn=.. path=..)"``.
# When that failure is a 429 (HotelRunner throttling OUR push), the queue worker
# has ALREADY caught it, set a cooldown, and scheduled an auto-retry — it is
# expected operational backpressure, not a server fault. This is the PUSH-side
# sibling of the PULL 429 noise above (different log template), so it gets the
# same treatment: drop ONLY the 429 variant in Sentry while every other
# [HR-OBS] FAILURE (auth / payload / parse / mapping) still pages, and the source
# ERROR stays visible in the workflow console. We require BOTH the
# HotelRunnerRateLimitError type AND the literal ``(429)`` status the client
# embeds in the message, so the predicate is anchored to the real 429 path and
# cannot swallow a same-typed error that lacks the status token.
_HOTELRUNNER_OBS_RATE_LIMIT_RE = re.compile(r"\[HR-OBS\] FAILURE HotelRunnerRateLimitError:.*Rate limit exceeded \(429\)")


def _is_hotelrunner_obs_rate_limited(event: dict) -> bool:
    """Drop predicate for the EXPECTED HotelRunner [HR-OBS] PUSH 429 backpressure."""
    try:
        le = event.get("logentry") or {}
        ev_msg = event.get("message")
        candidates = [
            le.get("message"),
            le.get("formatted"),
            ev_msg if isinstance(ev_msg, str) else None,
        ]
        exc = event.get("exception") or {}
        for val in exc.get("values") or []:
            if isinstance(val, dict):
                candidates.append(val.get("value"))
        return any(isinstance(c, str) and _HOTELRUNNER_OBS_RATE_LIMIT_RE.search(c) for c in candidates)
    except Exception:
        return False


# ── Static-asset client-disconnect noise ───────────────────────────
# Counter for filtered static client-disconnect events.
_STATIC_CLIENT_DISCONNECT_DROP_COUNT = 0

# uvicorn raises ``RuntimeError("Response content shorter than Content-Length")``
# when a client disconnects mid-download: StaticFiles set Content-Length from the
# file size, then the socket closed before all bytes were flushed. Mobile
# browsers cancel asset requests aggressively (prefetch / fast navigation), so
# this is benign client backpressure — we cannot stop a client from
# disconnecting. We drop it ONLY for GET/HEAD requests to static-asset paths, so
# a genuine Content-Length mismatch on an API endpoint (a real truncation bug)
# still pages.
_CONTENT_LENGTH_SHORT_MSG = "Response content shorter than Content-Length"
_STATIC_PATH_PREFIXES = ("/js/", "/assets/", "/logos/", "/landing/")
# Deliberately excludes data-ish extensions (json/txt) so a real API truncation
# never gets silenced — only true asset files qualify.
_STATIC_EXT_RE = re.compile(
    r"\.(?:js|mjs|css|map|png|jpe?g|gif|svg|webp|avif|ico|woff2?|ttf|otf|eot|wasm)"
    r"(?:[?#]|$)"
)


def _event_request_target(event: dict) -> tuple[str, str]:
    """Return ``(method, path)`` from a Sentry event, best-effort.

    ``path`` keeps the URL path only (scheme/host/query stripped) when a full
    URL is present; otherwise the raw value. Empty path if request context is
    unavailable.
    """
    try:
        req = event.get("request") or {}
        method = req.get("method")
        method = method.upper() if isinstance(method, str) else "GET"
        url = req.get("url")
        if not isinstance(url, str) or not url:
            return method, ""
        m = re.match(r"^[a-zA-Z][\w+.\-]*://[^/]+(/.*)?$", url)
        target = (m.group(1) or "/") if m else url
        target = target.split("?", 1)[0].split("#", 1)[0]
        return method, target
    except Exception:
        return "GET", ""


def _is_static_asset_target(method: str, path: str) -> bool:
    if method not in ("GET", "HEAD"):
        return False
    if not path:
        return False
    # Prefix-anchored (startswith), NOT substring: an API path that merely
    # contains a static-looking segment (e.g. ``/api/v2/assets/export``) must
    # NOT be classified static, or a genuine API truncation there is silenced.
    if any(path.startswith(p) for p in _STATIC_PATH_PREFIXES):
        return True
    return bool(_STATIC_EXT_RE.search(path))


def _is_static_client_disconnect(event: dict, hint: dict) -> bool:
    """Drop predicate for benign static-asset client-disconnect RuntimeErrors."""
    try:
        msg = ""
        exc_info = (hint or {}).get("exc_info")
        if exc_info and len(exc_info) >= 2 and exc_info[1] is not None:
            msg = str(exc_info[1])
        if _CONTENT_LENGTH_SHORT_MSG not in msg:
            candidates = []
            exc = event.get("exception") or {}
            for val in exc.get("values") or []:
                if isinstance(val, dict):
                    candidates.append(val.get("value"))
            le = event.get("logentry") or {}
            candidates.append(le.get("message"))
            candidates.append(le.get("formatted"))
            em = event.get("message")
            candidates.append(em if isinstance(em, str) else None)
            if not any(isinstance(c, str) and _CONTENT_LENGTH_SHORT_MSG in c for c in candidates):
                return False
        method, path = _event_request_target(event)
        return _is_static_asset_target(method, path)
    except Exception:
        return False


# ── uvicorn "incomplete response" client-disconnect artifact ───────
# Counter for filtered uvicorn incomplete-response events.
_ASGI_INCOMPLETE_RESPONSE_DROP_COUNT = 0

# uvicorn logs this EXACT message on the ``uvicorn.error`` logger when the ASGI
# app returns after the response STARTED but before it COMPLETED, and the
# disconnect was not yet observed (``response_complete is False and not
# disconnected``). This is emitted in the SAME asyncio task right after ``app``
# returns, AFTER the request scope is torn down — so the event carries no request
# context to path-scope on, and the message ALONE cannot tell a benign static
# client-disconnect apart from a real handler bug (a streaming/SSE/export route
# that starts a response then returns without completing it logs the IDENTICAL
# line). We therefore drop it ONLY when the StaticDisconnectSilencer just
# swallowed a benign static disconnect for THIS same request (its per-request
# ContextVar is True). A real mid-response handler bug never swallows → the flag
# is False → it still pages. We additionally anchor on the FULL template (the
# sibling "...without STARTING response." is a real no-response condition and is
# NOT matched) and, when a logger field is present, require ``uvicorn.error``.
# The ERROR still prints to the workflow console; only the Sentry page is dropped.
_ASGI_INCOMPLETE_RESPONSE_RE = re.compile(r"ASGI callable returned without completing response\.")


def _is_asgi_incomplete_response_noise(event: dict) -> bool:
    """Drop predicate for the benign uvicorn incomplete-response disconnect log.

    Requires BOTH the exact uvicorn template AND a positive per-request
    correlation with the StaticDisconnectSilencer (it just swallowed a benign
    static disconnect in this same task/context). Without that correlation the
    same log line may be a genuine mid-response handler bug, which must page.
    """
    try:
        # Correlation gate first: only the static silencer's follow-on log.
        try:
            from middleware.static_disconnect_silencer import (
                benign_static_disconnect_in_flight,
            )
        except Exception:
            return False
        if not benign_static_disconnect_in_flight():
            return False
        # If Sentry tagged a logger, it must be uvicorn's error logger; absent is
        # tolerated (older SDKs may omit it) since the correlation already binds.
        logger_name = event.get("logger")
        if logger_name is not None and logger_name != "uvicorn.error":
            return False
        le = event.get("logentry") or {}
        ev_msg = event.get("message")
        candidates = [
            le.get("message"),
            le.get("formatted"),
            ev_msg if isinstance(ev_msg, str) else None,
        ]
        exc = event.get("exception") or {}
        for val in exc.get("values") or []:
            if isinstance(val, dict):
                candidates.append(val.get("value"))
        return any(isinstance(c, str) and _ASGI_INCOMPLETE_RESPONSE_RE.search(c) for c in candidates)
    except Exception:
        return False


def _sentry_before_send(event: dict, hint: dict) -> dict | None:
    """Sentry SDK ``before_send`` hook — restart-noise filter + PII scrub.

    Returns ``None`` for two noise classes: transient workflow-restart
    port-bind noise (see ``_is_workflow_restart_port_bind``) and, in
    non-production environments only, the sustained-transient-DB escalation
    (see ``_is_nonprod_sustained_transient_db``). Dropped events are counted
    and logged at INFO so the underlying condition stays visible in the
    workflow console even when it no longer pages Sentry. All other events go
    through after PII scrub — we never drop on scrubber failure.
    """
    global _RESTART_BIND_DROP_COUNT, _TRANSIENT_DB_NONPROD_DROP_COUNT
    global _GRAPHQL_INTROSPECTION_DENIED_DROP_COUNT
    global _GRAPHQL_FIELD_VALIDATION_DROP_COUNT
    global _HOTELRUNNER_PULL_RATE_LIMIT_DROP_COUNT
    global _HOTELRUNNER_OBS_RATE_LIMIT_DROP_COUNT
    global _STATIC_CLIENT_DISCONNECT_DROP_COUNT
    global _ASGI_INCOMPLETE_RESPONSE_DROP_COUNT
    try:
        if _is_graphql_introspection_denied(event):
            _GRAPHQL_INTROSPECTION_DENIED_DROP_COUNT += 1
            logger.info(f"sentry before_send dropped expected graphql introspection-denied (cumulative={_GRAPHQL_INTROSPECTION_DENIED_DROP_COUNT})")
            return None
    except Exception:
        pass
    try:
        if _is_graphql_field_validation_error(event):
            _GRAPHQL_FIELD_VALIDATION_DROP_COUNT += 1
            logger.info(f"sentry before_send dropped expected graphql field-validation client error (cumulative={_GRAPHQL_FIELD_VALIDATION_DROP_COUNT})")
            return None
    except Exception:
        pass
    try:
        if _is_hotelrunner_pull_rate_limited(event):
            _HOTELRUNNER_PULL_RATE_LIMIT_DROP_COUNT += 1
            logger.info(f"sentry before_send dropped expected hotelrunner PULL 429 backpressure (cumulative={_HOTELRUNNER_PULL_RATE_LIMIT_DROP_COUNT})")
            return None
    except Exception:
        pass
    try:
        if _is_hotelrunner_obs_rate_limited(event):
            _HOTELRUNNER_OBS_RATE_LIMIT_DROP_COUNT += 1
            logger.info(f"sentry before_send dropped expected hotelrunner [HR-OBS] 429 backpressure (cumulative={_HOTELRUNNER_OBS_RATE_LIMIT_DROP_COUNT})")
            return None
    except Exception:
        pass
    try:
        if _is_static_client_disconnect(event, hint):
            _STATIC_CLIENT_DISCONNECT_DROP_COUNT += 1
            logger.info(f"sentry before_send dropped benign static client-disconnect (cumulative={_STATIC_CLIENT_DISCONNECT_DROP_COUNT})")
            return None
    except Exception:
        pass
    try:
        if _is_asgi_incomplete_response_noise(event):
            _ASGI_INCOMPLETE_RESPONSE_DROP_COUNT += 1
            logger.info(f"sentry before_send dropped benign uvicorn incomplete-response client-disconnect (cumulative={_ASGI_INCOMPLETE_RESPONSE_DROP_COUNT})")
            return None
    except Exception:
        pass
    try:
        if _is_workflow_restart_port_bind(event, hint):
            _RESTART_BIND_DROP_COUNT += 1
            logger.info(f"sentry before_send dropped restart-bind noise (cumulative={_RESTART_BIND_DROP_COUNT})")
            return None
    except Exception:
        pass
    try:
        if _is_nonprod_sustained_transient_db(event):
            _TRANSIENT_DB_NONPROD_DROP_COUNT += 1
            logger.info(f"sentry before_send dropped non-prod sustained-transient-db noise (cumulative={_TRANSIENT_DB_NONPROD_DROP_COUNT})")
            return None
    except Exception:
        pass
    try:
        _scrub_event_inplace(event)
    except Exception as e:
        logger.warning(f"sentry before_send scrub failed: {e}")
    return event


# ── OpenTelemetry Integration ──────────────────────────────────────


class OTelTracer:
    """OpenTelemetry tracing abstraction with graceful fallback."""

    def __init__(self):
        self._endpoint = os.environ.get("OTEL_EXPORTER_ENDPOINT", "")
        self._service_name = os.environ.get("OTEL_SERVICE_NAME", "syroce-pms")
        self._tracer = None
        self._active = False
        self._spans_created = 0
        self._spans_exported = 0
        self._export_errors = 0

    async def initialize(self):
        if not self._endpoint:
            logger.info("OTEL_EXPORTER_ENDPOINT not set — tracing disabled")
            return

        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            resource = Resource.create({"service.name": self._service_name})
            provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(endpoint=self._endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer(self._service_name)
            self._active = True
            logger.info(f"OpenTelemetry initialized: {self._endpoint}")
        except ImportError:
            logger.warning("OpenTelemetry SDK not installed — tracing unavailable")
        except Exception as e:
            logger.error(f"OpenTelemetry init failed: {e}")

    def start_span(self, name: str, attributes: dict | None = None):
        self._spans_created += 1
        if self._tracer and self._active:
            span = self._tracer.start_span(name)
            if attributes:
                for k, v in attributes.items():
                    span.set_attribute(k, str(v))
            return span
        return _NoOpSpan()

    def get_status(self) -> dict[str, Any]:
        return {
            "active": self._active,
            "endpoint": self._endpoint or "not configured",
            "service_name": self._service_name,
            "spans_created": self._spans_created,
            "spans_exported": self._spans_exported,
            "export_errors": self._export_errors,
        }


class _NoOpSpan:
    """No-op span for when tracing is disabled."""

    def set_attribute(self, key, value):
        pass

    def set_status(self, status):
        pass

    def end(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


# ── Sentry Integration ──────────────────────────────────────────────


class SentryIntegration:
    """Sentry error tracking abstraction."""

    def __init__(self):
        self._dsn = os.environ.get("SENTRY_DSN", "")
        self._environment = os.environ.get("SENTRY_ENVIRONMENT", "development")
        self._active = False
        self._events_sent = 0
        self._errors_captured = 0

    async def initialize(self):
        if not self._dsn:
            logger.info("SENTRY_DSN not set — Sentry disabled")
            return

        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.starlette import StarletteIntegration

            integrations = [StarletteIntegration(), FastApiIntegration()]
            try:
                from sentry_sdk.integrations.celery import CeleryIntegration

                integrations.append(CeleryIntegration())
            except (ImportError, Exception):
                pass

            sentry_sdk.init(
                dsn=self._dsn,
                environment=self._environment,
                traces_sample_rate=0.1,
                profiles_sample_rate=0.1,
                integrations=integrations,
                send_default_pii=False,
                before_send=_sentry_before_send,
            )
            self._active = True
            logger.info(f"Sentry initialized: env={self._environment} (PII scrub active)")
        except ImportError:
            logger.warning("sentry-sdk not installed — error tracking unavailable")
        except Exception as e:
            logger.error(f"Sentry init failed: {e}")

    def capture_error(self, error: Exception, tags: dict | None = None):
        self._errors_captured += 1
        if not self._active:
            return
        try:
            import sentry_sdk

            with sentry_sdk.push_scope() as scope:
                if tags:
                    for k, v in tags.items():
                        scope.set_tag(k, str(v))
                sentry_sdk.capture_exception(error)
                self._events_sent += 1
        except Exception:
            pass

    def capture_message(self, message: str, level: str = "info", tags: dict | None = None):
        if not self._active:
            return
        try:
            import sentry_sdk

            with sentry_sdk.push_scope() as scope:
                if tags:
                    for k, v in tags.items():
                        scope.set_tag(k, str(v))
                sentry_sdk.capture_message(message, level=level)
                self._events_sent += 1
        except Exception:
            pass

    def get_status(self) -> dict[str, Any]:
        return {
            "active": self._active,
            "dsn_configured": bool(self._dsn),
            "environment": self._environment,
            "events_sent": self._events_sent,
            "errors_captured": self._errors_captured,
        }


# ── Enhanced Metrics Collector ─────────────────────────────────────


class CloudMetricsCollector:
    """Extended metrics for cloud observability."""

    def __init__(self):
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = defaultdict(float)
        self._max_histogram_size = 1000

    def record_latency(self, name: str, duration_sec: float):
        """Record latency histogram sample."""
        self._histograms[name].append(duration_sec)
        if len(self._histograms[name]) > self._max_histogram_size:
            self._histograms[name] = self._histograms[name][-self._max_histogram_size :]

    def increment(self, name: str, value: int = 1):
        self._counters[name] += value

    def set_gauge(self, name: str, value: float):
        self._gauges[name] = value

    def get_percentile(self, name: str, percentile: float = 0.95) -> float:
        data = sorted(self._histograms.get(name, []))
        if not data:
            return 0.0
        idx = int(len(data) * percentile)
        return round(data[min(idx, len(data) - 1)], 4)

    def get_summary(self) -> dict[str, Any]:
        latency_summary = {}
        for name, values in self._histograms.items():
            if values:
                latency_summary[name] = {
                    "count": len(values),
                    "avg": round(sum(values) / len(values), 4),
                    "p50": self.get_percentile(name, 0.5),
                    "p95": self.get_percentile(name, 0.95),
                    "p99": self.get_percentile(name, 0.99),
                    "max": round(max(values), 4),
                }
        return {
            "latency": latency_summary,
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
        }


# ── Singletons ─────────────────────────────────────────────────────
otel_tracer = OTelTracer()
sentry_integration = SentryIntegration()
cloud_metrics = CloudMetricsCollector()
