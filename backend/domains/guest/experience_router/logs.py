"""
logs

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Guest Experience

Guest CRM, upsell AI, messaging, feedback/reviews, guest mobile app.
"""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import (
    User,
)
from modules.pms_core.role_permission_service import require_op  # v98 DW

DEFAULT_UPSELL_PRICES = {
    "early_checkin": 25.00,
    "late_checkout": 35.00,
    "airport_transfer": 50.00,
}


async def _get_upsell_prices(tenant_id: str) -> dict:
    """Return per-tenant upsell prices, falling back to defaults for any missing key."""
    prices = dict(DEFAULT_UPSELL_PRICES)
    doc = await db.upsell_settings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if doc and isinstance(doc.get("prices"), dict):
        for k, v in doc["prices"].items():
            if k in prices:
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if fv >= 0:
                    prices[k] = fv
    return prices


# ============= PHASE H: GUEST CRM + UPSELL AI + MESSAGING =============









_MANUAL_UPSELL_TYPES = {
    "early_checkin", "late_checkout", "airport_transfer",
    "room_upgrade", "spa_package", "dining_credit", "champagne", "custom",
}














async def check_rate_limit(tenant_id: str, channel: str, limit_per_hour: int = 100) -> bool:
    """Check if rate limit is exceeded for messaging"""
    one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    count = await db.messages.count_documents({
        'tenant_id': tenant_id,
        'channel': channel,
        'sent_at': {'$gte': one_hour_ago}
    })

    return count < limit_per_hour








# Router will be included at the very end after ALL endpoints are defined

logger = logging.getLogger(__name__)



# ========================================

# 1. EXTERNAL REVIEW API INTEGRATION (Booking.com, Google, TripAdvisor)





# 2. IN-HOUSE SURVEY SYSTEM





# 3. DEPARTMENT-BASED SATISFACTION TRACKING




# ============= GUEST MOBILE APP ENDPOINTS =============

# rbac-allow: cache-rbac — GUEST portal — kendi rezervasyonları


































router = APIRouter(prefix="/api", tags=["guest-experience"])


# ── GET /logs/alerts-history ──
@router.get("/logs/alerts-history")
async def get_alert_history(
    start_date: str | None = None,
    end_date: str | None = None,
    alert_type: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    source_module: str | None = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_user)
):
    """
    Get alert center history
    - Filter by date, type, severity, status
    - Includes response time metrics
    """
    query = {'tenant_id': current_user.tenant_id}

    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter['$gte'] = start_date
        if end_date:
            date_filter['$lte'] = end_date
        if date_filter:
            query['timestamp'] = date_filter

    if alert_type:
        query['alert_type'] = alert_type
    if severity:
        query['severity'] = severity
    if status:
        query['status'] = status
    if source_module:
        query['source_module'] = source_module

    alerts = []
    async for alert in db.alert_history.find(query).sort('timestamp', -1).skip(skip).limit(limit):
        alerts.append(alert)

    total_count = await db.alert_history.count_documents(query)

    # Calculate stats
    stats = {
        'total_alerts': total_count,
        'unread': 0,
        'acknowledged': 0,
        'resolved': 0,
        'by_severity': {},
        'by_module': {}
    }

    async for alert in db.alert_history.find({'tenant_id': current_user.tenant_id}):
        status = alert.get('status', 'unread')
        if status == 'unread':
            stats['unread'] += 1
        elif status == 'acknowledged':
            stats['acknowledged'] += 1
        elif status == 'resolved':
            stats['resolved'] += 1

        # Count by severity
        severity = alert.get('severity', 'medium')
        stats['by_severity'][severity] = stats['by_severity'].get(severity, 0) + 1

        # Count by module
        module = alert.get('source_module', 'system')
        stats['by_module'][module] = stats['by_module'].get(module, 0) + 1

    return {
        'alerts': alerts,
        'total_count': total_count,
        'returned_count': len(alerts),
        'skip': skip,
        'limit': limit,
        'stats': stats
    }
# ── POST /logs/alerts/{alert_id}/acknowledge ──
@router.post("/logs/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    """Acknowledge an alert"""
    result = await db.alerts.update_one(
        {
            'id': alert_id,
            'tenant_id': current_user.tenant_id
        },
        {
            '$set': {
                'status': 'acknowledged',
                'acknowledged_at': datetime.now(UTC).isoformat(),
                'acknowledged_by': current_user.id
            }
        }
    )

    # Also update history
    await db.alert_history.update_one(
        {'id': alert_id},
        {
            '$set': {
                'status': 'acknowledged',
                'acknowledged_at': datetime.now(UTC).isoformat(),
                'acknowledged_by': current_user.id
            }
        }
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {
        'success': True,
        'message': 'Alert acknowledged'
    }
# ── POST /logs/alerts/{alert_id}/resolve ──
@router.post("/logs/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    resolution_notes: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    """Resolve an alert"""
    result = await db.alerts.update_one(
        {
            'id': alert_id,
            'tenant_id': current_user.tenant_id
        },
        {
            '$set': {
                'status': 'resolved',
                'resolved_at': datetime.now(UTC).isoformat(),
                'resolved_by': current_user.id,
                'resolution_notes': resolution_notes
            }
        }
    )

    # Also update history
    await db.alert_history.update_one(
        {'id': alert_id},
        {
            '$set': {
                'status': 'resolved',
                'resolved_at': datetime.now(UTC).isoformat(),
                'resolved_by': current_user.id,
                'resolution_notes': resolution_notes
            }
        }
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {
        'success': True,
        'message': 'Alert resolved'
    }
# ── GET /logs/dashboard ──
@router.get("/logs/dashboard")
async def get_logs_dashboard(
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive logging dashboard
    - Overview of all log types
    - Recent errors, alerts
    - System health indicators
    """
    # Get counts for each log type
    error_count = await db.error_logs.count_documents({'tenant_id': current_user.tenant_id})
    night_audit_count = await db.night_audit_logs.count_documents({'tenant_id': current_user.tenant_id})
    ota_sync_count = await db.ota_sync_logs.count_documents({'tenant_id': current_user.tenant_id})
    rms_publish_count = await db.rms_publish_logs.count_documents({'tenant_id': current_user.tenant_id})
    maintenance_prediction_count = await db.maintenance_prediction_logs.count_documents({'tenant_id': current_user.tenant_id})
    alert_count = await db.alert_history.count_documents({'tenant_id': current_user.tenant_id})

    # Recent critical errors (last 24 hours)
    from datetime import timedelta
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    recent_critical_errors = []
    async for error in db.error_logs.find({
        'tenant_id': current_user.tenant_id,
        'severity': 'critical',
        'timestamp': {'$gte': yesterday},
        'resolved': False
    }).sort('timestamp', -1).limit(5):
        recent_critical_errors.append(error)

    # Unread alerts
    unread_alerts = []
    async for alert in db.alerts.find({
        'tenant_id': current_user.tenant_id,
        'status': 'unread'
    }).sort('timestamp', -1).limit(10):
        unread_alerts.append(alert)

    # System health indicators
    health = {
        'overall_status': 'healthy',
        'indicators': []
    }

    # Check for critical errors
    if len(recent_critical_errors) > 0:
        health['overall_status'] = 'warning'
        health['indicators'].append({
            'type': 'critical_errors',
            'status': 'warning',
            'message': f'{len(recent_critical_errors)} critical errors in last 24 hours'
        })

    # Check for failed night audits
    failed_audits = await db.night_audit_logs.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'failed',
        'timestamp': {'$gte': yesterday}
    })

    if failed_audits > 0:
        health['overall_status'] = 'warning'
        health['indicators'].append({
            'type': 'night_audit',
            'status': 'warning',
            'message': f'{failed_audits} failed night audits in last 24 hours'
        })

    # Check for OTA sync failures
    failed_syncs = await db.ota_sync_logs.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'failed',
        'timestamp': {'$gte': yesterday}
    })

    if failed_syncs > 2:
        health['overall_status'] = 'warning'
        health['indicators'].append({
            'type': 'ota_sync',
            'status': 'warning',
            'message': f'{failed_syncs} failed OTA syncs in last 24 hours'
        })

    if len(health['indicators']) == 0:
        health['indicators'].append({
            'type': 'all_systems',
            'status': 'healthy',
            'message': 'All systems operating normally'
        })

    return {
        'summary': {
            'total_errors': error_count,
            'total_night_audits': night_audit_count,
            'total_ota_syncs': ota_sync_count,
            'total_rms_publishes': rms_publish_count,
            'total_maintenance_predictions': maintenance_prediction_count,
            'total_alerts': alert_count
        },
        'recent_critical_errors': recent_critical_errors,
        'unread_alerts': unread_alerts,
        'health': health
    }
