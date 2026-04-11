"""
Early Warning Engine v1 — Trend-based Predictive Alerting
==========================================================

Sprint 4: Rule-based trend detection (NOT ML).

Provides:
  - Trend analysis for operational metrics
  - Early warning detection before actual failures
  - Confidence-based warnings with recommended actions
  - Integration with ops_events for unified telemetry

Warning Types:
  - predictive.warning.degradation_likely    (health_score dropping)
  - predictive.warning.failure_rate_rising   (failure_rate_1h increasing)
  - predictive.warning.backlog_growth        (retry_backlog growing)
  - predictive.warning.dlq_spike             (dlq_count sudden spike)
  - predictive.warning.throttle_risk         (throttle windows increasing)
  - predictive.warning.staleness_risk        (last_success_age growing)
  - predictive.warning.recovery_expected     (metrics improving)

Each warning produces:
  - warning_type
  - provider
  - confidence (0-100)
  - reason
  - detected_at
  - recommended_action
  - impacted_scope
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db
from routers.ops_event_emitter import (
    SEVERITY_WARNING,
    emit_ops_event,
)

logger = logging.getLogger("early_warning_engine")

# ══════════════════════════════════════════════════════════════════════
# Configuration — Thresholds & Weights
# ══════════════════════════════════════════════════════════════════════

# Trend analysis windows
TREND_WINDOW_SHORT = 30    # minutes
TREND_WINDOW_MEDIUM = 90   # minutes
TREND_WINDOW_LONG = 180    # minutes

# Failure rate thresholds
FAILURE_RATE_WARNING_THRESHOLD = 15   # %
FAILURE_RATE_CRITICAL_THRESHOLD = 30  # %
FAILURE_RATE_TREND_THRESHOLD = 10     # % increase between windows

# DLQ thresholds
DLQ_SPIKE_THRESHOLD = 3               # new DLQ items in short window
DLQ_GROWTH_THRESHOLD = 5              # total pending DLQ items

# Retry backlog thresholds
BACKLOG_WARNING_THRESHOLD = 10        # items
BACKLOG_GROWTH_RATE_THRESHOLD = 5     # items/hour

# Staleness thresholds (minutes since last success)
STALENESS_WARNING_MINUTES = 60
STALENESS_CRITICAL_MINUTES = 180

# Health score thresholds
HEALTH_SCORE_WARNING_THRESHOLD = 70
HEALTH_SCORE_CRITICAL_THRESHOLD = 50
HEALTH_SCORE_DROP_THRESHOLD = 15      # points drop triggers warning

# Throttle risk thresholds
THROTTLE_FREQUENCY_THRESHOLD = 3      # events in 1 hour

# Confidence weights
CONFIDENCE_BASE = 50
CONFIDENCE_TREND_BONUS = 20           # add if trend is consistent
CONFIDENCE_SEVERITY_BONUS = 15        # add if multiple signals
CONFIDENCE_HISTORY_BONUS = 15         # add if pattern matches history


# ══════════════════════════════════════════════════════════════════════
# Data Models
# ══════════════════════════════════════════════════════════════════════

class EarlyWarning:
    """Represents a predictive warning."""

    def __init__(
        self,
        warning_type: str,
        provider: str,
        connector_id: str,
        confidence: int,
        reason: str,
        recommended_action: str,
        impacted_scope: str,
        trend_data: dict[str, Any] | None = None,
        severity: str = "warning",
    ):
        self.warning_type = warning_type
        self.provider = provider
        self.connector_id = connector_id
        self.confidence = min(100, max(0, confidence))
        self.reason = reason
        self.recommended_action = recommended_action
        self.impacted_scope = impacted_scope
        self.trend_data = trend_data or {}
        self.severity = severity
        self.detected_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "warning_type": self.warning_type,
            "provider": self.provider,
            "connector_id": self.connector_id,
            "confidence": self.confidence,
            "reason": self.reason,
            "recommended_action": self.recommended_action,
            "impacted_scope": self.impacted_scope,
            "trend_data": self.trend_data,
            "severity": self.severity,
            "detected_at": self.detected_at,
        }


# ══════════════════════════════════════════════════════════════════════
# Trend Data Collectors
# ══════════════════════════════════════════════════════════════════════

async def get_failure_rate_trend(
    tenant_id: str,
    connector_id: str,
    provider: str
) -> dict[str, Any]:
    """Get failure rate trend across multiple time windows."""
    now = datetime.now(UTC)

    windows = {
        "short": (now - timedelta(minutes=TREND_WINDOW_SHORT)).isoformat(),
        "medium": (now - timedelta(minutes=TREND_WINDOW_MEDIUM)).isoformat(),
        "long": (now - timedelta(minutes=TREND_WINDOW_LONG)).isoformat(),
    }

    results = {}
    for window_name, since in windows.items():
        total = await db.cm_rate_push_metrics.count_documents({
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "recorded_at": {"$gte": since},
        })
        failed = await db.cm_rate_push_metrics.count_documents({
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "success": False,
            "recorded_at": {"$gte": since},
        })
        rate = round(failed / max(total, 1) * 100, 1)
        results[window_name] = {
            "total": total,
            "failed": failed,
            "rate": rate,
        }

    # Calculate trend direction
    short_rate = results["short"]["rate"]
    medium_rate = results["medium"]["rate"]
    long_rate = results["long"]["rate"]

    trend_direction = "stable"
    if short_rate > medium_rate > long_rate:
        trend_direction = "rising"
    elif short_rate < medium_rate < long_rate:
        trend_direction = "falling"
    elif short_rate > medium_rate:
        trend_direction = "rising_recent"
    elif short_rate < medium_rate:
        trend_direction = "falling_recent"

    return {
        "windows": results,
        "trend_direction": trend_direction,
        "short_vs_long_delta": round(short_rate - long_rate, 1),
        "short_vs_medium_delta": round(short_rate - medium_rate, 1),
    }


async def get_dlq_trend(tenant_id: str) -> dict[str, Any]:
    """Get DLQ growth trend."""
    from core.tenant_db import get_system_db
    sysdb = get_system_db()

    now = datetime.now(UTC)
    short_since = (now - timedelta(minutes=TREND_WINDOW_SHORT)).isoformat()
    medium_since = (now - timedelta(minutes=TREND_WINDOW_MEDIUM)).isoformat()

    # Current pending count
    pending_count = await sysdb.webhook_dlq.count_documents({
        "tenant_id": tenant_id,
        "status": "pending",
    })

    # Recent additions (short window)
    recent_additions = await sysdb.webhook_dlq.count_documents({
        "tenant_id": tenant_id,
        "created_at": {"$gte": short_since},
    })

    # Medium term additions
    medium_additions = await sysdb.webhook_dlq.count_documents({
        "tenant_id": tenant_id,
        "created_at": {"$gte": medium_since},
    })

    growth_rate = recent_additions  # items per short window

    return {
        "pending_count": pending_count,
        "recent_additions": recent_additions,
        "medium_additions": medium_additions,
        "growth_rate_per_30min": growth_rate,
        "is_spiking": recent_additions >= DLQ_SPIKE_THRESHOLD,
        "is_growing": pending_count >= DLQ_GROWTH_THRESHOLD,
    }


async def get_backlog_trend(tenant_id: str) -> dict[str, Any]:
    """Get retry backlog trend."""
    from core.tenant_db import get_system_db
    sysdb = get_system_db()

    now = datetime.now(UTC)
    short_since = (now - timedelta(minutes=TREND_WINDOW_SHORT)).isoformat()

    # Current backlog
    current_backlog = await sysdb.webhook_deliveries.count_documents({
        "tenant_id": tenant_id,
        "status": "retrying",
    })

    # Recent additions to backlog
    recent_retrying = await sysdb.webhook_deliveries.count_documents({
        "tenant_id": tenant_id,
        "status": "retrying",
        "created_at": {"$gte": short_since},
    })

    return {
        "current_backlog": current_backlog,
        "recent_additions": recent_retrying,
        "is_growing": current_backlog >= BACKLOG_WARNING_THRESHOLD,
        "growth_rate_per_30min": recent_retrying,
    }


async def get_throttle_trend(tenant_id: str, provider: str) -> dict[str, Any]:
    """Get throttle event frequency trend."""
    now = datetime.now(UTC)
    since_1h = (now - timedelta(hours=1)).isoformat()
    since_6h = (now - timedelta(hours=6)).isoformat()
    since_24h = (now - timedelta(hours=24)).isoformat()

    # Throttle events by window
    throttle_1h = await db.ops_events.count_documents({
        "tenant_id": tenant_id,
        "event_type": {"$in": ["rate_limit.active", "push.throttled"]},
        "channel": {"$regex": provider, "$options": "i"},
        "created_at": {"$gte": since_1h},
    })

    throttle_6h = await db.ops_events.count_documents({
        "tenant_id": tenant_id,
        "event_type": {"$in": ["rate_limit.active", "push.throttled"]},
        "channel": {"$regex": provider, "$options": "i"},
        "created_at": {"$gte": since_6h},
    })

    throttle_24h = await db.ops_events.count_documents({
        "tenant_id": tenant_id,
        "event_type": {"$in": ["rate_limit.active", "push.throttled"]},
        "channel": {"$regex": provider, "$options": "i"},
        "created_at": {"$gte": since_24h},
    })

    # Check if frequency is increasing
    avg_6h = throttle_6h / 6  # per hour
    avg_24h = throttle_24h / 24  # per hour

    is_increasing = throttle_1h > avg_6h > avg_24h

    return {
        "throttle_1h": throttle_1h,
        "throttle_6h": throttle_6h,
        "throttle_24h": throttle_24h,
        "avg_per_hour_6h": round(avg_6h, 2),
        "avg_per_hour_24h": round(avg_24h, 2),
        "is_increasing": is_increasing,
        "is_frequent": throttle_1h >= THROTTLE_FREQUENCY_THRESHOLD,
    }


async def get_staleness_data(
    tenant_id: str,
    connector_id: str
) -> dict[str, Any]:
    """Get last success age data."""
    now = datetime.now(UTC)

    # Get last successful push
    last_success = await db.cm_rate_push_metrics.find_one(
        {
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "success": True,
        },
        {"_id": 0, "recorded_at": 1},
        sort=[("recorded_at", -1)],
    )

    if not last_success:
        return {
            "last_success_at": None,
            "age_minutes": None,
            "is_stale": True,
            "staleness_level": "critical",
        }

    last_ts_str = last_success.get("recorded_at")
    try:
        last_ts = datetime.fromisoformat(last_ts_str.replace("Z", "+00:00"))
        age_minutes = (now - last_ts).total_seconds() / 60
    except Exception:
        age_minutes = 999

    staleness_level = "normal"
    if age_minutes >= STALENESS_CRITICAL_MINUTES:
        staleness_level = "critical"
    elif age_minutes >= STALENESS_WARNING_MINUTES:
        staleness_level = "warning"

    return {
        "last_success_at": last_ts_str,
        "age_minutes": round(age_minutes, 1),
        "is_stale": age_minutes >= STALENESS_WARNING_MINUTES,
        "staleness_level": staleness_level,
    }


async def get_health_score_trend(
    tenant_id: str,
    connector_id: str,
    provider: str,
) -> dict[str, Any]:
    """Calculate health score trend by comparing current vs historical."""
    # Get current metrics
    now = datetime.now(UTC)
    since_1h = (now - timedelta(hours=1)).isoformat()
    since_6h = (now - timedelta(hours=6)).isoformat()

    async def calc_health(since: str) -> int:
        """Calculate health score for a time window."""
        from core.tenant_db import get_system_db
        sysdb = get_system_db()

        score = 100

        # Failure rate impact
        total = await db.cm_rate_push_metrics.count_documents({
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "recorded_at": {"$gte": since},
        })
        failed = await db.cm_rate_push_metrics.count_documents({
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "success": False,
            "recorded_at": {"$gte": since},
        })
        failure_rate = failed / max(total, 1) * 100

        if failure_rate > 50:
            score -= 40
        elif failure_rate > 20:
            score -= 20
        elif failure_rate > 5:
            score -= 10

        # DLQ impact
        dlq_count = await sysdb.webhook_dlq.count_documents({
            "tenant_id": tenant_id,
            "status": "pending",
        })
        if dlq_count > 10:
            score -= 30
        elif dlq_count > 5:
            score -= 20
        elif dlq_count > 0:
            score -= 10

        # Retry backlog impact
        backlog = await sysdb.webhook_deliveries.count_documents({
            "tenant_id": tenant_id,
            "status": "retrying",
        })
        if backlog > 20:
            score -= 15
        elif backlog > 5:
            score -= 5

        return max(0, score)

    current_score = await calc_health(since_1h)
    historical_score = await calc_health(since_6h)

    score_delta = current_score - historical_score
    trend_direction = "stable"
    if score_delta <= -HEALTH_SCORE_DROP_THRESHOLD:
        trend_direction = "dropping"
    elif score_delta >= HEALTH_SCORE_DROP_THRESHOLD:
        trend_direction = "improving"
    elif score_delta < 0:
        trend_direction = "slight_drop"
    elif score_delta > 0:
        trend_direction = "slight_improvement"

    return {
        "current_score": current_score,
        "historical_score": historical_score,
        "score_delta": score_delta,
        "trend_direction": trend_direction,
        "is_dropping": score_delta <= -HEALTH_SCORE_DROP_THRESHOLD,
        "is_improving": score_delta >= HEALTH_SCORE_DROP_THRESHOLD,
    }


# ══════════════════════════════════════════════════════════════════════
# Warning Generators
# ══════════════════════════════════════════════════════════════════════

async def check_failure_rate_warning(
    tenant_id: str,
    connector_id: str,
    provider: str,
) -> EarlyWarning | None:
    """Check for rising failure rate trend."""
    trend = await get_failure_rate_trend(tenant_id, connector_id, provider)

    short_rate = trend["windows"]["short"]["rate"]
    delta = trend["short_vs_long_delta"]
    direction = trend["trend_direction"]

    # Skip if failure rate is low and stable
    if short_rate < FAILURE_RATE_WARNING_THRESHOLD and delta < FAILURE_RATE_TREND_THRESHOLD:
        return None

    # Calculate confidence
    confidence = CONFIDENCE_BASE
    if direction in ("rising", "rising_recent"):
        confidence += CONFIDENCE_TREND_BONUS
    if short_rate >= FAILURE_RATE_CRITICAL_THRESHOLD:
        confidence += CONFIDENCE_SEVERITY_BONUS
    if delta >= FAILURE_RATE_TREND_THRESHOLD * 2:
        confidence += CONFIDENCE_HISTORY_BONUS

    # Generate warning
    if direction in ("rising", "rising_recent") or short_rate >= FAILURE_RATE_WARNING_THRESHOLD:
        severity = "critical" if short_rate >= FAILURE_RATE_CRITICAL_THRESHOLD else "warning"

        return EarlyWarning(
            warning_type="predictive.warning.failure_rate_rising",
            provider=provider,
            connector_id=connector_id,
            confidence=confidence,
            reason=f"Failure rate son 30 dakikada %{short_rate} ({delta:+.1f}% artış). Trend: {direction}",
            recommended_action="Connector timeline'ı inceleyin, hata kaynaklarını belirleyin. Gerekirse connector'ı degrade edin.",
            impacted_scope=f"{provider} üzerinden yapılan tüm push işlemleri",
            trend_data=trend,
            severity=severity,
        )

    return None


async def check_dlq_warning(tenant_id: str) -> EarlyWarning | None:
    """Check for DLQ spike or growth."""
    trend = await get_dlq_trend(tenant_id)

    if not trend["is_spiking"] and not trend["is_growing"]:
        return None

    confidence = CONFIDENCE_BASE
    if trend["is_spiking"] and trend["is_growing"]:
        confidence += CONFIDENCE_SEVERITY_BONUS + CONFIDENCE_TREND_BONUS
    elif trend["is_spiking"]:
        confidence += CONFIDENCE_TREND_BONUS
    elif trend["is_growing"]:
        confidence += CONFIDENCE_SEVERITY_BONUS

    reason_parts = []
    if trend["is_spiking"]:
        reason_parts.append(f"Son 30 dakikada {trend['recent_additions']} yeni DLQ item eklendi")
    if trend["is_growing"]:
        reason_parts.append(f"Toplam {trend['pending_count']} pending DLQ item bekliyor")

    return EarlyWarning(
        warning_type="predictive.warning.dlq_spike",
        provider="system",
        connector_id="",
        confidence=confidence,
        reason=". ".join(reason_parts),
        recommended_action="DLQ öğelerini inceleyin ve manuel retry uygulayın. Webhook endpoint'lerinin durumunu kontrol edin.",
        impacted_scope="Webhook teslimatları",
        trend_data=trend,
        severity="critical" if trend["pending_count"] >= DLQ_GROWTH_THRESHOLD * 2 else "warning",
    )


async def check_backlog_warning(tenant_id: str) -> EarlyWarning | None:
    """Check for growing retry backlog."""
    trend = await get_backlog_trend(tenant_id)

    if not trend["is_growing"]:
        return None

    confidence = CONFIDENCE_BASE
    if trend["current_backlog"] >= BACKLOG_WARNING_THRESHOLD * 2:
        confidence += CONFIDENCE_SEVERITY_BONUS
    if trend["recent_additions"] >= BACKLOG_GROWTH_RATE_THRESHOLD:
        confidence += CONFIDENCE_TREND_BONUS

    return EarlyWarning(
        warning_type="predictive.warning.backlog_growth",
        provider="system",
        connector_id="",
        confidence=confidence,
        reason=f"Retry backlog {trend['current_backlog']} item'a ulaştı. Son 30 dakikada {trend['recent_additions']} yeni eklendi.",
        recommended_action="Backlog büyümesinin nedenini araştırın. Webhook endpoint'leri yavaş yanıt veriyor olabilir.",
        impacted_scope="Webhook retry işlemleri",
        trend_data=trend,
        severity="warning",
    )


async def check_throttle_warning(
    tenant_id: str,
    provider: str,
) -> EarlyWarning | None:
    """Check for increasing throttle frequency."""
    trend = await get_throttle_trend(tenant_id, provider)

    if not trend["is_frequent"] and not trend["is_increasing"]:
        return None

    confidence = CONFIDENCE_BASE
    if trend["is_frequent"]:
        confidence += CONFIDENCE_SEVERITY_BONUS
    if trend["is_increasing"]:
        confidence += CONFIDENCE_TREND_BONUS

    return EarlyWarning(
        warning_type="predictive.warning.throttle_risk",
        provider=provider,
        connector_id="",
        confidence=confidence,
        reason=f"Son 1 saatte {trend['throttle_1h']} throttle olayı. Ortalama: 6s={trend['avg_per_hour_6h']}/sa, 24s={trend['avg_per_hour_24h']}/sa",
        recommended_action="Push frekansını düşürün veya rate limit ayarlarını gözden geçirin. Gerekirse controlled queueing'i aktifleştirin.",
        impacted_scope=f"{provider} API limitleri",
        trend_data=trend,
        severity="warning",
    )


async def check_staleness_warning(
    tenant_id: str,
    connector_id: str,
    provider: str,
) -> EarlyWarning | None:
    """Check for stale connector (no recent success)."""
    data = await get_staleness_data(tenant_id, connector_id)

    if not data["is_stale"]:
        return None

    confidence = CONFIDENCE_BASE
    if data["staleness_level"] == "critical":
        confidence += CONFIDENCE_SEVERITY_BONUS + CONFIDENCE_TREND_BONUS
    elif data["staleness_level"] == "warning":
        confidence += CONFIDENCE_TREND_BONUS

    age_text = f"{data['age_minutes']:.0f} dakika" if data["age_minutes"] else "hiç"

    return EarlyWarning(
        warning_type="predictive.warning.staleness_risk",
        provider=provider,
        connector_id=connector_id,
        confidence=confidence,
        reason=f"Son başarılı işlem {age_text} önce. Connector sessiz kalmış olabilir.",
        recommended_action="Connector'ın aktif olup olmadığını kontrol edin. Test push göndererek bağlantıyı doğrulayın.",
        impacted_scope=f"{provider} connector senkronizasyonu",
        trend_data=data,
        severity="critical" if data["staleness_level"] == "critical" else "warning",
    )


async def check_health_score_warning(
    tenant_id: str,
    connector_id: str,
    provider: str,
) -> EarlyWarning | None:
    """Check for dropping health score trend."""
    trend = await get_health_score_trend(tenant_id, connector_id, provider)

    # Generate warning for significant drops or low scores
    if not trend["is_dropping"] and trend["current_score"] >= HEALTH_SCORE_WARNING_THRESHOLD:
        return None

    confidence = CONFIDENCE_BASE
    if trend["is_dropping"]:
        confidence += CONFIDENCE_TREND_BONUS
    if trend["current_score"] <= HEALTH_SCORE_CRITICAL_THRESHOLD:
        confidence += CONFIDENCE_SEVERITY_BONUS
    if abs(trend["score_delta"]) >= HEALTH_SCORE_DROP_THRESHOLD * 2:
        confidence += CONFIDENCE_HISTORY_BONUS

    severity = "critical" if trend["current_score"] <= HEALTH_SCORE_CRITICAL_THRESHOLD else "warning"

    return EarlyWarning(
        warning_type="predictive.warning.degradation_likely",
        provider=provider,
        connector_id=connector_id,
        confidence=confidence,
        reason=f"Health score {trend['current_score']} (6s öncesine göre {trend['score_delta']:+d}). Trend: {trend['trend_direction']}",
        recommended_action="Connector'ın genel durumunu inceleyin. Failure rate, DLQ ve backlog'u kontrol edin. Proaktif müdahale gerekebilir.",
        impacted_scope=f"{provider} connector operasyonları",
        trend_data=trend,
        severity=severity,
    )


async def check_recovery_signal(
    tenant_id: str,
    connector_id: str,
    provider: str,
) -> EarlyWarning | None:
    """Check for recovery signals (improving metrics)."""
    health_trend = await get_health_score_trend(tenant_id, connector_id, provider)
    failure_trend = await get_failure_rate_trend(tenant_id, connector_id, provider)

    # Check if things are improving
    is_health_improving = health_trend["is_improving"]
    is_failure_falling = failure_trend["trend_direction"] in ("falling", "falling_recent")

    if not is_health_improving and not is_failure_falling:
        return None

    # Only emit if score was previously low
    if health_trend["historical_score"] >= HEALTH_SCORE_WARNING_THRESHOLD:
        return None

    confidence = CONFIDENCE_BASE
    if is_health_improving and is_failure_falling:
        confidence += CONFIDENCE_TREND_BONUS + CONFIDENCE_SEVERITY_BONUS
    elif is_health_improving:
        confidence += CONFIDENCE_TREND_BONUS

    return EarlyWarning(
        warning_type="predictive.warning.recovery_expected",
        provider=provider,
        connector_id=connector_id,
        confidence=confidence,
        reason=f"Metrikler iyileşiyor. Health: {health_trend['historical_score']} → {health_trend['current_score']}. Failure trend: {failure_trend['trend_direction']}",
        recommended_action="Connector'ın tam recovery yapmasını bekleyin. Degraded durumdaysa normal'e geçirmeyi değerlendirin.",
        impacted_scope=f"{provider} connector",
        trend_data={
            "health": health_trend,
            "failure": failure_trend,
        },
        severity="info",
    )


# ══════════════════════════════════════════════════════════════════════
# Main Analysis Engine
# ══════════════════════════════════════════════════════════════════════

async def analyze_connector_warnings(
    tenant_id: str,
    connector_id: str,
    provider: str,
) -> list[EarlyWarning]:
    """Analyze all warning types for a specific connector."""
    warnings = []

    # Run all checks in parallel
    results = await asyncio.gather(
        check_failure_rate_warning(tenant_id, connector_id, provider),
        check_staleness_warning(tenant_id, connector_id, provider),
        check_health_score_warning(tenant_id, connector_id, provider),
        check_throttle_warning(tenant_id, provider),
        check_recovery_signal(tenant_id, connector_id, provider),
        return_exceptions=True,
    )

    for result in results:
        if isinstance(result, EarlyWarning):
            warnings.append(result)
        elif isinstance(result, Exception):
            logger.warning("Warning check failed: %s", result)

    return warnings


async def analyze_system_warnings(tenant_id: str) -> list[EarlyWarning]:
    """Analyze system-wide warnings (DLQ, backlog)."""
    warnings = []

    results = await asyncio.gather(
        check_dlq_warning(tenant_id),
        check_backlog_warning(tenant_id),
        return_exceptions=True,
    )

    for result in results:
        if isinstance(result, EarlyWarning):
            warnings.append(result)
        elif isinstance(result, Exception):
            logger.warning("System warning check failed: %s", result)

    return warnings


async def generate_all_warnings(tenant_id: str) -> list[dict[str, Any]]:
    """Generate all early warnings for a tenant."""
    all_warnings = []

    # System-wide warnings
    system_warnings = await analyze_system_warnings(tenant_id)
    all_warnings.extend(system_warnings)

    # Per-connector warnings
    connectors = await db.cm_connectors.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "provider": 1, "status": 1}
    ).to_list(50)

    connector_tasks = [
        analyze_connector_warnings(tenant_id, conn["id"], conn.get("provider", ""))
        for conn in connectors
    ]

    if connector_tasks:
        connector_results = await asyncio.gather(*connector_tasks, return_exceptions=True)
        for result in connector_results:
            if isinstance(result, list):
                all_warnings.extend(result)

    # Sort by confidence (highest first)
    all_warnings.sort(key=lambda w: w.confidence, reverse=True)

    # Convert to dict
    return [w.to_dict() for w in all_warnings]


async def emit_warning_events(tenant_id: str, warnings: list[dict[str, Any]]) -> int:
    """Emit ops events for generated warnings. Returns count of emitted events."""
    emitted = 0

    for warning in warnings:
        # Skip info-level recovery signals from event emission (too noisy)
        if warning["severity"] == "info":
            continue

        # Check if we recently emitted the same warning (dedup within 30 min)
        recent_same = await db.ops_events.find_one({
            "tenant_id": tenant_id,
            "event_type": warning["warning_type"],
            "connector_id": warning.get("connector_id", ""),
            "created_at": {"$gte": (datetime.now(UTC) - timedelta(minutes=30)).isoformat()},
        })

        if recent_same:
            continue  # Already emitted recently

        severity = SEVERITY_WARNING if warning["severity"] == "warning" else SEVERITY_WARNING
        if warning["severity"] == "critical":
            from routers.ops_event_emitter import SEVERITY_CRITICAL
            severity = SEVERITY_CRITICAL

        await emit_ops_event(
            warning["warning_type"],
            tenant_id,
            channel=warning["provider"],
            connector_id=warning.get("connector_id", ""),
            severity=severity,
            title=f"Erken Uyarı: {warning['reason'][:100]}",
            details={
                "confidence": warning["confidence"],
                "reason": warning["reason"],
                "recommended_action": warning["recommended_action"],
                "impacted_scope": warning["impacted_scope"],
                "trend_data": warning.get("trend_data", {}),
            },
            affected_entity_type="connector" if warning.get("connector_id") else "system",
            affected_entity_id=warning.get("connector_id", "system"),
        )
        emitted += 1

    return emitted


# ══════════════════════════════════════════════════════════════════════
# Background Engine (Optional)
# ══════════════════════════════════════════════════════════════════════

class EarlyWarningEngine:
    """Background engine for periodic warning generation."""

    def __init__(self):
        self._running = False
        self._task = None
        self._check_interval = 300  # 5 minutes

    async def start(self):
        """Start the background warning checker."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("[EARLY-WARNING] Engine started (interval=%ds)", self._check_interval)

    async def stop(self):
        """Stop the background checker."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[EARLY-WARNING] Engine stopped")

    async def _run_loop(self):
        """Background loop."""
        while self._running:
            try:
                await self._check_all_tenants()
            except Exception as exc:
                logger.error("[EARLY-WARNING] Check failed: %s", exc)
            await asyncio.sleep(self._check_interval)

    async def _check_all_tenants(self):
        """Check warnings for all tenants."""
        tenants = await db.tenants.find({}, {"_id": 0, "id": 1}).to_list(100)

        for tenant in tenants:
            tenant_id = tenant.get("id", "")
            if not tenant_id:
                continue

            try:
                warnings = await generate_all_warnings(tenant_id)
                if warnings:
                    emitted = await emit_warning_events(tenant_id, warnings)
                    if emitted > 0:
                        logger.info(
                            "[EARLY-WARNING] tenant=%s warnings=%d emitted=%d",
                            tenant_id, len(warnings), emitted
                        )
            except Exception as exc:
                logger.warning("[EARLY-WARNING] tenant=%s error: %s", tenant_id, exc)


# Singleton
_engine: EarlyWarningEngine | None = None


def get_early_warning_engine() -> EarlyWarningEngine:
    """Get or create the early warning engine singleton."""
    global _engine
    if _engine is None:
        _engine = EarlyWarningEngine()
    return _engine
