"""
Operational Monitoring — Data Models
======================================

Alert model and monitoring constants.
Collection: monitoring_alerts
"""
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

COLL_MONITORING_ALERTS = "monitoring_alerts"


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    INFO = "info"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertType(str, Enum):
    # Provider Health
    PROVIDER_CONNECTION_FAILURE = "provider_connection_failure"
    AUTH_FAILURE = "auth_failure"
    ERROR_RATE_SPIKE = "error_rate_spike"
    API_LATENCY_SPIKE = "api_latency_spike"
    # Ingest Pipeline
    INGEST_PIPELINE_FAILURE = "ingest_pipeline_failure"
    FAILED_INGEST_SPIKE = "failed_ingest_spike"
    # ARI Push Engine
    ARI_PUSH_FAILURE = "ari_push_failure"
    RETRY_BACKLOG_GROWTH = "retry_backlog_growth"
    # Reconciliation
    STATUS_CONFLICT_DETECTED = "status_conflict_detected"
    OVERBOOKING_RISK = "overbooking_risk"
    AMOUNT_MISMATCH_SPIKE = "amount_mismatch_spike"
    MISSING_RESERVATION_SPIKE = "missing_reservation_spike"
    # Queue & Worker
    WORKER_STALLED = "worker_stalled"
    QUEUE_OVERFLOW = "queue_overflow"


ALERT_SEVERITY_MAP = {
    AlertType.PROVIDER_CONNECTION_FAILURE: AlertSeverity.CRITICAL,
    AlertType.AUTH_FAILURE: AlertSeverity.CRITICAL,
    AlertType.ERROR_RATE_SPIKE: AlertSeverity.HIGH,
    AlertType.API_LATENCY_SPIKE: AlertSeverity.HIGH,
    AlertType.INGEST_PIPELINE_FAILURE: AlertSeverity.CRITICAL,
    AlertType.FAILED_INGEST_SPIKE: AlertSeverity.HIGH,
    AlertType.ARI_PUSH_FAILURE: AlertSeverity.CRITICAL,
    AlertType.RETRY_BACKLOG_GROWTH: AlertSeverity.HIGH,
    AlertType.STATUS_CONFLICT_DETECTED: AlertSeverity.CRITICAL,
    AlertType.OVERBOOKING_RISK: AlertSeverity.CRITICAL,
    AlertType.AMOUNT_MISMATCH_SPIKE: AlertSeverity.HIGH,
    AlertType.MISSING_RESERVATION_SPIKE: AlertSeverity.HIGH,
    AlertType.WORKER_STALLED: AlertSeverity.CRITICAL,
    AlertType.QUEUE_OVERFLOW: AlertSeverity.CRITICAL,
}


class MonitoringAlert(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = "system"
    provider: str = ""
    property_id: str = ""

    alert_type: str
    severity: str
    title: str
    details: str = ""

    metric_value: float | None = None
    threshold: float | None = None

    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    resolved_at: str | None = None
    acknowledged_at: str | None = None
    status: str = AlertStatus.ACTIVE.value

    def to_doc(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "MonitoringAlert":
        doc.pop("_id", None)
        return cls(**doc)
