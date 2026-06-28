"""
ml_training

Auto-split sub-router (shared imports/classes inlined).
"""

"""
AI / ML Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pydantic import Field as _PydField

from core.database import db
from core.security import (
    get_current_user,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)


class GuestPersona(BaseModel):
    id: str = _PydField(default_factory=lambda: __import__("uuid").uuid4().hex)
    tenant_id: str
    guest_id: str
    persona_type: str
    confidence_score: float
    indicators: list[str] = []
    recommendations: list[str] = []
    created_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))


class MaintenanceAlert(BaseModel):
    id: str = _PydField(default_factory=lambda: __import__("uuid").uuid4().hex)
    tenant_id: str
    room_id: str
    equipment_type: str
    severity: str
    prediction: str
    indicators: list[str] = []
    recommended_action: str
    estimated_failure_days: int = 0
    created_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))


async def create_predictive_maintenance_task(tenant_id: str, room_id: str, room_number: str, title: str, severity: str, alert_id: str) -> None:
    try:
        await db.maintenance_tasks.insert_one(
            {
                "id": uuid.uuid4().hex,
                "tenant_id": tenant_id,
                "room_id": room_id,
                "room_number": room_number,
                "title": title,
                "severity": severity,
                "source_alert_id": alert_id,
                "status": "pending",
                "source": "predictive_ai",
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
    except Exception:
        logger.exception("[ai] failed to create predictive maintenance task")


def distribute_tasks(rooms: list[dict], staff: list[dict], task_type: str) -> list[dict]:
    """Round-robin task distribution across staff members."""
    if not staff:
        return []
    minutes_per_task = 30 if task_type == "checkout" else 20
    out = []
    for idx, room in enumerate(rooms):
        member = staff[idx % len(staff)]
        out.append(
            {
                "staff_id": member.get("id") or member.get("staff_id"),
                "staff_name": member.get("name") or member.get("staff_name") or "Staff",
                "task": {
                    "room_id": room.get("id") or room.get("room_id"),
                    "type": task_type,
                    "priority": "high" if task_type == "checkout" else "normal",
                    "estimated_minutes": minutes_per_task,
                },
                "estimated_minutes": minutes_per_task,
            }
        )
    return out


def generate_scheduling_recommendations(capacity_pct: float, staff_count: int, total_rooms: int) -> list[str]:
    recs = []
    if capacity_pct >= 110:
        recs.append("Schedule additional housekeeping staff or extend shifts.")
    elif capacity_pct >= 90:
        recs.append("Capacity is tight — monitor task completion closely.")
    else:
        recs.append("Workload is healthy.")
    if staff_count and total_rooms / max(staff_count, 1) > 18:
        recs.append("Consider rebalancing room-to-staff ratio.")
    return recs


def get_tier_benefits(tier: str) -> list[str]:
    matrix = {
        "silver": ["Welcome drink", "Late checkout 1h"],
        "gold": ["Room upgrade subject to availability", "Late checkout 2h", "10% F&B discount"],
        "platinum": ["Guaranteed upgrade", "Late checkout 4h", "20% F&B discount", "Lounge access"],
    }
    return matrix.get((tier or "").lower(), [])


logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


# ============= AI DYNAMIC PRICING (MARKET LEADER FEATURE) =============


# ============= WHATSAPP BUSINESS INTEGRATION =============


# ============= HOUSEKEEPING AI PREDICTIONS =============


# ============= PREDICTIVE ANALYTICS (GAME-CHANGER #2) =============


# ============= SOCIAL MEDIA COMMAND CENTER (GAME-CHANGER #3) =============


# ============= REVENUE AUTOPILOT (GAME-CHANGER #4) =============


# ============= GUEST DNA PROFILE (GAME-CHANGER #5) =============


# ============= DYNAMIC STAFFING AI (GAME-CHANGER #6) =============


# ============= DELUXE+ ENTERPRISE FEATURES =============


# ============= MAINTENANCE WORK ORDERS =============


# ============= LOYALTY PROGRAM ENHANCEMENTS =============


# ============= AI HOUSEKEEPING SCHEDULER =============


# ============= MONITORING & LOGGING ENDPOINTS =============


# ============= NEW ENHANCEMENTS: OTA, GUEST PROFILE, HK MOBILE, RMS, MESSAGING, POS =============

# ===== 1. OTA RESERVATION DETAILS ENHANCEMENTS =====

# Extra charges model
# Multi-room reservation tracking

router = APIRouter(prefix="/api", tags=["AI / ML"])


# ── ML training dispatch boundary ──
# Agir ML egitimi API surecinde CALISMAZ. Tum /ml/*/train uc noktalari isi
# `ml` Celery kuyruguna gonderir; agir ML yigini (sklearn/xgboost/numpy/pandas)
# yalnizca ml.txt kurulu ML worker surecinde yuklenir. Broker/worker erisilemezse
# uc nokta kontrollu sekilde 503 dondurur (sessiz cokme yok); kritik PMS akislari
# etkilenmez. Egitim sonuclari GET /ml/jobs/{task_id} ile tuketilir.
def _dispatch_ml_training(model: str, params: dict) -> dict:
    """ML egitimini 'ml' worker kuyruguna gonderir.

    Basarili gonderim: kuyruga-alindi zarfi + task_id dondurur.
    Broker/worker erisilemezse HTTPException 503 (temiz degrade) firlatir.
    """
    try:
        from celery_app import celery_app

        async_result = celery_app.send_task(
            "celery_tasks.ml_training_task",
            args=[model, params],
            queue="ml",
        )
    except Exception as e:  # noqa: BLE001 - broker/worker unavailable → degrade
        logger.warning("[ai/ml] training dispatch failed for model=%s: %s", model, e)
        raise HTTPException(
            status_code=503,
            detail="ML worker queue unavailable; training could not be dispatched",
        )

    return {
        "success": True,
        "status": "queued",
        "queued": True,
        "model": model,
        "params": params,
        "task_id": async_result.id,
        "queue": "ml",
        "message": f"{model} training dispatched to ML worker queue",
        "status_url": f"/api/ml/jobs/{async_result.id}",
    }


# ── POST /ml/rms/train ──
@router.post("/ml/rms/train")
async def train_rms_model(
    historical_days: int = 730,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """
    Dispatch RMS (Revenue Management System) ML training to the ML worker queue.
    - Heavy training (XGBoost / data generation) runs out-of-process on the ML worker.
    - Returns a queued-job envelope; poll GET /ml/jobs/{task_id} for the result.
    """
    return _dispatch_ml_training("rms", {"historical_days": historical_days})


# ── POST /ml/persona/train ──
@router.post("/ml/persona/train")
async def train_persona_model(
    num_guests: int = 400,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """
    Dispatch Guest Persona ML training to the ML worker queue.
    - Heavy training (Random Forest / data generation) runs out-of-process.
    - Returns a queued-job envelope; poll GET /ml/jobs/{task_id} for the result.
    """
    return _dispatch_ml_training("persona", {"num_guests": num_guests})


# ── POST /ml/predictive-maintenance/train ──
@router.post("/ml/predictive-maintenance/train")
async def train_predictive_maintenance_model(
    num_samples: int = 1000,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """
    Dispatch Predictive Maintenance ML training to the ML worker queue.
    - Heavy training (XGBoost / Gradient Boosting) runs out-of-process.
    - Returns a queued-job envelope; poll GET /ml/jobs/{task_id} for the result.
    """
    return _dispatch_ml_training("predictive_maintenance", {"num_samples": num_samples})


# ── POST /ml/hk-scheduler/train ──
@router.post("/ml/hk-scheduler/train")
async def train_hk_scheduler_model(
    num_days: int = 365,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """
    Dispatch Housekeeping Scheduler ML training to the ML worker queue.
    - Heavy training (Random Forest regressors) runs out-of-process.
    - Returns a queued-job envelope; poll GET /ml/jobs/{task_id} for the result.
    """
    return _dispatch_ml_training("hk_scheduler", {"num_days": num_days})


# ── POST /ml/train-all ──
@router.post("/ml/train-all")
async def train_all_models(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """
    Dispatch ALL ML model training (RMS, Persona, Predictive Maintenance,
    HK Scheduler) to the ML worker queue as a single job.
    - Heavy training runs out-of-process on the ML worker.
    - Returns a queued-job envelope; poll GET /ml/jobs/{task_id} for the result.
    """
    return _dispatch_ml_training("all", {})


# ── GET /ml/jobs/{task_id} ──
@router.get("/ml/jobs/{task_id}")
async def get_ml_training_job(
    task_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """
    Poll the status/result of a dispatched ML training job.
    Consumes results over the worker-queue boundary (Celery result backend).
    """
    try:
        from celery_app import celery_app

        async_result = celery_app.AsyncResult(task_id)
        state = async_result.state
        ready = async_result.ready()
    except Exception as e:  # noqa: BLE001 - result backend unavailable → degrade
        logger.warning("[ai/ml] job status lookup failed for task_id=%s: %s", task_id, e)
        raise HTTPException(
            status_code=503,
            detail="ML result backend unavailable; job status could not be retrieved",
        )

    payload = {"task_id": task_id, "state": state, "ready": ready}
    if ready:
        if async_result.successful():
            payload["result"] = async_result.result
        else:
            payload["success"] = False
            payload["error"] = str(async_result.result)
    return payload


# ── GET /ml/models/status ──
@router.get("/ml/models/status")
async def get_ml_models_status(current_user: User = Depends(get_current_user)):
    """
    Get status of all ML models
    - Check if models are trained and available
    - Return training metrics if available
    """
    import json

    model_dir = "ml_models"

    models_status = {
        "rms": {"trained": False, "files": ["rms_occupancy_model.pkl", "rms_pricing_model.pkl", "rms_metrics.json"]},
        "persona": {"trained": False, "files": ["persona_model.pkl", "persona_label_encoder.pkl", "persona_metrics.json"]},
        "predictive_maintenance": {
            "trained": False,
            "files": ["maintenance_risk_model.pkl", "maintenance_days_model.pkl", "maintenance_label_encoder.pkl", "maintenance_equipment_encoder.pkl", "maintenance_metrics.json"],
        },
        "hk_scheduler": {"trained": False, "files": ["hk_staff_model.pkl", "hk_hours_model.pkl", "hk_scheduler_metrics.json"]},
    }

    # Check each model
    for model_name, info in models_status.items():
        all_files_exist = all(os.path.exists(os.path.join(model_dir, file)) for file in info["files"])

        info["trained"] = all_files_exist
        info["files_status"] = {file: os.path.exists(os.path.join(model_dir, file)) for file in info["files"]}

        # Load metrics if available
        metrics_file = [f for f in info["files"] if f.endswith("_metrics.json")]
        if metrics_file and all_files_exist:
            try:
                with open(os.path.join(model_dir, metrics_file[0])) as f:
                    info["metrics"] = json.load(f)
            except Exception:
                info["metrics"] = None

    # Overall summary
    trained_count = sum(1 for info in models_status.values() if info["trained"])
    total_count = len(models_status)

    return {
        "models": models_status,
        "summary": {"total_models": total_count, "trained_models": trained_count, "untrained_models": total_count - trained_count, "all_ready": trained_count == total_count},
    }
