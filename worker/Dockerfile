# ── Celery Worker Dockerfile ───────────────────────────────────────
# Shares backend codebase, runs celery worker process
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev && \
    rm -rf /var/lib/apt/lists/*

# Phase 5 of requirements split (Pragmatic case): install the production
# worker subset, NOT the full backend aggregate.
# - worker-runtime.txt = `-r worker.txt` + fastapi + starlette
#   (worker.txt itself = `-r base.txt` + celery/scheduler/flower core)
# - fastapi/starlette are needed because integrations/booking.py is a hybrid
#   FastAPI router + worker helper imported by celery_tasks.py.
# - See docs/backend_refactors/requirements-split-plan.md §4.4 and run.md
#   Phase 4.6 (worker AST scan) + Phase 5 (this swap).
# - backend/requirements.txt is still copied so legacy callers / debugging
#   commands inside the container can reference it; Phase 8 will drop it.
COPY backend/requirements.txt .
COPY backend/requirements/ ./requirements/
RUN pip install --no-cache-dir --prefix=/install --timeout=300 --retries=5 -r requirements/worker-runtime.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/

FROM python:3.11-slim AS runtime

RUN groupadd -r celeryuser && useradd -r -g celeryuser -d /app -s /sbin/nologin celeryuser

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY backend/ .

RUN chown -R celeryuser:celeryuser /app

USER celeryuser

HEALTHCHECK --interval=60s --timeout=10s --start-period=15s --retries=3 \
    CMD celery -A celery_app inspect ping --timeout 5 || exit 1

CMD ["celery", "-A", "celery_app", "worker", "--loglevel=info", "--concurrency=4", "-Q", "default,ml,analytics,messaging,pipeline,backup"]
