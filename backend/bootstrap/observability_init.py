"""
Bootstrap: Observability Init
Prometheus metrics, OpenTelemetry, Sentry, and structured logging setup.
"""

import logging
import os


def init_observability() -> None:
    """Initialize all observability integrations."""

    # Structured logging. LOG_LEVEL may arrive lower-case (e.g. "info") from a
    # deploy platform; getattr(logging, "info") returns the logging.info
    # FUNCTION (truthy, so the 3-arg getattr default is skipped) and
    # basicConfig then raises "Level not an integer or a valid string",
    # crashing every uvicorn worker at import. Normalize to upper-case and fall
    # back to INFO unless the name resolves to a real int level constant.
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    if not isinstance(log_level, int):
        log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
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
