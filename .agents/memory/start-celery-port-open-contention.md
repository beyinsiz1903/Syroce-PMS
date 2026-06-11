---
name: Celery start contends with uvicorn port-open on deploy VM
description: Why backend/start.sh defers Celery until the HTTP port is open in deployment, and what symptom that prevents.
---

# Celery startup must not race uvicorn's port-open in deployment

Starting the Celery worker+beat in the background right before `exec uvicorn`
makes `celery -A celery_app` import the entire app (+ ML via importlib) at the
same moment uvicorn imports `server.py`. On the constrained deploy VM that CPU
contention roughly TRIPLED time-to-open-port (~7s without celery -> ~21s with),
sometimes exceeding the platform port-open deadline.

**Symptom:** deploy logs show "required port 5000 never opened" -> crash/restart
loop; while no backend is listening the Replit edge proxy returns a bare
"Internal Server Error" for EVERY path (including `/`). It can self-recover once
a boot cycle wins the race, which makes it look intermittent.

**Why:** the platform kills the instance if the port isn't bound in time. The
heavy bootstrap (routers/indexes) is already deferred via
`DEFER_STARTUP_BOOTSTRAP=1`, so the only remaining pre-port work is server.py's
module import — and celery's concurrent import is what tips it over the deadline.

**How to apply:** keep Celery deferred in deployment until uvicorn has bound the
port. start.sh gates on `REPLIT_DEPLOYMENT`: in deploy it backgrounds a subshell
that polls `( exec 3<>/dev/tcp/127.0.0.1/$PORT )` until open, THEN starts
worker+beat, with a bounded fallback (`SYROCE_CELERY_PORT_WAIT`, default 120s) so
the night-audit dispatcher still runs if the port is never seen open. Dev (no
`REPLIT_DEPLOYMENT`) keeps immediate start — there is no port-open deadline
locally, so the dev workflow boot (~120s synchronous, no DEFER) is unaffected.
Verify after publish: deploy logs should show "Port 5000 open — starting Celery"
shortly after "Uvicorn running"; the 120s fallback warning would signal trouble.
This is a TIMING fix, not a crash fix — the app always booted; it just sometimes
booted too slowly to keep the port-open deadline.
