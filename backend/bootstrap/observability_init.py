"""
Bootstrap: Observability Init
Prometheus metrics, OpenTelemetry, Sentry, and structured logging setup.
"""
import os
import logging


def init_observability() -> None:
    """Initialize all observability integrations."""

    # Structured logging
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Sentry
    sentry_dsn = os.environ.get("SENTRY_DSN")
    if sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.starlette import StarletteIntegration
            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[StarletteIntegration(), FastApiIntegration()],
                traces_sample_rate=float(os.environ.get("SENTRY_TRACES_RATE", "0.1")),
                environment=os.environ.get("ENVIRONMENT", "development"),
            )
            logging.info("Sentry initialized")
        except ImportError:
            logging.warning("sentry-sdk not installed – skipping Sentry init")

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
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.resources import Resource
            provider = TracerProvider(resource=Resource.create({"service.name": "hotel-pms-backend"}))
            trace.set_tracer_provider(provider)
            logging.info("OpenTelemetry tracer initialized")
        except ImportError:
            logging.warning("opentelemetry SDK not installed – skipping OTel init")
