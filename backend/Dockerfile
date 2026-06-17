# ── Backend Production Dockerfile ──────────────────────────────────
# Multi-stage build for minimal, secure production image
# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev && \
    rm -rf /var/lib/apt/lists/*

# Phase 4 of requirements split: install via the requirements/ tree.
# Phase 8.2 (May 2026): legacy aggregate `requirements.txt` was REMOVED;
# `requirements/all.txt` is now the canonical full-surface aggregate
# composer (`-r base.txt + api.txt + worker.txt + ml.txt + reports.txt +
# integrations.txt + dev.txt`). The drift guard's parity invariant was
# retired (no aggregate to compare against); the duplicate-check half
# remains as a Phase 4.5 protection against subset hygiene regressions.
# See docs/backend_refactors/requirements-split.run.md Phases 8.1 / 8.2.
COPY requirements/ ./requirements/
# Phase 6.1 of requirements split (Pragmatic case): install the production
# backend API subset, NOT the full backend aggregate.
# - api-runtime.txt = `-r api.txt + -r integrations.txt + celery + psutil`
#   (celery/psutil added per Phase 6.0 AST scan: API-side task dispatch
#   via bootstrap/worker_registry.py + health/monitoring router need them)
# - Skips ml.txt (sklearn/xgboost/transformers — Phase 6.0 confirmed API
#   does NOT import ml stack), reports.txt, dev.txt → meaningful image
#   reduction (~38% by distribution count, ~137 vs 222 packages).
# - litellm override below stays IDENTICAL to the all.txt setup: forced
#   `>=1.84.0 --no-deps`. The >=1.84.0 floor clears CVE-2026-49468 (auth
#   bypass) and the earlier CVE-2026-35029/35030 (first fixed in 1.83.2);
#   --no-deps keeps openai at the pinned 1.99.9 (litellm>=1.83.0 would
#   otherwise force openai>=2.30.0) and avoids litellm's incompatible
#   httpx/openai upper pins we resolve via api.txt/integrations.txt directly.
# - See docs/backend_refactors/requirements-split-plan.md §4.5 and run.md
#   Phase 6.0 (API AST scan) + Phase 6.1 (this swap).
RUN python -m pip install --no-cache-dir --prefix=/install --timeout=300 --retries=5 -r requirements/api-runtime.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ && \
    PYTHONPATH=/install/lib/python3.11/site-packages python -m pip install --no-cache-dir --prefix=/install "litellm>=1.84.0" --no-deps

# Stage 2: Runtime
FROM python:3.11-slim AS runtime

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY . .

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8001

# v42 round-2: defense-in-depth tenant isolation. Production startup_check
# refuses to boot when this is not 'true' (see infra/production_config.py).
ENV STRICT_TENANT_MODE=true

# Bind to $PORT when the platform injects one (Render / Heroku-style), else
# fall back to 8001 (docker-compose, local, Replit). Shell form + `exec` keeps
# uvicorn as PID 1 so SIGTERM still triggers a graceful shutdown. Worker count
# is tunable per host plan via WEB_CONCURRENCY (default 4 = unchanged).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8001}/api/health/liveness || exit 1

CMD exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001} --workers ${WEB_CONCURRENCY:-4} --loop uvloop --http httptools
