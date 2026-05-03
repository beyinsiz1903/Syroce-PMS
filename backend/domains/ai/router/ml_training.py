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
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pydantic import Field as _PydField

from core.database import db
from core.helpers import (
    require_module,
)
from core.security import (
    get_current_user,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)


class GuestPersona(BaseModel):
    id: str = _PydField(default_factory=lambda: __import__('uuid').uuid4().hex)
    tenant_id: str
    guest_id: str
    persona_type: str
    confidence_score: float
    indicators: list[str] = []
    recommendations: list[str] = []
    created_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))


class MaintenanceAlert(BaseModel):
    id: str = _PydField(default_factory=lambda: __import__('uuid').uuid4().hex)
    tenant_id: str
    room_id: str
    equipment_type: str
    severity: str
    prediction: str
    indicators: list[str] = []
    recommended_action: str
    estimated_failure_days: int = 0
    created_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))


async def create_predictive_maintenance_task(
    tenant_id: str, room_id: str, room_number: str, title: str, severity: str, alert_id: str
) -> None:
    try:
        await db.maintenance_tasks.insert_one({
            'id': uuid.uuid4().hex,
            'tenant_id': tenant_id,
            'room_id': room_id,
            'room_number': room_number,
            'title': title,
            'severity': severity,
            'source_alert_id': alert_id,
            'status': 'pending',
            'source': 'predictive_ai',
            'created_at': datetime.now(UTC).isoformat(),
        })
    except Exception:
        logger.exception('[ai] failed to create predictive maintenance task')


def distribute_tasks(rooms: list[dict], staff: list[dict], task_type: str) -> list[dict]:
    """Round-robin task distribution across staff members."""
    if not staff:
        return []
    minutes_per_task = 30 if task_type == 'checkout' else 20
    out = []
    for idx, room in enumerate(rooms):
        member = staff[idx % len(staff)]
        out.append({
            'staff_id': member.get('id') or member.get('staff_id'),
            'staff_name': member.get('name') or member.get('staff_name') or 'Staff',
            'task': {
                'room_id': room.get('id') or room.get('room_id'),
                'type': task_type,
                'priority': 'high' if task_type == 'checkout' else 'normal',
                'estimated_minutes': minutes_per_task,
            },
            'estimated_minutes': minutes_per_task,
        })
    return out


def generate_scheduling_recommendations(capacity_pct: float, staff_count: int, total_rooms: int) -> list[str]:
    recs = []
    if capacity_pct >= 110:
        recs.append('Schedule additional housekeeping staff or extend shifts.')
    elif capacity_pct >= 90:
        recs.append('Capacity is tight — monitor task completion closely.')
    else:
        recs.append('Workload is healthy.')
    if staff_count and total_rooms / max(staff_count, 1) > 18:
        recs.append('Consider rebalancing room-to-staff ratio.')
    return recs


def get_tier_benefits(tier: str) -> list[str]:
    matrix = {
        'silver': ['Welcome drink', 'Late checkout 1h'],
        'gold': ['Room upgrade subject to availability', 'Late checkout 2h', '10% F&B discount'],
        'platinum': ['Guaranteed upgrade', 'Late checkout 4h', '20% F&B discount', 'Lounge access'],
    }
    return matrix.get((tier or '').lower(), [])


logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
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


# ── POST /ml/rms/train ──
@router.post("/ml/rms/train")
async def train_rms_model(
    historical_days: int = 730,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """
    Train RMS (Revenue Management System) ML Model
    - Generates 2 years of synthetic training data
    - Trains XGBoost models for occupancy prediction and dynamic pricing
    - Saves models to disk for production use
    """
    try:
        from ml_data_generators import RMSDataGenerator
        from ml_trainers import RMSModelTrainer

        # Generate training data
        logger.info(f"Generating {historical_days} days of RMS training data...")
        data_df = RMSDataGenerator.generate(days=historical_days)

        # Train models
        trainer = RMSModelTrainer(model_dir='ml_models')
        metrics = trainer.train(data_df)

        return {
            'success': True,
            'message': 'RMS models trained successfully',
            'metrics': metrics,
            'data_summary': {
                'total_samples': len(data_df),
                'date_range': {
                    'start': data_df['date'].min(),
                    'end': data_df['date'].max()
                },
                'occupancy_range': {
                    'min': float(data_df['occupancy_rate'].min()),
                    'max': float(data_df['occupancy_rate'].max()),
                    'mean': float(data_df['occupancy_rate'].mean())
                },
                'price_range': {
                    'min': float(data_df['optimal_price'].min()),
                    'max': float(data_df['optimal_price'].max()),
                    'mean': float(data_df['optimal_price'].mean())
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")
# ── POST /ml/persona/train ──
@router.post("/ml/persona/train")
async def train_persona_model(
    num_guests: int = 400,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """
    Train Guest Persona ML Model
    - Generates 300-500 synthetic guest profiles
    - Trains Random Forest classifier for persona segmentation
    - Saves model to disk for production use
    """
    try:
        from ml_data_generators import PersonaDataGenerator
        from ml_trainers import PersonaModelTrainer

        # Generate training data
        logger.info(f"Generating {num_guests} guest persona training samples...")
        data_df = PersonaDataGenerator.generate(num_guests=num_guests)

        # Train model
        trainer = PersonaModelTrainer(model_dir='ml_models')
        metrics = trainer.train(data_df)

        return {
            'success': True,
            'message': 'Persona model trained successfully',
            'metrics': metrics,
            'data_summary': {
                'total_guests': len(data_df),
                'persona_distribution': data_df['persona_type'].value_counts().to_dict(),
                'avg_stays': float(data_df['total_stays'].mean()),
                'avg_spend': float(data_df['avg_spend'].mean())
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")
# ── POST /ml/predictive-maintenance/train ──
@router.post("/ml/predictive-maintenance/train")
async def train_predictive_maintenance_model(
    num_samples: int = 1000,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """
    Train Predictive Maintenance ML Model
    - Generates IoT sensor simulation data
    - Trains XGBoost classifier for failure risk prediction
    - Trains Gradient Boosting for days-until-failure prediction
    - Saves models to disk for production use
    """
    try:
        from ml_data_generators import PredictiveMaintenanceDataGenerator
        from ml_trainers import PredictiveMaintenanceModelTrainer

        # Generate training data
        logger.info(f"Generating {num_samples} predictive maintenance training samples...")
        data_df = PredictiveMaintenanceDataGenerator.generate(num_samples=num_samples)

        # Train models
        trainer = PredictiveMaintenanceModelTrainer(model_dir='ml_models')
        metrics = trainer.train(data_df)

        return {
            'success': True,
            'message': 'Predictive maintenance models trained successfully',
            'metrics': metrics,
            'data_summary': {
                'total_samples': len(data_df),
                'equipment_distribution': data_df['equipment_type'].value_counts().to_dict(),
                'risk_distribution': data_df['failure_risk'].value_counts().to_dict(),
                'avg_days_until_failure': float(data_df['days_until_failure'].mean())
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")
# ── POST /ml/hk-scheduler/train ──
@router.post("/ml/hk-scheduler/train")
async def train_hk_scheduler_model(
    num_days: int = 365,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """
    Train Housekeeping Scheduler ML Model
    - Generates occupancy-based staffing data
    - Trains Random Forest regressors for staff and hours prediction
    - Saves models to disk for production use
    """
    try:
        from ml_data_generators import HKSchedulerDataGenerator
        from ml_trainers import HKSchedulerModelTrainer

        # Generate training data
        logger.info(f"Generating {num_days} days of HK scheduler training data...")
        data_df = HKSchedulerDataGenerator.generate(num_days=num_days)

        # Train models
        trainer = HKSchedulerModelTrainer(model_dir='ml_models')
        metrics = trainer.train(data_df)

        return {
            'success': True,
            'message': 'HK scheduler models trained successfully',
            'metrics': metrics,
            'data_summary': {
                'total_days': len(data_df),
                'avg_occupancy': float(data_df['occupancy_rate'].mean()),
                'avg_staff_needed': float(data_df['staff_needed'].mean()),
                'avg_hours': float(data_df['estimated_hours'].mean()),
                'peak_staff_needed': int(data_df['staff_needed'].max())
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")
# ── POST /ml/train-all ──
@router.post("/ml/train-all")
async def train_all_models(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """
    Train ALL ML Models in sequence
    - RMS (Revenue Management)
    - Persona (Guest Segmentation)
    - Predictive Maintenance
    - HK Scheduler
    """
    results = {}
    errors = []

    try:
        # Import all required modules
        from ml_data_generators import HKSchedulerDataGenerator, PersonaDataGenerator, PredictiveMaintenanceDataGenerator, RMSDataGenerator
        from ml_trainers import HKSchedulerModelTrainer, PersonaModelTrainer, PredictiveMaintenanceModelTrainer, RMSModelTrainer

        # 1. Train RMS Model
        try:
            logger.info("\n=== Training RMS Model ===")
            data_df = RMSDataGenerator.generate(days=730)
            trainer = RMSModelTrainer(model_dir='ml_models')
            results['rms'] = trainer.train(data_df)
            results['rms']['status'] = 'success'
        except Exception as e:
            results['rms'] = {'status': 'failed', 'error': str(e)}
            errors.append(f"RMS: {str(e)}")

        # 2. Train Persona Model
        try:
            logger.info("\n=== Training Persona Model ===")
            data_df = PersonaDataGenerator.generate(num_guests=400)
            trainer = PersonaModelTrainer(model_dir='ml_models')
            results['persona'] = trainer.train(data_df)
            results['persona']['status'] = 'success'
        except Exception as e:
            results['persona'] = {'status': 'failed', 'error': str(e)}
            errors.append(f"Persona: {str(e)}")

        # 3. Train Predictive Maintenance Model
        try:
            logger.info("\n=== Training Predictive Maintenance Model ===")
            data_df = PredictiveMaintenanceDataGenerator.generate(num_samples=1000)
            trainer = PredictiveMaintenanceModelTrainer(model_dir='ml_models')
            results['predictive_maintenance'] = trainer.train(data_df)
            results['predictive_maintenance']['status'] = 'success'
        except Exception as e:
            results['predictive_maintenance'] = {'status': 'failed', 'error': str(e)}
            errors.append(f"Predictive Maintenance: {str(e)}")

        # 4. Train HK Scheduler Model
        try:
            logger.info("\n=== Training HK Scheduler Model ===")
            data_df = HKSchedulerDataGenerator.generate(num_days=365)
            trainer = HKSchedulerModelTrainer(model_dir='ml_models')
            results['hk_scheduler'] = trainer.train(data_df)
            results['hk_scheduler']['status'] = 'success'
        except Exception as e:
            results['hk_scheduler'] = {'status': 'failed', 'error': str(e)}
            errors.append(f"HK Scheduler: {str(e)}")

        # Summary
        successful = sum(1 for r in results.values() if r.get('status') == 'success')
        total = len(results)

        return {
            'success': len(errors) == 0,
            'message': f'Training complete: {successful}/{total} models trained successfully',
            'results': results,
            'errors': errors if errors else None,
            'summary': {
                'total_models': total,
                'successful': successful,
                'failed': len(errors)
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulk training failed: {str(e)}")
# ── GET /ml/models/status ──
@router.get("/ml/models/status")
async def get_ml_models_status(
    current_user: User = Depends(get_current_user)
):
    """
    Get status of all ML models
    - Check if models are trained and available
    - Return training metrics if available
    """
    import json

    model_dir = 'ml_models'

    models_status = {
        'rms': {
            'trained': False,
            'files': ['rms_occupancy_model.pkl', 'rms_pricing_model.pkl', 'rms_metrics.json']
        },
        'persona': {
            'trained': False,
            'files': ['persona_model.pkl', 'persona_label_encoder.pkl', 'persona_metrics.json']
        },
        'predictive_maintenance': {
            'trained': False,
            'files': ['maintenance_risk_model.pkl', 'maintenance_days_model.pkl', 'maintenance_label_encoder.pkl', 'maintenance_equipment_encoder.pkl', 'maintenance_metrics.json']
        },
        'hk_scheduler': {
            'trained': False,
            'files': ['hk_staff_model.pkl', 'hk_hours_model.pkl', 'hk_scheduler_metrics.json']
        }
    }

    # Check each model
    for model_name, info in models_status.items():
        all_files_exist = all(
            os.path.exists(os.path.join(model_dir, file))
            for file in info['files']
        )

        info['trained'] = all_files_exist
        info['files_status'] = {
            file: os.path.exists(os.path.join(model_dir, file))
            for file in info['files']
        }

        # Load metrics if available
        metrics_file = [f for f in info['files'] if f.endswith('_metrics.json')]
        if metrics_file and all_files_exist:
            try:
                with open(os.path.join(model_dir, metrics_file[0])) as f:
                    info['metrics'] = json.load(f)
            except Exception:
                info['metrics'] = None

    # Overall summary
    trained_count = sum(1 for info in models_status.values() if info['trained'])
    total_count = len(models_status)

    return {
        'models': models_status,
        'summary': {
            'total_models': total_count,
            'trained_models': trained_count,
            'untrained_models': total_count - trained_count,
            'all_ready': trained_count == total_count
        }
    }
