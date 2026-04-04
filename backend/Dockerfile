# ── Backend Production Dockerfile ──────────────────────────────────
# Multi-stage build for minimal, secure production image
# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --prefix=/install --timeout=300 --retries=5 -r requirements.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ && \
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

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/api/health/liveness || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "4", "--loop", "uvloop", "--http", "httptools"]
