"""
Bootstrap: Observability Init
Prometheus metrics, OpenTelemetry, Sentry, and structured logging setup.
"""
import logging
import os


def init_observability() -> None:
    """Initialize all observability integrations."""

    # Structured logging
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Sentry init handled by infra/cloud_observability.py (single source of truth)
    # to avoid double sentry_sdk.init() which overwrites SDK state.

    # Prometheus metrics endpoint is handled by prometheus_metrics.py
    try:
        from infra.prometheus_metrics import setup_metrics  # noqa: F401
        logging.info("Prometheus metrics available")
    except ImportError:
        pass

    # OpenTelemetry
    otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otel_endpoint:
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            provider = TracerProvider(resource=Resource.create({"service.name": "hotel-pms-backend"}))
            trace.set_tracer_provider(provider)
            logging.info("OpenTelemetry tracer initialized")
        except ImportError:
            logging.warning("opentelemetry SDK not installed – skipping OTel init")
