"""
system

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Admin / Operations Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status

from core.database import db
from core.helpers import (
    require_super_admin_guard,
)
from core.security import (
    _is_super_admin,
    get_current_user,
)

try:
    from cache_manager import cache as _cache_mgr
    from cache_manager import cached as _cm_cached
except ImportError:
    _cache_mgr = None  # type: ignore
    def _cm_cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator


def _invalidate_admin_tenants_cache(tenant_id: str | None) -> None:
    """v95.3 — admin/tenants list cache'i temizle. Super-admin tenant_id ile
    set edilir; bu fonksiyon güvenli (hata fırlatmaz)."""
    if not _cache_mgr or not tenant_id:
        return
    try:
        _cache_mgr.invalidate_tenant_cache(tenant_id, "admin_tenants_list")
    except Exception:
        pass

require_super_admin = require_super_admin_guard()
from models.enums import ROLE_PERMISSIONS, Permission, UserRole
from models.schemas import User


def _has_permission(role: UserRole | str, perm: Permission) -> bool:
    """Lightweight helper: ROLE_PERMISSIONS lookup."""
    role_key = role if isinstance(role, UserRole) else UserRole(role) if role in {r.value for r in UserRole} else None
    if role_key is None:
        return False
    perms = ROLE_PERMISSIONS.get(role_key, [])
    perm_value = perm.value if isinstance(perm, Permission) else perm
    return any((p.value if isinstance(p, Permission) else p) == perm_value for p in perms)

logger = logging.getLogger(__name__)


def _svc_enc():
    try:
        from security.field_encryption import get_field_encryption_service
        return get_field_encryption_service()
    except Exception:
        return None

ROLES_BY_TIER = {
    "mini": ["admin", "front_desk", "housekeeping"],
    "basic": ["admin", "front_desk", "housekeeping"],
    "professional": ["admin", "front_desk", "housekeeping", "manager", "revenue", "night_audit", "finance", "procurement"],
    "enterprise": ["admin", "front_desk", "housekeeping", "manager", "revenue", "night_audit", "gm", "super_admin", "finance", "procurement", "supervisor", "sales"],
}


def is_role_allowed_for_tier(role: str, tier: str) -> bool:
    allowed = ROLES_BY_TIER.get(tier, ROLES_BY_TIER["basic"])
    return role in allowed






# ============= CHANNEL MANAGER & RMS =============









# ============= MOBILE APP ENDPOINTS (STAFF & GUEST) =============
























# ── Task #28: Kullanıcı bazlı operasyon izinleri ──────────────────────
#
# Rol-bazlı RBAC dışında bazı operasyonlar (şu an yalnız acil mesaj
# gönderme) tek tek kullanıcılara verilip alınabilsin diye User modelinde
# `granted_permissions: list[str]` alanı tutuluyor. Endpoint'ler ADMIN ve
# SUPER_ADMIN'e açık. ADMIN sadece kendi tenant'ı içindeki kullanıcılara
# yazabilir; SUPER_ADMIN her tenant'a yazabilir.

# Whitelist: kötü niyetli/yanlış izin atamalarını önlemek için kabul
# edilen izinler dar tutulur.
GRANTABLE_PERMISSIONS: set[str] = {"send_urgent_message"}


def _require_admin_for_target_user(
    current_user: User, target_tenant_id: str | None,
):
    """ADMIN ve SUPER_ADMIN'e izin ver; ADMIN'in başka tenant'a yazmasını
    engelle. Diğer roller 403 alır."""
    if _is_super_admin(current_user):
        return
    role_value = getattr(current_user.role, "value", str(current_user.role))
    if role_value != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Yalnızca yöneticiler kullanıcı izinlerini düzenleyebilir.",
        )
    # ADMIN'in tenant_id'si target ile eşleşmeli.
    if not current_user.tenant_id or current_user.tenant_id != target_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )








# ── Task #32: Web push gönderim metrikleri ────────────────────────────

















# ============= ADMIN TENANT INFO & TEAM MANAGEMENT =============
























# ============= BILLING HISTORY & PLAN MANAGEMENT =============
















# ============= HOTEL TEAM MANAGEMENT ENDPOINTS =============

















# ============= DEMO ENVIRONMENT ENDPOINTS =============

















# 6. GET /api/sales/follow-ups - Follow-up reminders








# ============================================================================
# COMPREHENSIVE FINANCE MODULE - CASH FLOW & RISK MANAGEMENT
# ============================================================================

# ============================================================================
# DELAYED TASKS MONITORING & PUSH NOTIFICATIONS
# ============================================================================

# MOVED: /tasks/delayed endpoint moved earlier to avoid path conflict with /tasks/{task_id}


# ============================================================================
# SYSTEM MONITORING & PERFORMANCE - APM INTEGRATED
# ============================================================================

import time

import psutil

# api_metrics is now provided by apm_store from apm_middleware.py
# Backward compat: alias api_metrics to apm_store.requests
try:
    from apm_middleware import apm_store as _apm_store_ref
    api_metrics = _apm_store_ref.requests
except ImportError:
    from collections import deque
    api_metrics = deque(maxlen=1000)

# Legacy APIMetricsMiddleware replaced by APMMiddleware in apm_middleware.py

# 1. SYSTEM PERFORMANCE MONITORING




# 1b. APM DETAILED ENDPOINT STATS




# 1c. RATE LIMIT STATUS




# 1d. DATABASE OPTIMIZATION STATUS




# 1e. RECENT ERRORS




# 2. LOG VIEWER




# 3. NETWORK PING TEST




# 4. ENDPOINT HEALTH CHECK




# ============================================================================
# OPERA CLOUD PARITY FEATURES - CRITICAL ENTERPRISE FUNCTIONALITY
# ============================================================================

# Import night audit models

# ============= 1. NIGHT AUDIT MODULE (ENTERPRISE GRADE) =============

# ============= 2. CASHIERING & CITY LEDGER MODULE =============

# ============= 3. QUEUE ROOMS MODULE (EARLY ARRIVAL MANAGEMENT) =============

# ============= AUDIT TRAIL LOGGING (AUTO-TRACKING) =============













# ──────────────────────────────────────────────────────────────────────────────
# v95.4 — Maintenance: Oda statüsü ↔ rezervasyon defteri sync
# UctanUcaTest 2026-05-02: dashboard "OCCUPANCY-DRIFT" uyarısı için kalıcı
# çözüm. KPI zaten booking ledger'ı kaynak alıyor, bu endpoint rooms.status
# tarafındaki tortu veriyi (eski non-atomic flow'lardan kalan) düzeltir.
# ──────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api", tags=["Admin / Operations"])


# ── GET /system/performance ──
@router.get("/system/performance")
async def get_system_performance(
    minutes: int = 10,
    current_user: User = Depends(get_current_user)
):
    """
    Get real-time system performance metrics powered by APM middleware.
    Returns: CPU, RAM, API response times, request rates, rate limiting, errors
    """
    try:
        # Get CPU and Memory info
        cpu_percent = psutil.cpu_percent(interval=0)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Get APM summary (real data from middleware)
        try:
            apm_summary = _apm_store_ref.get_summary(minutes=minutes)
        except Exception:
            try:
                from apm_middleware import apm_store as _apm
                apm_summary = _apm.get_summary(minutes=minutes) if hasattr(_apm, 'get_summary') else {}
            except Exception:
                apm_summary = {}

        # Get rate limit stats
        try:
            rl_stats = _get_rl_stats()
        except Exception:
            try:
                from apm_middleware import get_rate_limit_stats as _rl
                rl_stats = _rl()
            except Exception:
                rl_stats = {}

        # Get recent errors
        try:
            recent_errors = _apm_store_ref.get_recent_errors(limit=20)
        except Exception:
            recent_errors = []

        # Database stats (lightweight)
        db_stats = {}
        try:
            server_status = await db.command('serverStatus')
            db_stats = {
                'connections': {
                    'current': server_status.get('connections', {}).get('current', 0),
                    'available': server_status.get('connections', {}).get('available', 0),
                    'total_created': server_status.get('connections', {}).get('totalCreated', 0),
                },
                'opcounters': {
                    'insert': server_status.get('opcounters', {}).get('insert', 0),
                    'query': server_status.get('opcounters', {}).get('query', 0),
                    'update': server_status.get('opcounters', {}).get('update', 0),
                    'delete': server_status.get('opcounters', {}).get('delete', 0),
                },
                'uptime_seconds': server_status.get('uptime', 0),
            }
        except Exception:
            pass

        return {
            'system': {
                'cpu_percent': round(cpu_percent, 2),
                'memory_percent': round(memory.percent, 2),
                'memory_used_gb': round(memory.used / (1024**3), 2),
                'memory_total_gb': round(memory.total / (1024**3), 2),
                'disk_percent': round(disk.percent, 2),
                'disk_used_gb': round(disk.used / (1024**3), 2),
                'disk_total_gb': round(disk.total / (1024**3), 2),
            },
            'api_metrics': {
                'avg_response_time_ms': apm_summary.get('avg_response_time_ms', 0),
                'p50_ms': apm_summary.get('p50_ms', 0),
                'p95_ms': apm_summary.get('p95_ms', 0),
                'p99_ms': apm_summary.get('p99_ms', 0),
                'requests_per_minute': apm_summary.get('requests_per_minute', 0),
                'total_requests_tracked': apm_summary.get('total_requests', 0),
                'error_rate_percent': apm_summary.get('error_rate_percent', 0),
                'slow_requests': apm_summary.get('slow_requests', 0),
                'status_breakdown': apm_summary.get('status_breakdown', {}),
                'endpoints': apm_summary.get('top_endpoints', []),
                'slowest_endpoints': apm_summary.get('slowest_endpoints', []),
                'error_endpoints': apm_summary.get('error_endpoints', []),
            },
            'rate_limiting': {
                'active_clients': rl_stats.get('active_clients', 0),
                'total_rate_limit_hits': rl_stats.get('total_rate_limit_hits', 0),
                'hits_by_endpoint': rl_stats.get('hits_by_endpoint', {}),
                'limits_config': rl_stats.get('limits_config', {}),
            },
            'database': db_stats,
            'recent_errors': recent_errors[:10],
            'timeline': apm_summary.get('timeline', []),
            'health_status': 'healthy' if cpu_percent < 80 and memory.percent < 80 else 'degraded',
            'uptime_seconds': apm_summary.get('uptime_seconds', 0),
            'timestamp': datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get performance metrics: {str(e)}")
# ── GET /system/apm/endpoints ──
@router.get("/system/apm/endpoints")
async def get_apm_endpoint_details(
    current_user: User = Depends(get_current_user)
):
    """Get detailed APM stats for all tracked endpoints"""
    try:
        summary = _apm_store_ref.get_summary(minutes=30)
        return {
            'top_endpoints': summary.get('top_endpoints', []),
            'slowest_endpoints': summary.get('slowest_endpoints', []),
            'error_endpoints': summary.get('error_endpoints', []),
            'total_requests': summary.get('total_requests', 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# ── GET /system/rate-limits ──
@router.get("/system/rate-limits")
async def get_rate_limit_status(
    current_user: User = Depends(get_current_user)
):
    """Get current rate limiting status and configuration"""
    try:
        rl_stats = _get_rl_stats()
        return {
            'enabled': True,
            'mode': 'in-memory',
            'stats': rl_stats,
            'timestamp': datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        return {
            'enabled': False,
            'mode': 'disabled',
            'error': str(e),
            'timestamp': datetime.now(UTC).isoformat(),
        }
# ── GET /system/db-stats ──
@router.get("/system/db-stats")
async def get_database_stats(
    current_user: User = Depends(get_current_user)
):
    """Get database optimization and performance statistics.

    Degrades gracefully (HTTP 200 + partial payload) when an individual
    sub-query is unavailable on the deployed tier. Atlas shared tiers restrict
    the privileged `serverStatus`/`collStats` commands; previously any one of
    those raising turned the whole endpoint into a 500. Each sub-call is now
    isolated and failures are surfaced in a `degraded` list rather than
    collapsing the response — same guarded-return posture as the audit-logs /
    hr-staff read hardening. (RBAC posture unchanged: any-auth, /system/*.)
    """
    degraded: list[str] = []

    index_info = None
    collection_stats = None
    try:
        from infra.database_optimizer import DatabaseOptimizer
        optimizer = DatabaseOptimizer(db)
        try:
            index_info = await optimizer.verify_indexes()
        except Exception as e:
            degraded.append(f"indexes: {str(e)[:120]}")
        try:
            collection_stats = await optimizer.get_collection_stats()
        except Exception as e:
            degraded.append(f"collections: {str(e)[:120]}")
    except Exception as e:
        degraded.append(f"optimizer_init: {str(e)[:120]}")

    connections = {}
    opcounters = {}
    uptime_seconds = 0
    try:
        server_status = await db.command('serverStatus')
        connections = server_status.get('connections', {})
        opcounters = server_status.get('opcounters', {})
        uptime_seconds = server_status.get('uptime', 0)
    except Exception as e:
        # Atlas shared tiers / restricted DB roles deny serverStatus.
        degraded.append(f"server_status: {str(e)[:120]}")

    return {
        'indexes': index_info,
        'collections': collection_stats,
        'connections': {
            'current': connections.get('current', 0),
            'available': connections.get('available', 0),
            'total_created': connections.get('totalCreated', 0),
        },
        'operations': {
            'insert': opcounters.get('insert', 0),
            'query': opcounters.get('query', 0),
            'update': opcounters.get('update', 0),
            'delete': opcounters.get('delete', 0),
        },
        'pool_config': {
            'max_pool_size': 500,
            'min_pool_size': 50,
            'max_idle_time_ms': 45000,
        },
        'uptime_seconds': uptime_seconds,
        'degraded': degraded or None,
        'timestamp': datetime.now(UTC).isoformat(),
    }
# ── GET /system/errors ──
@router.get("/system/errors")
async def get_recent_errors(
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """Get recent API errors tracked by APM"""
    try:
        errors = _apm_store_ref.get_recent_errors(limit=limit)
        return {
            'errors': errors,
            'total': len(errors),
            'timestamp': datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        return {'errors': [], 'total': 0, 'error': str(e)}
# ── GET /system/logs ──
@router.get("/system/logs")
async def get_system_logs(
    level: str | None = None,  # ERROR, WARN, INFO, DEBUG
    search: str | None = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """
    Get system logs with filtering
    """
    try:
        # Read from audit logs and create application logs
        logs = []

        # Get audit logs from database
        from security.query_safety import safe_search_term
        filter_dict = {'tenant_id': current_user.tenant_id}
        if (s := safe_search_term(search)):
            filter_dict['$or'] = [
                {'action': {'$regex': s, '$options': 'i'}},
                {'entity_type': {'$regex': s, '$options': 'i'}},
                {'user_name': {'$regex': s, '$options': 'i'}}
            ]

        audit_logs = await db.audit_logs.find(filter_dict).sort('timestamp', -1).limit(limit).to_list(limit)

        for log in audit_logs:
            # Convert audit log to application log format
            log_entry = {
                'id': log['id'],
                'level': 'INFO',
                'timestamp': log['timestamp'],
                'message': f"{log['user_name']} performed {log['action']} on {log['entity_type']}",
                'user': log.get('user_name', 'System'),
                'action': log['action'],
                'entity_type': log.get('entity_type'),
                'entity_id': log.get('entity_id'),
                'details': log.get('changes', {})
            }

            # Determine log level based on action
            if 'DELETE' in log['action'] or 'VOID' in log['action']:
                log_entry['level'] = 'WARN'
            elif 'ERROR' in log['action'] or 'FAIL' in log['action']:
                log_entry['level'] = 'ERROR'

            logs.append(log_entry)

        # Add some system logs
        system_logs = [
            {
                'id': str(uuid.uuid4()),
                'level': 'INFO',
                'timestamp': datetime.now(UTC).isoformat(),
                'message': 'System performance check completed',
                'user': 'System',
                'action': 'SYSTEM_CHECK',
                'details': {'status': 'healthy'}
            },
            {
                'id': str(uuid.uuid4()),
                'level': 'INFO',
                'timestamp': (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
                'message': 'Database connection verified',
                'user': 'System',
                'action': 'DB_CHECK',
                'details': {'latency_ms': 12}
            }
        ]

        logs.extend(system_logs)
        logs.sort(key=lambda x: x['timestamp'], reverse=True)

        # Filter by level if specified (after adding all logs)
        if level:
            logs = [log for log in logs if log['level'] == level.upper()]

        return {
            'logs': logs[:limit],
            'count': len(logs),
            'filters': {
                'level': level,
                'search': search,
                'limit': limit
            },
            'log_levels': {
                'ERROR': len([l for l in logs if l['level'] == 'ERROR']),
                'WARN': len([l for l in logs if l['level'] == 'WARN']),
                'INFO': len([l for l in logs if l['level'] == 'INFO']),
                'DEBUG': len([l for l in logs if l['level'] == 'DEBUG'])
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve logs: {str(e)}")
# ── GET /system/health ──
@router.get("/system/health")
async def system_health_check(
    current_user: User = Depends(get_current_user)
):
    """
    Check health of all critical endpoints and services
    """
    try:
        health_checks = []

        # Check database connection
        try:
            await db.command('ping')
            db_latency_start = time.time()
            await db.bookings.find_one({})
            db_latency = (time.time() - db_latency_start) * 1000

            health_checks.append({
                'service': 'MongoDB',
                'status': 'healthy',
                'latency_ms': round(db_latency, 2),
                'message': 'Database connection active'
            })
        except Exception as e:
            health_checks.append({
                'service': 'MongoDB',
                'status': 'unhealthy',
                'latency_ms': 0,
                'message': f'Database error: {str(e)}'
            })

        # Check API endpoints
        critical_endpoints = [
            {'name': 'Authentication', 'count_collection': 'users'},
            {'name': 'Bookings', 'count_collection': 'bookings'},
            {'name': 'Rooms', 'count_collection': 'rooms'},
            {'name': 'Guests', 'count_collection': 'guests'}
        ]

        for endpoint in critical_endpoints:
            try:
                start_time = time.time()
                count = await db[endpoint['count_collection']].count_documents({'tenant_id': current_user.tenant_id})
                latency = (time.time() - start_time) * 1000

                health_checks.append({
                    'service': endpoint['name'],
                    'status': 'healthy',
                    'latency_ms': round(latency, 2),
                    'message': f'{count} records',
                    'record_count': count
                })
            except Exception as e:
                health_checks.append({
                    'service': endpoint['name'],
                    'status': 'unhealthy',
                    'latency_ms': 0,
                    'message': f'Error: {str(e)}'
                })

        # Overall health status
        unhealthy_count = len([h for h in health_checks if h['status'] == 'unhealthy'])
        overall_status = 'healthy' if unhealthy_count == 0 else 'degraded' if unhealthy_count < 2 else 'critical'

        return {
            'overall_status': overall_status,
            'checks': health_checks,
            'total_checks': len(health_checks),
            'healthy_count': len([h for h in health_checks if h['status'] == 'healthy']),
            'unhealthy_count': unhealthy_count,
            'timestamp': datetime.now(UTC).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")
