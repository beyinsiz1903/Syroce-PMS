"""
Router Registry — Central registration for all feature-based CM routers.
Replaces the monolithic router.py with modular, feature-scoped sub-routers.

All routes are prefixed with /api/channel-manager/v2/ to preserve backward compatibility.
"""
from fastapi import APIRouter

from .routers.connector_router import router as connector_router
from .routers.sync_router import router as sync_router
from .routers.reservation_router import router as reservation_router
from .routers.audit_router import router as audit_router
from .routers.metrics_router import router as metrics_router
from .routers.alert_router import router as alert_router
from .routers.scheduler_router import router as scheduler_router
from .routers.health_router import router as health_router
from .routers.delivery_router import router as delivery_router
from .routers.worker_router import router as worker_router
from .routers.validation_router import router as validation_router
from .routers.sandbox_router import router as sandbox_router

router = APIRouter(prefix="/api/channel-manager/v2", tags=["Channel Manager v2"])

router.include_router(connector_router)
router.include_router(sync_router)
router.include_router(reservation_router)
router.include_router(audit_router)
router.include_router(metrics_router)
router.include_router(alert_router)
router.include_router(scheduler_router)
router.include_router(health_router)
router.include_router(delivery_router)
router.include_router(worker_router)
router.include_router(validation_router)
router.include_router(sandbox_router)
