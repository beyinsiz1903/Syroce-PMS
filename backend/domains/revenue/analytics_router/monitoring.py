"""
monitoring

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Analytics

Extracted from legacy_routes.py — GM Dashboard, pickup analysis, anomaly detection, revenue analytics.
"""
import random
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from core.database import db
from core.security import _is_super_admin, get_current_user, security
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.role_permission_service import require_role as _require_role

# v67 Bug DD: frontdesk/* endpoint'lerinde RBAC eksikti — HK kullanıcı guest PII (search-bookings),
# müsaitlik (available-rooms), oda atama (assign-room) erişebiliyordu. Front office personeline kısıtla.
_FD_READ = Depends(_require_role("super_admin", "admin", "supervisor", "front_desk"))
_FD_WRITE = Depends(_require_role("super_admin", "admin", "front_desk"))

try:
    from routers.pms_availability import check_room_availability
except Exception:  # pragma: no cover
    async def check_room_availability(*args, **kwargs):
        return {"available": False, "rooms": []}



# --------------------------------------------------------------------------
# GM Dashboard - Pickup Analysis & Anomaly Detection
# --------------------------------------------------------------------------







# rbac-allow: cache-rbac — FO booking search operasyonel

# rbac-allow: cache-rbac — FO available rooms operasyonel











































_SYSTEM_HEALTH_CACHE: dict = {"ts": 0.0, "payload": None}
_SYSTEM_HEALTH_TTL = 5.0  # seconds

router = APIRouter(prefix="/api", tags=["analytics"])


# ── GET /monitoring/api-metrics ──
@router.get("/monitoring/api-metrics")
async def get_api_metrics(
    hours: int = 24,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get API performance metrics"""
    current_user = await get_current_user(credentials)

    # Only IT staff and admins
    if not _is_super_admin(current_user) and current_user.role not in ['admin', 'it_manager', 'super_admin']:
        raise HTTPException(status_code=403, detail="Access denied")

    # Mock API metrics (in production, collect from actual monitoring)
    now = datetime.now(UTC)
    metrics = []

    for i in range(24):
        timestamp = now - timedelta(hours=23-i)
        metrics.append({
            'timestamp': timestamp.isoformat(),
            'avg_response_time': round(50 + (i % 5) * 10 + random.uniform(-10, 10), 2),
            'requests_per_minute': 120 + random.randint(-20, 20),
            'error_rate': round(random.uniform(0.5, 2.5), 2),
            'success_rate': round(100 - random.uniform(0.5, 2.5), 2)
        })

    return {
        'metrics': metrics,
        'summary': {
            'avg_response_time': round(sum(m['avg_response_time'] for m in metrics) / len(metrics), 2),
            'total_requests': sum(m['requests_per_minute'] for m in metrics) * 60,
            'avg_error_rate': round(sum(m['error_rate'] for m in metrics) / len(metrics), 2),
            'uptime_percentage': 99.8
        }
    }
# ── GET /monitoring/system-health ──
@router.get("/monitoring/system-health")
async def get_system_health_detailed(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get detailed system health metrics (cached for 5s)."""
    current_user = await get_current_user(credentials)

    # Only IT staff and admins
    if not _is_super_admin(current_user) and current_user.role not in ['admin', 'it_manager', 'super_admin']:
        raise HTTPException(status_code=403, detail="Access denied")

    import platform
    import time

    import psutil

    now = time.time()
    if _SYSTEM_HEALTH_CACHE["payload"] is not None and (now - _SYSTEM_HEALTH_CACHE["ts"]) < _SYSTEM_HEALTH_TTL:
        return _SYSTEM_HEALTH_CACHE["payload"]

    # Get system info — non-blocking cpu_percent (returns avg since last call)
    try:
        cpu_percent = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        system_info = {
            'cpu': {
                'usage_percent': cpu_percent,
                'cores': psutil.cpu_count(),
                'status': 'healthy' if cpu_percent < 80 else 'warning'
            },
            'memory': {
                'total_gb': round(memory.total / (1024**3), 2),
                'used_gb': round(memory.used / (1024**3), 2),
                'percent': memory.percent,
                'status': 'healthy' if memory.percent < 80 else 'warning'
            },
            'disk': {
                'total_gb': round(disk.total / (1024**3), 2),
                'used_gb': round(disk.used / (1024**3), 2),
                'percent': disk.percent,
                'status': 'healthy' if disk.percent < 85 else 'warning'
            },
            'platform': {
                'system': platform.system(),
                'python_version': platform.python_version()
            }
        }
    except Exception as e:
        system_info = {
            'error': str(e),
            'message': 'Unable to collect system metrics'
        }

    # Check database connection
    try:
        await db.command('ping')
        db_status = 'operational'
        db_response_time = 5  # Mock
    except Exception:
        db_status = 'error'
        db_response_time = 0

    # Service statuses
    services = {
        'pms': {'status': 'operational', 'response_time': 45, 'uptime': 99.9},
        'pos': {'status': 'operational', 'response_time': 38, 'uptime': 99.7},
        'channel_manager': {'status': 'operational', 'response_time': 120, 'uptime': 99.5},
        'database': {'status': db_status, 'response_time': db_response_time, 'uptime': 99.95},
        'api_gateway': {'status': 'operational', 'response_time': 15, 'uptime': 99.99}
    }

    # Calculate overall health score
    operational_count = sum(1 for s in services.values() if s['status'] == 'operational')
    health_score = (operational_count / len(services)) * 100

    payload = {
        'system': system_info,
        'services': services,
        'health_score': round(health_score, 1),
        'timestamp': datetime.now(UTC).isoformat()
    }
    _SYSTEM_HEALTH_CACHE["ts"] = now
    _SYSTEM_HEALTH_CACHE["payload"] = payload
    return payload
# ── GET /monitoring/alert-thresholds ──
@router.get("/monitoring/alert-thresholds")
async def get_alert_thresholds(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get configured alert thresholds"""
    await get_current_user(credentials)

    thresholds = {
        'api_response_time': {
            'warning': 200,  # ms
            'critical': 500,
            'current': 65
        },
        'error_rate': {
            'warning': 2.0,  # percent
            'critical': 5.0,
            'current': 1.2
        },
        'cpu_usage': {
            'warning': 80,  # percent
            'critical': 95,
            'current': 45
        },
        'memory_usage': {
            'warning': 80,
            'critical': 95,
            'current': 62
        },
        'disk_usage': {
            'warning': 85,
            'critical': 95,
            'current': 58
        },
        'database_connections': {
            'warning': 80,
            'critical': 95,
            'current': 35
        }
    }

    return {
        'thresholds': thresholds,
        'alerts_triggered': 0
    }
# ── POST /monitoring/set-threshold ──
@router.post("/monitoring/set-threshold")
async def set_alert_threshold(
    threshold_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_system_diagnostics")),  # v89 DW
):
    """Set or update an alert threshold"""
    current_user = await get_current_user(credentials)

    # Only IT staff and admins
    if not _is_super_admin(current_user) and current_user.role not in ['admin', 'it_manager', 'super_admin']:
        raise HTTPException(status_code=403, detail="Access denied")

    threshold = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'metric': threshold_data.get('metric'),
        'warning_value': threshold_data.get('warning_value'),
        'critical_value': threshold_data.get('critical_value'),
        'updated_by': current_user.name,
        'updated_at': datetime.now(UTC).isoformat()
    }

    await db.alert_thresholds.insert_one(threshold)

    return {
        'message': 'Threshold updated',
        'threshold_id': threshold['id']
    }
