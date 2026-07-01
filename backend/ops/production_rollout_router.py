"""
Phase 7 — Production Rollout & Pilot Readiness Router
=======================================================
Unified API for:
- Production environment preparation
- Canary deployment strategy
- Pilot hotel onboarding
- Pilot monitoring pack
- Production load validation
- Tenant isolation confirmation
- Post-launch monitoring
- Final platform maturity score
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from common.context import OperationContext
from common.response import from_service_result
from core.security import get_current_user
from modules.pms_core.role_permission_service import require_op  # v101 DW
from ops.canary_deployment_service import canary_deployment_service
from ops.golive_scorer import golive_scorer
from ops.pilot_monitoring_service import pilot_monitoring_service
from ops.pilot_onboarding_service import pilot_onboarding_service
from ops.post_launch_monitoring_service import post_launch_monitoring_service
from ops.production_env_service import production_env_service
from ops.production_load_validation_service import production_load_validation_service
from ops.tenant_isolation_confirmation_service import tenant_isolation_confirmation_service

router = APIRouter(prefix="/api/production", tags=["Phase 7 — Production Rollout"])


# ── Schemas ──────────────────────────────────────────────────────────


class AdvanceStageRequest(BaseModel):
    target_stage_id: str


class RollbackRequest(BaseModel):
    reason: str


class OnboardingRequest(BaseModel):
    hotel_name: str
    config: dict[str, Any] | None = None


class CompleteStepRequest(BaseModel):
    step_id: str
    notes: str = ""


class RunScenarioRequest(BaseModel):
    scenario_id: str


class RecordDrillRequest(BaseModel):
    schedule_id: str
    result: str
    details: dict[str, Any] | None = None


# ═══════════════════════════════════════════════════════════════════════
# 1. PRODUCTION ENVIRONMENT PREPARATION
# ═══════════════════════════════════════════════════════════════════════


@router.get("/env/validate")
async def validate_production_env(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await production_env_service.run_full_validation(ctx)
    return from_service_result(result)


# ═══════════════════════════════════════════════════════════════════════
# 2. CANARY DEPLOYMENT
# ═══════════════════════════════════════════════════════════════════════


@router.get("/canary/plan")
async def get_canary_plan(user=Depends(get_current_user)):
    result = await canary_deployment_service.get_deployment_plan()
    return from_service_result(result)


@router.get("/canary/status")
async def get_canary_status(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await canary_deployment_service.get_current_stage(ctx)
    return from_service_result(result)


@router.post("/canary/advance")
async def advance_canary_stage(
    req: AdvanceStageRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await canary_deployment_service.advance_stage(ctx, req.target_stage_id)
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)


@router.post("/canary/rollback")
async def rollback_canary(
    req: RollbackRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await canary_deployment_service.rollback(ctx, req.reason)
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)


@router.get("/canary/triggers")
async def check_rollback_triggers(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await canary_deployment_service.check_rollback_triggers(ctx)
    return from_service_result(result)


# ═══════════════════════════════════════════════════════════════════════
# 3. PILOT HOTEL ONBOARDING
# ═══════════════════════════════════════════════════════════════════════


@router.post("/pilot/onboarding")
async def create_pilot_onboarding(
    req: OnboardingRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await pilot_onboarding_service.create_onboarding(ctx, req.hotel_name, req.config)
    return from_service_result(result)


@router.get("/pilot/onboarding")
async def get_pilot_onboarding(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await pilot_onboarding_service.get_onboarding(ctx)
    return from_service_result(result)


@router.post("/pilot/onboarding/complete-step")
async def complete_onboarding_step(
    req: CompleteStepRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await pilot_onboarding_service.complete_step(ctx, req.step_id, req.notes)
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)


@router.post("/pilot/onboarding/run-auto")
async def run_auto_validations(
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await pilot_onboarding_service.run_auto_validations(ctx)
    return from_service_result(result)


@router.get("/pilot/success-criteria")
async def get_pilot_success_criteria(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await pilot_onboarding_service.get_success_criteria(ctx)
    return from_service_result(result)


# ═══════════════════════════════════════════════════════════════════════
# 4. PILOT MONITORING PACK
# ═══════════════════════════════════════════════════════════════════════


@router.get("/monitoring/dashboard")
async def get_monitoring_dashboard(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await pilot_monitoring_service.get_tenant_dashboard(ctx)
    return from_service_result(result)


@router.get("/monitoring/alerts-config")
async def get_monitoring_alerts_config(user=Depends(get_current_user)):
    result = await pilot_monitoring_service.get_operational_alerts_config()
    return from_service_result(result)


@router.post("/monitoring/daily-report")
async def generate_daily_report(
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await pilot_monitoring_service.generate_daily_report(ctx)
    return from_service_result(result)


@router.get("/monitoring/reports")
async def get_report_history(
    limit: int = Query(10, le=50),
    user=Depends(get_current_user),
):
    ctx = OperationContext.from_user(user)
    result = await pilot_monitoring_service.get_report_history(ctx, limit)
    return from_service_result(result)


# ═══════════════════════════════════════════════════════════════════════
# 5. INCIDENT RESPONSE READINESS (uses existing incident service)
# ═══════════════════════════════════════════════════════════════════════


@router.get("/incident-readiness")
async def get_incident_readiness(user=Depends(get_current_user)):
    """Verify incident response readiness: lifecycle, recovery tools, runbooks."""
    ctx = OperationContext.from_user(user)
    from modules.incident.incident_service import incident_response_service

    health = await incident_response_service.get_service_health_matrix(ctx)
    return from_service_result(health)


# ═══════════════════════════════════════════════════════════════════════
# 6. PRODUCTION LOAD VALIDATION
# ═══════════════════════════════════════════════════════════════════════


@router.get("/load/scenarios")
async def get_load_scenarios(user=Depends(get_current_user)):
    result = await production_load_validation_service.get_scenarios()
    return from_service_result(result)


@router.post("/load/run")
async def run_load_scenario(
    req: RunScenarioRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await production_load_validation_service.run_scenario(ctx, req.scenario_id)
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)


@router.get("/load/report")
async def get_load_report(
    hours: int = Query(24, ge=1, le=720),
    user=Depends(get_current_user),
):
    ctx = OperationContext.from_user(user)
    result = await production_load_validation_service.get_load_report(ctx, hours)
    return from_service_result(result)


# ═══════════════════════════════════════════════════════════════════════
# 7. TENANT ISOLATION CONFIRMATION
# ═══════════════════════════════════════════════════════════════════════


@router.get("/isolation/validate")
async def validate_tenant_isolation(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await tenant_isolation_confirmation_service.run_full_validation(ctx)
    return from_service_result(result)


# ═══════════════════════════════════════════════════════════════════════
# 8. POST-LAUNCH MONITORING
# ═══════════════════════════════════════════════════════════════════════


@router.get("/post-launch/status")
async def get_post_launch_status(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await post_launch_monitoring_service.get_monitoring_status(ctx)
    return from_service_result(result)


@router.post("/post-launch/record-drill")
async def record_drill(
    req: RecordDrillRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await post_launch_monitoring_service.record_drill_execution(ctx, req.schedule_id, req.result, req.details)
    return from_service_result(result)


@router.get("/post-launch/maturity-report")
async def get_maturity_report(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await post_launch_monitoring_service.get_platform_maturity_report(ctx)
    return from_service_result(result)


# ═══════════════════════════════════════════════════════════════════════
# 9. FINAL PLATFORM MATURITY SCORE
# ═══════════════════════════════════════════════════════════════════════


@router.get("/maturity/score")
async def get_final_maturity_score(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await golive_scorer.compute_score(ctx)
    return from_service_result(result)


@router.get("/maturity/history")
async def get_maturity_history(
    limit: int = Query(10, le=50),
    user=Depends(get_current_user),
):
    ctx = OperationContext.from_user(user)
    result = await golive_scorer.get_score_history(ctx, limit)
    return from_service_result(result)


# ── Soak Test Results ────────────────────────────────────────────────


@router.get("/soak-test/status")
async def get_soak_test_status(user=Depends(get_current_user)):
    """Get current soak test status and results."""
    import json
    from pathlib import Path

    results = {
        "soak_running": False,
        "final_report": None,
        "system_metrics": None,
        "locust_stats": None,
    }

    # Check if locust is running
    import subprocess

    try:
        ps = subprocess.run(["pgrep", "-f", "locust"], capture_output=True, text=True)
        results["soak_running"] = bool(ps.stdout.strip())
    except Exception:
        pass

    # Final report from locust event listener
    final_path = Path("/app/test_reports/soak_final_report.json")
    if final_path.exists():
        try:
            results["final_report"] = json.loads(final_path.read_text())
        except Exception:
            pass

    # System metrics from monitor
    metrics_path = Path("/app/test_reports/soak_system_metrics.json")
    if metrics_path.exists():
        try:
            results["system_metrics"] = json.loads(metrics_path.read_text())
        except Exception:
            pass

    # Latest CSV stats
    report_dir = Path("/app/test_reports")
    csv_files = sorted(report_dir.glob("soak_*_stats.csv"), reverse=True)
    if csv_files:
        try:
            import csv

            with open(csv_files[0]) as f:
                reader = csv.DictReader(f)
                results["locust_stats"] = list(reader)
        except Exception:
            pass

    return results


@router.post("/soak-test/start")
async def start_soak_test(
    duration: str = Query("15m", description="Test süresi: 15m, 30m, 1h, 12h"),
    users: int = Query(20, ge=5, le=100),
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Start soak test in background."""
    import subprocess

    # Check if already running
    try:
        ps = subprocess.run(["pgrep", "-f", "locust"], capture_output=True, text=True)
        if ps.stdout.strip():
            raise HTTPException(400, "Soak test is already running")
    except HTTPException:
        raise
    except Exception:
        pass

    # Start in background
    subprocess.Popen(
        ["bash", "/app/load_tests/run_soak_test.sh", duration, str(users)],
        stdout=open("/app/test_reports/soak_runner.log", "w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    return {
        "status": "started",
        "duration": duration,
        "users": users,
        "message": f"Soak test started: {users} users for {duration}",
    }


@router.post("/soak-test/stop")
async def stop_soak_test(
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Stop running soak test."""
    import subprocess

    try:
        subprocess.run(["pkill", "-f", "locust"], capture_output=True)
        subprocess.run(["pkill", "-f", "soak_monitor"], capture_output=True)
        return {"status": "stopped", "message": "Soak test stopped"}
    except Exception as e:
        raise HTTPException(500, f"Failed to stop soak test: {str(e)}")
