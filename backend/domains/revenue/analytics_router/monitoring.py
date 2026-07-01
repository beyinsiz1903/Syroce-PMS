"""
monitoring

Auto-split sub-router (shared imports/classes inlined).
"""

"""
Domain Router: Analytics

Extracted from legacy_routes.py — GM Dashboard, pickup analysis, anomaly detection, revenue analytics.
"""
import uuid
from datetime import UTC, datetime

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
async def get_api_metrics(hours: int = 24, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get API performance metrics"""
    current_user = await get_current_user(credentials)

    # Only IT staff and admins
    if not _is_super_admin(current_user) and current_user.role not in ["admin", "it_manager", "super_admin"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Fail-closed: gerçek APM/metrics toplama (Prometheus vb.) yapılandırılmamış.
    # Sahte/rastgele metrik üretilmez.
    return {
        "metrics": [],
        "summary": {},
        "data_available": False,
        "message": "API performans metrikleri için gerçek izleme (APM) yapılandırılmamış. Veri yok.",
    }


# ── GET /monitoring/system-health ──
@router.get("/monitoring/system-health")
async def get_system_health_detailed(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get detailed system health metrics (cached for 5s)."""
    current_user = await get_current_user(credentials)

    # Only IT staff and admins
    if not _is_super_admin(current_user) and current_user.role not in ["admin", "it_manager", "super_admin"]:
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
        disk = psutil.disk_usage("/")

        system_info = {
            "cpu": {"usage_percent": cpu_percent, "cores": psutil.cpu_count(), "status": "healthy" if cpu_percent < 80 else "warning"},
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "percent": memory.percent,
                "status": "healthy" if memory.percent < 80 else "warning",
            },
            "disk": {"total_gb": round(disk.total / (1024**3), 2), "used_gb": round(disk.used / (1024**3), 2), "percent": disk.percent, "status": "healthy" if disk.percent < 85 else "warning"},
            "platform": {"system": platform.system(), "python_version": platform.python_version()},
        }
    except Exception as e:
        system_info = {"error": str(e), "message": "Unable to collect system metrics"}

    # Veritabanı bağlantısı — gerçek ping süresi ölçülür.
    try:
        _t0 = time.perf_counter()
        await db.command("ping")
        db_response_time = round((time.perf_counter() - _t0) * 1000, 1)
        db_status = "operational"
    except Exception:
        db_status = "error"
        db_response_time = None

    # Servis durumları: yalnızca veritabanı gerçek ölçülür. Diğer servisler için
    # gerçek uptime/yanıt-süresi izlemesi yapılandırılmadığından uydurma değer
    # döndürülmez (fail-closed).
    services = {
        "database": {"status": db_status, "response_time_ms": db_response_time},
    }

    # Sağlık skoru: gerçek sistem (cpu/mem/disk) + db sinyallerinden hesaplanır.
    signals = []
    if isinstance(system_info, dict) and "cpu" in system_info:
        signals.append(system_info["cpu"]["status"] == "healthy")
        signals.append(system_info["memory"]["status"] == "healthy")
        signals.append(system_info["disk"]["status"] == "healthy")
    signals.append(db_status == "operational")
    health_score = round((sum(1 for s in signals if s) / len(signals)) * 100, 1) if signals else 0

    payload = {
        "system": system_info,
        "services": services,
        "services_note": "Servis-bazlı uptime/yanıt-süresi izlemesi yapılandırılmamış; yalnızca veritabanı gerçek ölçülür.",
        "health_score": health_score,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    _SYSTEM_HEALTH_CACHE["ts"] = now
    _SYSTEM_HEALTH_CACHE["payload"] = payload
    return payload


# ── GET /monitoring/alert-thresholds ──
@router.get("/monitoring/alert-thresholds")
async def get_alert_thresholds(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get configured alert thresholds.

    warning/critical değerleri yapılandırmadır. 'current' değerleri yalnızca
    gerçek ölçüm kaynağı olan metrikler için doldurulur (cpu/mem/disk = psutil);
    APM gerektirenler (api_response_time/error_rate/database_connections) için
    gerçek kaynak yok → current=null (fail-closed, sahte değer yok).
    """
    await get_current_user(credentials)

    import psutil

    try:
        cpu_cur = psutil.cpu_percent(interval=None)
        mem_cur = psutil.virtual_memory().percent
        disk_cur = psutil.disk_usage("/").percent
    except Exception:
        cpu_cur = mem_cur = disk_cur = None

    thresholds = {
        "api_response_time": {"warning": 200, "critical": 500, "current": None},
        "error_rate": {"warning": 2.0, "critical": 5.0, "current": None},
        "cpu_usage": {"warning": 80, "critical": 95, "current": cpu_cur},
        "memory_usage": {"warning": 80, "critical": 95, "current": mem_cur},
        "disk_usage": {"warning": 85, "critical": 95, "current": disk_cur},
        "database_connections": {"warning": 80, "critical": 95, "current": None},
    }

    triggered = 0
    for key in ("cpu_usage", "memory_usage", "disk_usage"):
        cur = thresholds[key]["current"]
        if cur is not None and cur >= thresholds[key]["warning"]:
            triggered += 1

    return {
        "thresholds": thresholds,
        "alerts_triggered": triggered,
        "note": "API yanıt süresi, hata oranı ve DB bağlantı sayısı için gerçek ölçüm kaynağı yok (current=null).",
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
    if not _is_super_admin(current_user) and current_user.role not in ["admin", "it_manager", "super_admin"]:
        raise HTTPException(status_code=403, detail="Access denied")

    threshold = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "metric": threshold_data.get("metric"),
        "warning_value": threshold_data.get("warning_value"),
        "critical_value": threshold_data.get("critical_value"),
        "updated_by": current_user.name,
        "updated_at": datetime.now(UTC).isoformat(),
    }

    await db.alert_thresholds.insert_one(threshold)

    return {"message": "Threshold updated", "threshold_id": threshold["id"]}
