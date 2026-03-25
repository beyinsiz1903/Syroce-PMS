"""
Data Pipeline Router - API endpoints for ML data pipeline management.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from modules.data_pipeline.dataset_generator import dataset_generator
from modules.data_pipeline.feature_store import feature_store
from modules.data_pipeline.model_registry import model_registry
from modules.data_pipeline.pipeline_orchestrator import pipeline_orchestrator
from modules.data_pipeline.prediction_service import prediction_service
from shared_kernel.tenancy_context import TenantContext, get_current_tenant

router = APIRouter(prefix="/api/data-pipeline", tags=["data-pipeline"])


@router.get("/feature-store/summary")
async def get_feature_store_summary(tenant: TenantContext = Depends(get_current_tenant)):
    return await feature_store.get_summary(tenant.tenant_id)


@router.post("/feature-store/extract/{feature_set}")
async def extract_features(feature_set: str, tenant: TenantContext = Depends(get_current_tenant)):
    if feature_set == "revenue":
        return await feature_store.extract_revenue_features(tenant.tenant_id)
    elif feature_set == "operational":
        return await feature_store.extract_operational_features(tenant.tenant_id)
    elif feature_set == "guest_intelligence":
        return await feature_store.extract_guest_features(tenant.tenant_id)
    raise HTTPException(status_code=400, detail=f"Unknown feature set: {feature_set}")


@router.get("/datasets")
async def list_datasets(
    model_type: str | None = None,
    limit: int = Query(20, le=100),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await dataset_generator.list_datasets(tenant.tenant_id, model_type, limit)


@router.post("/datasets/generate")
async def generate_dataset(
    model_type: str = Query(...),
    feature_set: str = Query(...),
    description: str = Query(""),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await dataset_generator.generate_dataset(
        tenant.tenant_id, model_type, feature_set, description
    )


@router.get("/models")
async def list_models(
    model_type: str | None = None,
    limit: int = Query(20, le=100),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await model_registry.list_models(tenant.tenant_id, model_type, limit)


@router.get("/models/summary")
async def get_model_summary(tenant: TenantContext = Depends(get_current_tenant)):
    return await model_registry.get_summary(tenant.tenant_id)


@router.get("/models/stale")
async def get_stale_models(
    stale_hours: int = Query(24),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await model_registry.get_stale_models(tenant.tenant_id, stale_hours)


@router.post("/models/{model_id}/deploy")
async def deploy_model(model_id: str, tenant: TenantContext = Depends(get_current_tenant)):
    return await model_registry.deploy_model(model_id)


@router.get("/predictions")
async def list_predictions(
    model_type: str | None = None,
    limit: int = Query(20, le=100),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await prediction_service.get_predictions(tenant.tenant_id, model_type, limit)


@router.get("/predictions/confidence")
async def get_confidence_summary(tenant: TenantContext = Depends(get_current_tenant)):
    return await prediction_service.get_confidence_summary(tenant.tenant_id)


@router.get("/predictions/stale")
async def get_stale_predictions(
    stale_hours: int = Query(12),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await prediction_service.get_stale_predictions(tenant.tenant_id, stale_hours)


@router.post("/predict")
async def make_prediction(
    model_type: str = Query(...),
    tenant: TenantContext = Depends(get_current_tenant),
):
    input_data = {"current_rate": 150, "occupancy": 0.7, "expected_departures": 12}
    return await prediction_service.predict(tenant.tenant_id, model_type, input_data)


@router.get("/runs")
async def list_pipeline_runs(
    model_type: str | None = None,
    limit: int = Query(20, le=100),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await pipeline_orchestrator.get_runs(tenant.tenant_id, model_type, limit)


@router.post("/runs/execute")
async def execute_pipeline(
    model_type: str = Query(...),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await pipeline_orchestrator.run_full_pipeline(
        tenant.tenant_id, model_type, triggered_by=tenant.user_id or "api"
    )


@router.get("/health")
async def get_pipeline_health(tenant: TenantContext = Depends(get_current_tenant)):
    return await pipeline_orchestrator.get_pipeline_health(tenant.tenant_id)
