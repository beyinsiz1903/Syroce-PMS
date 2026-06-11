"""
ML Service Boundary
===================

Tek ML sinir modulu. Agir ML yigini (scikit-learn, xgboost, numpy, pandas,
joblib) SADECE burada ve `ml_trainers` / `ml_data_generators` icinde import
edilir. Bu modul yalnizca ML worker surecinde (ml kuyrugu, ml.txt kurulu)
yuklenir; API surecine veya varsayilan worker imajina ASLA statik olarak
baglanmaz.

API/REST katmani egitim sonuclarini bu sinir uzerinden, `ml` Celery kuyruguna
gonderilen `celery_tasks.ml_training_task` araciligiyla tuketir. ML servisi
erisilemezse API uygulamasi kontrollu sekilde degrade olur (503) ve kritik PMS
akislari etkilenmez.

`run_training` cagrildiginda agir importlar tembel (fonksiyon icinde) yapilir,
boylece bu modulun salt yuklenmesi numpy/xgboost gerektirmez.
"""
from __future__ import annotations

from typing import Any

MODEL_DIR = "ml_models"

SUPPORTED_MODELS = ("rms", "persona", "predictive_maintenance", "hk_scheduler", "all")


def _train_rms(params: dict[str, Any]) -> dict[str, Any]:
    from ml_data_generators import RMSDataGenerator
    from ml_trainers import RMSModelTrainer

    historical_days = int(params.get("historical_days", 730))
    data_df = RMSDataGenerator.generate(days=historical_days)
    trainer = RMSModelTrainer(model_dir=MODEL_DIR)
    metrics = trainer.train(data_df)

    return {
        "success": True,
        "message": "RMS models trained successfully",
        "metrics": metrics,
        "data_summary": {
            "total_samples": int(len(data_df)),
            "date_range": {
                "start": str(data_df["date"].min()),
                "end": str(data_df["date"].max()),
            },
            "occupancy_range": {
                "min": float(data_df["occupancy_rate"].min()),
                "max": float(data_df["occupancy_rate"].max()),
                "mean": float(data_df["occupancy_rate"].mean()),
            },
            "price_range": {
                "min": float(data_df["optimal_price"].min()),
                "max": float(data_df["optimal_price"].max()),
                "mean": float(data_df["optimal_price"].mean()),
            },
        },
    }


def _train_persona(params: dict[str, Any]) -> dict[str, Any]:
    from ml_data_generators import PersonaDataGenerator
    from ml_trainers import PersonaModelTrainer

    num_guests = int(params.get("num_guests", 400))
    data_df = PersonaDataGenerator.generate(num_guests=num_guests)
    trainer = PersonaModelTrainer(model_dir=MODEL_DIR)
    metrics = trainer.train(data_df)

    return {
        "success": True,
        "message": "Persona model trained successfully",
        "metrics": metrics,
        "data_summary": {
            "total_guests": int(len(data_df)),
            "persona_distribution": {
                str(k): int(v) for k, v in data_df["persona_type"].value_counts().to_dict().items()
            },
            "avg_stays": float(data_df["total_stays"].mean()),
            "avg_spend": float(data_df["avg_spend"].mean()),
        },
    }


def _train_predictive_maintenance(params: dict[str, Any]) -> dict[str, Any]:
    from ml_data_generators import PredictiveMaintenanceDataGenerator
    from ml_trainers import PredictiveMaintenanceModelTrainer

    num_samples = int(params.get("num_samples", 1000))
    data_df = PredictiveMaintenanceDataGenerator.generate(num_samples=num_samples)
    trainer = PredictiveMaintenanceModelTrainer(model_dir=MODEL_DIR)
    metrics = trainer.train(data_df)

    return {
        "success": True,
        "message": "Predictive maintenance models trained successfully",
        "metrics": metrics,
        "data_summary": {
            "total_samples": int(len(data_df)),
            "equipment_distribution": {
                str(k): int(v) for k, v in data_df["equipment_type"].value_counts().to_dict().items()
            },
            "risk_distribution": {
                str(k): int(v) for k, v in data_df["failure_risk"].value_counts().to_dict().items()
            },
            "avg_days_until_failure": float(data_df["days_until_failure"].mean()),
        },
    }


def _train_hk_scheduler(params: dict[str, Any]) -> dict[str, Any]:
    from ml_data_generators import HKSchedulerDataGenerator
    from ml_trainers import HKSchedulerModelTrainer

    num_days = int(params.get("num_days", 365))
    data_df = HKSchedulerDataGenerator.generate(num_days=num_days)
    trainer = HKSchedulerModelTrainer(model_dir=MODEL_DIR)
    metrics = trainer.train(data_df)

    return {
        "success": True,
        "message": "HK scheduler models trained successfully",
        "metrics": metrics,
        "data_summary": {
            "total_days": int(len(data_df)),
            "avg_occupancy": float(data_df["occupancy_rate"].mean()),
            "avg_staff_needed": float(data_df["staff_needed"].mean()),
            "avg_hours": float(data_df["estimated_hours"].mean()),
            "peak_staff_needed": int(data_df["staff_needed"].max()),
        },
    }


def _train_all(params: dict[str, Any]) -> dict[str, Any]:
    runners = {
        "rms": _train_rms,
        "persona": _train_persona,
        "predictive_maintenance": _train_predictive_maintenance,
        "hk_scheduler": _train_hk_scheduler,
    }

    results: dict[str, Any] = {}
    errors: list[str] = []

    for name, runner in runners.items():
        try:
            outcome = runner(params)
            results[name] = {**outcome.get("metrics", {}), "status": "success"}
        except Exception as exc:  # noqa: BLE001 - per-model isolation, capture and continue
            results[name] = {"status": "failed", "error": str(exc)}
            errors.append(f"{name}: {exc}")

    successful = sum(1 for r in results.values() if r.get("status") == "success")
    total = len(results)

    return {
        "success": len(errors) == 0,
        "message": f"Training complete: {successful}/{total} models trained successfully",
        "results": results,
        "errors": errors if errors else None,
        "summary": {
            "total_models": total,
            "successful": successful,
            "failed": len(errors),
        },
    }


def run_training(model: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Tek giris noktasi: model adina gore ilgili egitimi calistirir.

    model: 'rms' | 'persona' | 'predictive_maintenance' | 'hk_scheduler' | 'all'
    params: modele ozel parametreler (historical_days, num_guests, ...).
    """
    params = params or {}
    key = (model or "all").lower()

    dispatch = {
        "rms": _train_rms,
        "persona": _train_persona,
        "predictive_maintenance": _train_predictive_maintenance,
        "hk_scheduler": _train_hk_scheduler,
        "all": _train_all,
    }

    runner = dispatch.get(key)
    if runner is None:
        raise ValueError(
            f"unknown ml model '{model}'; supported: {', '.join(SUPPORTED_MODELS)}"
        )

    return runner(params)
