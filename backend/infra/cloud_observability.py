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

# Managed ports: dev workflow (8000) and Replit deployment (5000).
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
    return {"restart_bind_drops": _RESTART_BIND_DROP_COUNT}


def _sentry_before_send(event: dict, hint: dict) -> dict | None:
    """Sentry SDK ``before_send`` hook — restart-noise filter + PII scrub.

    Returns ``None`` only for transient workflow-restart port-bind noise
    (see ``_is_workflow_restart_port_bind``). Dropped events are counted
    and logged at INFO so persistent bind conflicts remain visible in
    the workflow console even when they no longer page Sentry. All
    other events go through after PII scrub — we never drop on scrubber
    failure.
    """
    global _RESTART_BIND_DROP_COUNT
    try:
        if _is_workflow_restart_port_bind(event, hint):
            _RESTART_BIND_DROP_COUNT += 1
            logger.info(
                "sentry before_send dropped restart-bind noise "
                f"(cumulative={_RESTART_BIND_DROP_COUNT})"
            )
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
    def set_attribute(self, key, value): pass
    def set_status(self, status): pass
    def end(self): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass


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

    def capture_message(self, message: str, level: str = "info",
                        tags: dict | None = None):
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
            self._histograms[name] = self._histograms[name][-self._max_histogram_size:]

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
