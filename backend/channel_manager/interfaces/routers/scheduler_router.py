"""Scheduled import job management, safety-net sync, and environment config endpoints."""
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User

from ...application.scheduled_import_service import ScheduledImportService
from ...connectors.hotelrunner.environment_config import get_all_environments, get_environment_config

logger = logging.getLogger("channel_manager.routers.scheduler")

router = APIRouter(tags=["CM Scheduler & Jobs"])


class UpdatePollingRequest(BaseModel):
    interval_seconds: int = 300


# ─── Scheduled Import Jobs ───────────────────────────────────────

@router.post("/import-jobs/run/{connector_id}")
async def run_scheduled_import(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ScheduledImportService()
    result = await svc.run_scheduled_import(
        current_user.tenant_id, connector_id, current_user.id,
    )
    return result


@router.post("/import-jobs/run-all")
async def run_all_scheduled_imports(
    current_user: User = Depends(get_current_user),
):
    svc = ScheduledImportService()
    return await svc.run_all_connectors(current_user.tenant_id)


@router.get("/import-jobs")
async def list_import_jobs(
    connector_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
):
    svc = ScheduledImportService()
    jobs = await svc.get_import_jobs(
        current_user.tenant_id, connector_id, status, limit,
    )
    return {"jobs": jobs, "count": len(jobs)}


@router.get("/import-jobs/{job_id}")
async def get_import_job_detail(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ScheduledImportService()
    detail = await svc.get_job_detail(current_user.tenant_id, job_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Import job not found")
    return detail


@router.post("/import-jobs/{job_id}/retry")
async def retry_failed_import_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ScheduledImportService()
    return await svc.retry_failed_job(
        current_user.tenant_id, job_id, current_user.id,
    )


@router.post("/safety-net/inventory-sync")
async def run_safety_net_sync(
    current_user: User = Depends(get_current_user),
):
    svc = ScheduledImportService()
    return await svc.run_safety_net_inventory_sync(current_user.tenant_id)


# ─── Polling Configuration ───────────────────────────────────────

@router.get("/connectors/{connector_id}/polling-config")
async def get_polling_config(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    connector = await repo.get_connector(current_user.tenant_id, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    env = connector.get("environment", "sandbox")
    env_config = get_environment_config(env)
    return {
        "connector_id": connector_id,
        "environment": env,
        "reservation_polling_interval": connector.get(
            "reservation_polling_interval", env_config.reservation_polling_interval_seconds,
        ),
        "sync_polling_interval": connector.get(
            "sync_polling_interval", env_config.sync_polling_interval_seconds,
        ),
        "default_reservation_interval": env_config.reservation_polling_interval_seconds,
        "default_sync_interval": env_config.sync_polling_interval_seconds,
    }


@router.put("/connectors/{connector_id}/polling-config")
async def update_polling_config(
    connector_id: str,
    req: UpdatePollingRequest,
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    connector = await repo.get_connector(current_user.tenant_id, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    if req.interval_seconds < 60:
        raise HTTPException(status_code=400, detail="Minimum polling interval is 60 seconds")
    connector["reservation_polling_interval"] = req.interval_seconds
    await repo.upsert_connector(connector)
    return {"message": "Polling config updated", "interval_seconds": req.interval_seconds}


# ─── Environment Configuration ───────────────────────────────────

@router.get("/environments")
async def list_environments(
    current_user: User = Depends(get_current_user),
):
    return {"environments": get_all_environments()}


@router.get("/environments/{env_name}")
async def get_environment(
    env_name: str,
    current_user: User = Depends(get_current_user),
):
    config = get_environment_config(env_name)
    return config.model_dump()


@router.put("/connectors/{connector_id}/environment")
async def set_connector_environment(
    connector_id: str,
    environment: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    connector = await repo.get_connector(current_user.tenant_id, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    if environment not in ("mock", "sandbox", "production"):
        raise HTTPException(status_code=400, detail="Invalid environment. Must be: mock, sandbox, production")
    connector["environment"] = environment
    await repo.upsert_connector(connector)
    return {"message": f"Environment set to {environment}", "connector_id": connector_id}
