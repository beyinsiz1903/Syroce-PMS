"""
Operational Monitoring — Alert Engine
=======================================

Evaluates collected metrics against defined thresholds.
Creates alert events when thresholds are breached.
Auto-resolves alerts when metrics return to normal.
"""
import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db

from .models import (
    ALERT_SEVERITY_MAP,
    COLL_MONITORING_ALERTS,
    AlertSeverity,
    AlertStatus,
    AlertType,
    MonitoringAlert,
)

logger = logging.getLogger("monitoring.alert_engine")

_NO_ID = {"_id": 0}

# ── Threshold Definitions ────────────────────────────────────────────

THRESHOLDS = {
    # Provider Health
    "provider_consecutive_failures": 3,
    "provider_error_rate": 20.0,
    # Ingest Pipeline
    "ingest_failed_24h": 10,
    "ingest_pending_queue": 200,
    # ARI Push
    "ari_success_rate_min": 85.0,
    "ari_pending_changesets": 100,
    # Reconciliation
    "recon_critical_cases": 1,
    "recon_open_cases": 30,
    "recon_status_conflicts": 1,
    "recon_missing_reservations": 5,
    "recon_amount_mismatches": 5,
    # Queue & Worker
    "queue_depth_max": 300,
    "worker_stalled_count": 1,
}


async def evaluate_alerts(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Evaluate all collected metrics against thresholds.
    Returns list of alerts to create/resolve.
    """
    new_alerts: list[dict[str, Any]] = []

    # 1. Provider Health Alerts
    provider_health = metrics.get("provider_health", {})
    for provider_name, pdata in provider_health.get("providers", {}).items():
        consec = pdata.get("consecutive_failures", 0)
        if consec >= THRESHOLDS["provider_consecutive_failures"]:
            new_alerts.append(_build_alert(
                AlertType.PROVIDER_CONNECTION_FAILURE,
                provider=provider_name,
                title=f"{provider_name} baglanti hatasi",
                details=f"Ardisik hata sayisi: {consec}",
                metric_value=consec,
                threshold=THRESHOLDS["provider_consecutive_failures"],
            ))

        error_rate = pdata.get("api_error_rate", 0)
        if error_rate > THRESHOLDS["provider_error_rate"]:
            new_alerts.append(_build_alert(
                AlertType.ERROR_RATE_SPIKE,
                provider=provider_name,
                title=f"{provider_name} hata orani yuksek",
                details=f"API hata orani: %{error_rate}",
                metric_value=error_rate,
                threshold=THRESHOLDS["provider_error_rate"],
            ))

    # 2. Ingest Pipeline Alerts
    ingest = metrics.get("ingest_health", {})
    failed_24h = ingest.get("failed_recent_24h", 0)
    if failed_24h >= THRESHOLDS["ingest_failed_24h"]:
        new_alerts.append(_build_alert(
            AlertType.FAILED_INGEST_SPIKE,
            title="Ingest pipeline basarisiz islem artisi",
            details=f"Son 24 saatte {failed_24h} basarisiz islem",
            metric_value=failed_24h,
            threshold=THRESHOLDS["ingest_failed_24h"],
        ))

    pending = ingest.get("pending", 0)
    if pending >= THRESHOLDS["ingest_pending_queue"]:
        new_alerts.append(_build_alert(
            AlertType.INGEST_PIPELINE_FAILURE,
            title="Ingest pipeline kuyrugu doldu",
            details=f"Bekleyen event sayisi: {pending}",
            metric_value=pending,
            threshold=THRESHOLDS["ingest_pending_queue"],
        ))

    # 3. ARI Push Alerts
    ari = metrics.get("ari_health", {})
    success_rate = ari.get("success_rate", 100)
    if success_rate < THRESHOLDS["ari_success_rate_min"]:
        new_alerts.append(_build_alert(
            AlertType.ARI_PUSH_FAILURE,
            title="ARI push basari orani dusuk",
            details=f"Basari orani: %{success_rate}",
            metric_value=success_rate,
            threshold=THRESHOLDS["ari_success_rate_min"],
        ))

    pending_cs = ari.get("pending_changesets", 0)
    if pending_cs >= THRESHOLDS["ari_pending_changesets"]:
        new_alerts.append(_build_alert(
            AlertType.RETRY_BACKLOG_GROWTH,
            title="ARI retry kuyrugu buyuyor",
            details=f"Bekleyen changeset: {pending_cs}",
            metric_value=pending_cs,
            threshold=THRESHOLDS["ari_pending_changesets"],
        ))

    # 4. Reconciliation Alerts
    recon = metrics.get("reconciliation_health", {})
    by_type = recon.get("cases_by_type", {})
    by_severity = recon.get("cases_by_severity", {})

    critical_cases = by_severity.get("critical", 0)
    if critical_cases >= THRESHOLDS["recon_critical_cases"]:
        new_alerts.append(_build_alert(
            AlertType.OVERBOOKING_RISK,
            title="Kritik reconciliation vakalari tespit edildi",
            details=f"Kritik vaka sayisi: {critical_cases}",
            metric_value=critical_cases,
            threshold=THRESHOLDS["recon_critical_cases"],
        ))

    status_conflicts = by_type.get("status_conflict", 0)
    if status_conflicts >= THRESHOLDS["recon_status_conflicts"]:
        new_alerts.append(_build_alert(
            AlertType.STATUS_CONFLICT_DETECTED,
            title="Durum catismasi tespit edildi",
            details=f"Status conflict sayisi: {status_conflicts}",
            metric_value=status_conflicts,
            threshold=THRESHOLDS["recon_status_conflicts"],
        ))

    missing_res = by_type.get("missing_reservation", 0)
    if missing_res >= THRESHOLDS["recon_missing_reservations"]:
        new_alerts.append(_build_alert(
            AlertType.MISSING_RESERVATION_SPIKE,
            title="Eksik rezervasyon artisi",
            details=f"Eksik rezervasyon sayisi: {missing_res}",
            metric_value=missing_res,
            threshold=THRESHOLDS["recon_missing_reservations"],
        ))

    amount_mm = by_type.get("amount_mismatch", 0)
    if amount_mm >= THRESHOLDS["recon_amount_mismatches"]:
        new_alerts.append(_build_alert(
            AlertType.AMOUNT_MISMATCH_SPIKE,
            title="Tutar uyusmazligi artisi",
            details=f"Amount mismatch sayisi: {amount_mm}",
            metric_value=amount_mm,
            threshold=THRESHOLDS["recon_amount_mismatches"],
        ))

    # 5. Queue & Worker Alerts
    queue = metrics.get("queue_health", {})
    stalled = queue.get("stalled_workers", [])
    if len(stalled) >= THRESHOLDS["worker_stalled_count"]:
        new_alerts.append(_build_alert(
            AlertType.WORKER_STALLED,
            title="Worker durdu",
            details=f"Duran worker'lar: {', '.join(stalled)}",
            metric_value=len(stalled),
            threshold=THRESHOLDS["worker_stalled_count"],
        ))

    queue_depth = queue.get("queue_depth", 0)
    if queue_depth >= THRESHOLDS["queue_depth_max"]:
        new_alerts.append(_build_alert(
            AlertType.QUEUE_OVERFLOW,
            title="Kuyruk tasmasi riski",
            details=f"Kuyruk derinligi: {queue_depth}",
            metric_value=queue_depth,
            threshold=THRESHOLDS["queue_depth_max"],
        ))

    return new_alerts


async def process_alerts(new_alerts: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Process alert list: create new alerts, auto-resolve stale ones.
    Prevents duplicate active alerts for the same alert_type + provider.
    """
    created = 0
    resolved = 0
    skipped = 0

    active_types = set()

    for alert_data in new_alerts:
        alert_type = alert_data["alert_type"]
        provider = alert_data.get("provider", "")
        active_types.add((alert_type, provider))

        existing = await db[COLL_MONITORING_ALERTS].find_one(
            {
                "alert_type": alert_type,
                "provider": provider,
                "status": {"$in": ["active", "acknowledged"]},
            },
        )

        if existing:
            skipped += 1
            continue

        alert = MonitoringAlert(**alert_data)
        doc = alert.to_doc()
        await db[COLL_MONITORING_ALERTS].insert_one(doc)
        created += 1
        logger.info(f"Alert created: [{alert_data['severity']}] {alert_data['title']}")

        # Dispatch to configured channels (Slack, etc.)
        try:
            from .alert_dispatch import dispatch_alert
            await dispatch_alert(alert_data)
        except Exception as e:
            logger.warning(f"Alert dispatch failed: {e}")

    # Auto-resolve alerts whose conditions are no longer met
    active_alerts = await db[COLL_MONITORING_ALERTS].find(
        {"status": "active"}, _NO_ID,
    ).to_list(500)

    for alert in active_alerts:
        key = (alert.get("alert_type", ""), alert.get("provider", ""))
        if key not in active_types:
            await db[COLL_MONITORING_ALERTS].update_one(
                {"id": alert["id"]},
                {"$set": {
                    "status": AlertStatus.RESOLVED.value,
                    "resolved_at": datetime.now(UTC).isoformat(),
                }},
            )
            resolved += 1
            logger.info(f"Alert auto-resolved: {alert.get('title', '?')}")

    return {"created": created, "resolved": resolved, "skipped": skipped}


def _build_alert(
    alert_type: AlertType,
    title: str,
    details: str = "",
    provider: str = "",
    property_id: str = "",
    metric_value: float = 0,
    threshold: float = 0,
) -> dict[str, Any]:
    severity = ALERT_SEVERITY_MAP.get(alert_type, AlertSeverity.MEDIUM)
    return {
        "alert_type": alert_type.value,
        "severity": severity.value,
        "title": title,
        "details": details,
        "provider": provider,
        "property_id": property_id,
        "metric_value": metric_value,
        "threshold": threshold,
    }
