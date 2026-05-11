# ── Backend Production Dockerfile ──────────────────────────────────
# Multi-stage build for minimal, secure production image
# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev && \
    rm -rf /var/lib/apt/lists/*

# Phase 4 of requirements split: install via requirements/all.txt (legacy
# aggregate composer that chains base+api+worker+ml+reports+integrations+dev).
# Behavior is parity-preserving with the prior `-r requirements.txt` call;
# see docs/backend_refactors/requirements-split-plan.md and run.md.
# requirements.txt is still copied for now (legacy callers / debugging);
# Phase 8 will deprecate it once all consumers point to requirements/.
COPY requirements.txt ./
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
#   `>=1.83.2 --no-deps` because litellm declares incompatible upper
#   pins on httpx/openai we resolve via api.txt/integrations.txt directly.
# - See docs/backend_refactors/requirements-split-plan.md §4.5 and run.md
#   Phase 6.0 (API AST scan) + Phase 6.1 (this swap).
RUN python -m pip install --no-cache-dir --prefix=/install --timeout=300 --retries=5 -r requirements/api-runtime.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ && \
    PYTHONPATH=/install/lib/python3.11/site-packages python -m pip install --no-cache-dir --prefix=/install "litellm>=1.83.2" --no-deps

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

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/api/health/liveness || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "4", "--loop", "uvloop", "--http", "httptools"]
