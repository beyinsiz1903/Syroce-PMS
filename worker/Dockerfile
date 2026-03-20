# ── Celery Worker Dockerfile ───────────────────────────────────────
# Shares backend codebase, runs celery worker process
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/

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
