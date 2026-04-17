"""
Domain Router: RMS Revenue

Revenue management system, comp-set, yield management, Faz 2 sales/revenue features.
"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.cache import cached
from core.database import db
from core.security import get_current_user, security
from models.schemas import (
    AddCompetitorRequest,
    AutoPricingRequest,
    DemandForecastRequest,
    ScrapePricesRequest,
    User,
)

router = APIRouter(prefix="/api", tags=["rms-revenue"])

# ========================================


# ─── Endpoints (split: security_mobile) ───


@router.get("/security/user-activity-logs")
async def get_user_activity_logs(
    user_id: str | None = None,
    action_type: str | None = None,
    limit: int = 100,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get user activity logs for security monitoring"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if user_id:
        query['user_id'] = user_id
    if action_type:
        query['action'] = action_type

    logs = []
    async for log in db.audit_logs.find(query).sort('timestamp', -1).limit(limit):
        logs.append({
            'log_id': log.get('id'),
            'user_id': log.get('user_id'),
            'user_name': log.get('user_name'),
            'action': log.get('action'),
            'entity_type': log.get('entity_type'),
            'entity_id': log.get('entity_id'),
            'ip_address': log.get('ip_address'),
            'user_agent': log.get('user_agent'),
            'timestamp': log.get('timestamp').isoformat() if log.get('timestamp') else None,
            'changes': log.get('changes', {})
        })

    # Get activity summary
    activity_summary = {}
    for log in logs:
        action = log['action']
        activity_summary[action] = activity_summary.get(action, 0) + 1

    return {
        'logs': logs,
        'total_count': len(logs),
        'activity_summary': activity_summary
    }




@router.get("/security/api-rate-limits")
async def get_api_rate_limits(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get API rate limit monitoring data"""
    current_user = await get_current_user(credentials)

    # Track API calls per endpoint
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0)

    # Get API access logs
    endpoint_stats = {}

    async for log in db.api_access_logs.find({
        'tenant_id': current_user.tenant_id,
        'timestamp': {'$gte': today}
    }):
        endpoint = log.get('endpoint', 'unknown')

        if endpoint not in endpoint_stats:
            endpoint_stats[endpoint] = {
                'endpoint': endpoint,
                'total_requests': 0,
                'successful_requests': 0,
                'failed_requests': 0,
                'avg_response_time_ms': [],
                'rate_limit_hits': 0
            }

        endpoint_stats[endpoint]['total_requests'] += 1

        if log.get('status_code', 200) < 400:
            endpoint_stats[endpoint]['successful_requests'] += 1
        else:
            endpoint_stats[endpoint]['failed_requests'] += 1

        if log.get('status_code') == 429:  # Too Many Requests
            endpoint_stats[endpoint]['rate_limit_hits'] += 1

        if log.get('response_time_ms'):
            endpoint_stats[endpoint]['avg_response_time_ms'].append(log.get('response_time_ms'))

    # Calculate averages
    for endpoint in endpoint_stats.values():
        if endpoint['avg_response_time_ms']:
            endpoint['avg_response_time_ms'] = sum(endpoint['avg_response_time_ms']) / len(endpoint['avg_response_time_ms'])
        else:
            endpoint['avg_response_time_ms'] = 0

    return {
        'date': today.date().isoformat(),
        'endpoint_stats': list(endpoint_stats.values()),
        'total_api_calls': sum(s['total_requests'] for s in endpoint_stats.values()),
        'total_rate_limit_hits': sum(s['rate_limit_hits'] for s in endpoint_stats.values())
    }


# --------------------------------------------------------------------------
# Housekeeping - Inventory & Stock Management
# --------------------------------------------------------------------------



@router.get("/security/mobile/system-status")
async def get_system_status_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get system status for security/IT mobile dashboard"""
    current_user = await get_current_user(credentials)

    # Check various system components
    system_status = {
        'database': 'operational',
        'pms': 'operational',
        'pos': 'operational',
        'channel_manager': 'operational',
        'payment_gateway': 'operational'
    }

    # Check for recent errors in logs
    recent_errors = []
    last_hour = datetime.now(UTC) - timedelta(hours=1)

    async for log in db.system_logs.find({
        'tenant_id': current_user.tenant_id,
        'log_level': 'error',
        'created_at': {'$gte': last_hour}
    }).limit(10):
        recent_errors.append({
            'component': log.get('component', 'unknown'),
            'message': log.get('message', ''),
            'timestamp': log.get('created_at').isoformat()
        })

        # Update system status if errors found
        component = log.get('component', 'unknown')
        if component in system_status:
            system_status[component] = 'degraded'

    # Overall health score
    operational_count = sum(1 for status in system_status.values() if status == 'operational')
    health_score = (operational_count / len(system_status)) * 100

    return {
        'overall_status': 'healthy' if health_score >= 80 else 'degraded' if health_score >= 50 else 'critical',
        'health_score': health_score,
        'components': system_status,
        'recent_errors': recent_errors,
        'last_check': datetime.now(UTC).isoformat()
    }




@router.get("/security/mobile/connection-status")
async def get_connection_status_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get POS and Channel Manager connection status"""
    current_user = await get_current_user(credentials)

    connections = {}

    # Check POS connection (last successful transaction)
    last_pos_transaction = await db.pos_transactions.find_one(
        {'tenant_id': current_user.tenant_id},
        sort=[('created_at', -1)]
    )

    if last_pos_transaction:
        last_activity = last_pos_transaction.get('created_at')
        minutes_ago = (datetime.now(UTC) - last_activity).total_seconds() / 60

        connections['pos'] = {
            'status': 'connected' if minutes_ago < 60 else 'idle' if minutes_ago < 240 else 'disconnected',
            'last_activity': last_activity.isoformat(),
            'minutes_since_activity': int(minutes_ago)
        }
    else:
        connections['pos'] = {
            'status': 'no_data',
            'last_activity': None,
            'minutes_since_activity': None
        }

    # Check Channel Manager sync (last successful sync)
    last_cm_sync = await db.channel_manager_syncs.find_one(
        {'tenant_id': current_user.tenant_id},
        sort=[('sync_timestamp', -1)]
    )

    if last_cm_sync:
        last_sync = last_cm_sync.get('sync_timestamp')
        minutes_ago = (datetime.now(UTC) - last_sync).total_seconds() / 60

        connections['channel_manager'] = {
            'status': 'connected' if minutes_ago < 15 else 'idle' if minutes_ago < 60 else 'disconnected',
            'last_sync': last_sync.isoformat(),
            'minutes_since_sync': int(minutes_ago),
            'sync_status': last_cm_sync.get('status', 'unknown')
        }
    else:
        connections['channel_manager'] = {
            'status': 'no_data',
            'last_sync': None,
            'minutes_since_sync': None
        }

    return {
        'connections': connections,
        'timestamp': datetime.now(UTC).isoformat()
    }




@router.get("/security/mobile/security-alerts")
async def get_security_alerts_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get security alerts for security/IT mobile dashboard"""
    current_user = await get_current_user(credentials)

    alerts = []

    # Check for unauthorized access attempts
    failed_logins = await db.auth_logs.count_documents({
        'tenant_id': current_user.tenant_id,
        'action': 'login_failed',
        'timestamp': {'$gte': datetime.now(UTC) - timedelta(hours=1)}
    })

    if failed_logins > 5:
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'unauthorized_access',
            'title': 'Unauthorized Access Attempt',
            'message': f"{failed_logins} failed login attempts in the last hour",
            'severity': 'high',
            'timestamp': datetime.now(UTC).isoformat()
        })

    # Check for unusual data access patterns
    async for log in db.audit_logs.find({
        'tenant_id': current_user.tenant_id,
        'action': {'$in': ['DATA_EXPORT', 'BULK_DELETE']},
        'timestamp': {'$gte': datetime.now(UTC) - timedelta(hours=24)}
    }):
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'data_access',
            'title': 'Unusual Data Access',
            'message': f"{log.get('action')} by {log.get('user_name')}",
            'severity': 'medium',
            'timestamp': log.get('timestamp').isoformat()
        })

    # GDPR compliance alerts (guest data older than retention period)
    retention_period = 365 * 2  # 2 years
    old_data_cutoff = datetime.now(UTC) - timedelta(days=retention_period)

    old_guest_count = await db.guests.count_documents({
        'tenant_id': current_user.tenant_id,
        'last_stay_date': {'$lt': old_data_cutoff}
    })

    if old_guest_count > 0:
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'gdpr_compliance',
            'title': 'GDPR Warning',
            'message': f"{old_guest_count} guest(s) data exceeded retention period",
            'severity': 'low',
            'timestamp': datetime.now(UTC).isoformat()
        })

    return {
        'alerts': alerts,
        'alert_count': len(alerts)
    }


