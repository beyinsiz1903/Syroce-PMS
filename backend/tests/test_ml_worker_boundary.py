"""
Task #365 — ML worker-queue boundary tests.

Dogrular:
- ml_service.run_training model adina gore dogru runner'a yonlenir; bilinmeyen
  model ValueError firlatir (agir egitim monkeypatch ile izole edilir).
- celery_tasks.ml_training_task ml_service.run_training'i cagirir.
- Router /ml/*/train uc noktalari isi 'ml' kuyruguna gonderir (queued zarfi).
- Broker/worker erisilemezse uc nokta 503 ile temiz degrade olur.
- GET /ml/jobs/{task_id} sonucu worker sinirindan tuketir.

Agir ML yigini (sklearn/xgboost/numpy/pandas) bu testlerde CALISTIRILMAZ;
sadece sinir/dispatch davranisi test edilir.
"""
import asyncio

import pytest
from fastapi import HTTPException


# ── ml_service: routing boundary ──────────────────────────────────

def test_run_training_routes_to_each_model(monkeypatch):
    import ml_service

    calls = {}
    for name in ("rms", "persona", "predictive_maintenance", "hk_scheduler"):
        fn_name = {
            "rms": "_train_rms",
            "persona": "_train_persona",
            "predictive_maintenance": "_train_predictive_maintenance",
            "hk_scheduler": "_train_hk_scheduler",
        }[name]

        def make_stub(n):
            def _stub(params):
                calls[n] = params
                return {"success": True, "model": n}
            return _stub

        monkeypatch.setattr(ml_service, fn_name, make_stub(name))

    assert ml_service.run_training("rms", {"historical_days": 10})["model"] == "rms"
    assert ml_service.run_training("persona", {"num_guests": 5})["model"] == "persona"
    assert ml_service.run_training("predictive_maintenance", {})["model"] == "predictive_maintenance"
    assert ml_service.run_training("hk_scheduler", {})["model"] == "hk_scheduler"
    assert calls["rms"] == {"historical_days": 10}
    assert calls["persona"] == {"num_guests": 5}


def test_run_training_all_aggregates(monkeypatch):
    import ml_service

    monkeypatch.setattr(ml_service, "_train_rms", lambda p: {"metrics": {"r2": 1}})
    monkeypatch.setattr(ml_service, "_train_persona", lambda p: {"metrics": {"acc": 1}})

    def boom(p):
        raise RuntimeError("pm trainer failed")

    monkeypatch.setattr(ml_service, "_train_predictive_maintenance", boom)
    monkeypatch.setattr(ml_service, "_train_hk_scheduler", lambda p: {"metrics": {"rmse": 1}})

    out = ml_service.run_training("all", {})
    assert out["summary"]["total_models"] == 4
    assert out["summary"]["successful"] == 3
    assert out["summary"]["failed"] == 1
    assert out["success"] is False
    assert out["results"]["rms"]["status"] == "success"
    assert out["results"]["predictive_maintenance"]["status"] == "failed"


def test_run_training_unknown_model_raises():
    import ml_service

    with pytest.raises(ValueError):
        ml_service.run_training("does_not_exist", {})


# ── celery task: dispatches to ml_service ─────────────────────────

def test_ml_training_task_invokes_ml_service(monkeypatch):
    import ml_service
    from celery_tasks import ml_training_task

    seen = {}

    def fake_run(model, params):
        seen["model"] = model
        seen["params"] = params
        return {"ok": True}

    monkeypatch.setattr(ml_service, "run_training", fake_run)

    result = ml_training_task.apply(args=["rms", {"historical_days": 1}])
    assert result.successful()
    assert result.get() == {"ok": True}
    assert seen == {"model": "rms", "params": {"historical_days": 1}}


# ── router: dispatch envelope + degrade ───────────────────────────

def test_dispatch_returns_queued_envelope(monkeypatch):
    import celery_app as celery_app_mod
    from domains.ai.router.ml_training import _dispatch_ml_training

    class _R:
        id = "fake-task-id-123"

    def fake_send_task(name, args=None, queue=None, **kw):
        assert name == "celery_tasks.ml_training_task"
        assert queue == "ml"
        assert args == ["rms", {"historical_days": 730}]
        return _R()

    monkeypatch.setattr(celery_app_mod.celery_app, "send_task", fake_send_task)

    out = _dispatch_ml_training("rms", {"historical_days": 730})
    assert out["status"] == "queued"
    assert out["queued"] is True
    assert out["task_id"] == "fake-task-id-123"
    assert out["queue"] == "ml"
    assert out["status_url"] == "/api/ml/jobs/fake-task-id-123"


def test_dispatch_degrades_to_503_when_broker_down(monkeypatch):
    import celery_app as celery_app_mod
    from domains.ai.router.ml_training import _dispatch_ml_training

    def boom(*a, **k):
        raise RuntimeError("broker unreachable")

    monkeypatch.setattr(celery_app_mod.celery_app, "send_task", boom)

    with pytest.raises(HTTPException) as ei:
        _dispatch_ml_training("rms", {})
    assert ei.value.status_code == 503


def test_job_status_consumes_result(monkeypatch):
    import celery_app as celery_app_mod
    from domains.ai.router.ml_training import get_ml_training_job

    class FakeResult:
        def __init__(self, tid):
            self.id = tid
            self.state = "SUCCESS"

        def ready(self):
            return True

        def successful(self):
            return True

        @property
        def result(self):
            return {"success": True, "metrics": {"r2": 0.9}}

    monkeypatch.setattr(celery_app_mod.celery_app, "AsyncResult", lambda tid: FakeResult(tid))

    out = asyncio.run(get_ml_training_job("abc", current_user=None, _perm=None))
    assert out["state"] == "SUCCESS"
    assert out["ready"] is True
    assert out["result"] == {"success": True, "metrics": {"r2": 0.9}}


def test_job_status_degrades_to_503(monkeypatch):
    import celery_app as celery_app_mod
    from domains.ai.router.ml_training import get_ml_training_job

    def boom(tid):
        raise RuntimeError("result backend unreachable")

    monkeypatch.setattr(celery_app_mod.celery_app, "AsyncResult", boom)

    with pytest.raises(HTTPException) as ei:
        asyncio.run(get_ml_training_job("abc", current_user=None, _perm=None))
    assert ei.value.status_code == 503
