---
name: Syroce deployment must be Reserved VM, not autoscale
description: Why this app deploys as VM and why the autoscale build kept failing
---

Syroce PMS must deploy as **Reserved VM**, never autoscale/static-for-the-backend.

**Why:**
- Runtime (`backend/start.sh`) starts a *local* MongoDB + *local* Redis and runs in-process background OTA-sync workers/cron (Exely/HotelRunner). That is stateful + single-instance + always-on — autoscale (stateless, ephemeral disk, scales to zero, many replicas) loses DB data, breaks Redis pub/sub auth-invalidation across instances, and kills the background workers.
- The FastAPI app *also* serves the built React SPA from `frontend/build` (see `backend/app.py`), so prod is a single service on port 5000 (mapped to external 80). No separate static frontend deploy needed.

**Autoscale build failure signature (already debugged):** the build was SIGKILLed during `yarn install` — log stops at "Resolving packages", build marked failed ~16s later with NO yarn error line. Cause was resource exhaustion on the small builder: `uv pip install` of the heavy ML stack (`xgboost` pulls ~286MB nvidia-nccl-cu12, plus scikit-learn/numpy/pandas → ~2GB venv) then fetching node_modules on top blew the build disk/mem. xgboost+sklearn are genuinely used (`backend/ml_trainers.py`) so they cannot be removed. Fix was VM (bigger persistent disk) + `--no-cache` on the uv pip install. Lockfile is fine — `yarn install --frozen-lockfile` + `yarn build` both pass locally.

**How to apply:** keep `deploymentTarget = "vm"` in `.replit`. If a future build still gets killed, the lever is a larger VM machine size (user-selected in Publishing pane) and/or trimming build disk — not "fix the lockfile". For durable production data set `MONGO_ATLAS_URI` (app prefers Atlas; local Mongo at `$HOME/.syroce-mongodb-data` is reset on each VM redeploy).
