"""
Cloud Observability Stack — OpenTelemetry tracing, Sentry error tracking,
enhanced Prometheus metrics, and Grafana dashboard configs.

Environment:
    OTEL_EXPORTER_ENDPOINT — OpenTelemetry collector endpoint
    OTEL_SERVICE_NAME      — Service name (default: syroce-pms)
    SENTRY_DSN             — Sentry DSN for error tracking
    SENTRY_ENVIRONMENT     — Sentry environment tag
"""
import logging
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("infra.observability")


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

    def start_span(self, name: str, attributes: Optional[Dict] = None):
        self._spans_created += 1
        if self._tracer and self._active:
            span = self._tracer.start_span(name)
            if attributes:
                for k, v in attributes.items():
                    span.set_attribute(k, str(v))
            return span
        return _NoOpSpan()

    def get_status(self) -> Dict[str, Any]:
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
            from sentry_sdk.integrations.celery import CeleryIntegration
            from sentry_sdk.integrations.fastapi import FastApiIntegration

            sentry_sdk.init(
                dsn=self._dsn,
                environment=self._environment,
                traces_sample_rate=0.1,
                profiles_sample_rate=0.1,
                integrations=[FastApiIntegration(), CeleryIntegration()],
                send_default_pii=False,
            )
            self._active = True
            logger.info(f"Sentry initialized: env={self._environment}")
        except ImportError:
            logger.warning("sentry-sdk not installed — error tracking unavailable")
        except Exception as e:
            logger.error(f"Sentry init failed: {e}")

    def capture_error(self, error: Exception, tags: Optional[Dict] = None):
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
                        tags: Optional[Dict] = None):
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

    def get_status(self) -> Dict[str, Any]:
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
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = defaultdict(float)
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

    def get_summary(self) -> Dict[str, Any]:
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
