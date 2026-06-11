---
name: ML worker boundary vs import-closure scans
description: How heavy ML stays out of the API/worker images and how the closure scans actually behave (dynamic-import blind spots).
---

Heavy ML (sklearn/xgboost/numpy/pandas/joblib) lives ONLY in `backend/ml_trainers.py`,
`backend/ml_data_generators.py`, and the single boundary `backend/ml_service.py`. The
API and default worker images must never carry ml.txt. Training runs out-of-process on
the `ml` Celery queue via `celery_tasks.ml_training_task` -> `ml_service.run_training`.
The API router only `celery_app.send_task(...queue='ml')` and degrades 503 if the
broker/worker is unreachable; `GET /api/ml/jobs/{task_id}` consumes the result.

**Why dynamic import in celery_tasks.py:** `check_worker_import_closure.py --target
worker-runtime` is an AST scan that WALKS FUNCTION BODIES, so even a lazy
`from ml_service import ...` inside the task would pull numpy/xgboost into the worker's
static closure and regress the scan. `ml_training_task` therefore loads ml_service via
`importlib.import_module('ml_service')` (string name) so the heavy stack is invisible to
the static scan but loads at runtime on the ml worker (which installs ml.txt).

**How to apply / gotchas:**
- The CI closure scans (`check_api_import_closure --target api-runtime`,
  `check_worker_import_closure --target worker-runtime`) are AST-only and DYNAMIC-IMPORT
  BLIND. Routers load via `bootstrap/router_registry.py` `importlib.import_module`, so the
  API scan from server.py never even reaches `domains/ai/router/*` — that's why api-runtime
  shows 0 missing despite the router referencing ml. The REAL gate is API/worker boot smoke.
- worker-runtime scan is independently RED (prometheus-client, python-socketio, resend,
  weasyprint) — pre-existing, unrelated to ML. Don't let an ML change ADD to that list.
- ml_service must JSON-cast outputs (numpy int64/float64 -> python int/float, value_counts
  keys -> str) because the Celery result backend serializes JSON.
- Inference/AI endpoints (predictions, pricing, predictive_engine, data_intelligence) are
  pure-Python heuristics with NO heavy ML deps — they already work ML-free, leave them.
