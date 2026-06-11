#!/bin/bash
set -e

mkdir -p /tmp/redis-data

# MongoDB: Atlas (cloud) öncelikli; yoksa local fallback
if [ -n "$MONGO_ATLAS_URI" ]; then
  export MONGO_URL="$MONGO_ATLAS_URI"
  export DB_NAME="${DB_NAME:-syroce-pms}"
  echo "✅ MongoDB: Atlas Cloud kullanılıyor (DB: $DB_NAME)"
else
  echo "⚠️  MONGO_ATLAS_URI tanımlı değil, local MongoDB başlatılıyor..."
  # KALICI dbpath: /tmp Replit restart'ta silinir, workspace kalır.
  MONGO_DBPATH="${SYROCE_MONGO_DBPATH:-$HOME/.syroce-mongodb-data}"
  mkdir -p "$MONGO_DBPATH"
  # Eski /tmp verisini bir kez taşı (varsa ve hedef boşsa)
  if [ -d /tmp/mongodb-data ] && [ -z "$(ls -A "$MONGO_DBPATH" 2>/dev/null)" ]; then
    echo "ℹ️  /tmp/mongodb-data → $MONGO_DBPATH (kalıcı konuma taşınıyor)"
    cp -a /tmp/mongodb-data/. "$MONGO_DBPATH/" 2>/dev/null || true
  fi
  if ! mongod --version > /dev/null 2>&1; then
    echo "ERROR: mongod not found in PATH"
    exit 1
  fi
  if ! python -c "import pymongo; pymongo.MongoClient('localhost', 27017, serverSelectionTimeoutMS=1000).admin.command('ping')" 2>/dev/null; then
    mongod --dbpath "$MONGO_DBPATH" --port 27017 --fork --logpath /tmp/mongod.log
    sleep 2
  fi
  export MONGO_URL="${MONGO_URL:-mongodb://localhost:27017}"
  export DB_NAME="${DB_NAME:-syroce-pms}"
fi

# Redis: yerel instance'ı 6380 portunda başlat (6379 Replit proxy ile çakışıyor).
REDIS_PORT="${SYROCE_REDIS_PORT:-6380}"
if ! redis-cli -p "$REDIS_PORT" ping > /dev/null 2>&1; then
  if command -v redis-server > /dev/null 2>&1; then
    redis-server --port "$REDIS_PORT" --daemonize yes --dir /tmp/redis-data \
      --save "" --appendonly no --maxmemory 256mb --maxmemory-policy allkeys-lru \
      --logfile /tmp/redis.log > /dev/null 2>&1 || true
    sleep 1
  fi
fi
if redis-cli -p "$REDIS_PORT" ping > /dev/null 2>&1; then
  export REDIS_URL="${REDIS_URL:-redis://localhost:$REDIS_PORT/0}"
  echo "✅ Redis: localhost:$REDIS_PORT"
else
  echo "ℹ️  Redis başlatılamadı, in-memory fallback kullanılacak."
fi

# Cron sıklık ayarları (log spam'ini azaltmak için varsayılanlar artırıldı)
export SYROCE_EXELY_PULL_INTERVAL="${SYROCE_EXELY_PULL_INTERVAL:-180}"
export SYROCE_HR_PULL_INTERVAL="${SYROCE_HR_PULL_INTERVAL:-180}"
export SYROCE_MONITOR_INTERVAL="${SYROCE_MONITOR_INTERVAL:-300}"

# Dev fallbacks for non-production startup checks (silences harmless warnings)
export CORS_ORIGINS="${CORS_ORIGINS:-*}"
export CM_MASTER_KEY_CURRENT="${CM_MASTER_KEY_CURRENT:-dev-master-key-not-for-production-use-only}"
export CM_KEY_VERSION="${CM_KEY_VERSION:-v1}"

# v42 Bug BH (defense-in-depth): enforce strict tenant isolation. Without
# this, TenantAwareDBProxy returns raw collections when tenant_context is
# missing — meaning any route that forgets `Depends(get_current_user)` and
# uses `db.<col>` directly would query across ALL tenants. Production must
# fail-closed. Override per-deploy if a specific operation needs to bypass
# (and use `get_raw_db()` explicitly).
export STRICT_TENANT_MODE="${STRICT_TENANT_MODE:-true}"

# Dev/test only: skip auth throttle so per-class pytest fixtures (which
# re-login many times) don't trip 429 cascades. Production deployments
# must NOT set this; defaults off.
export DISABLE_AUTH_THROTTLE="${DISABLE_AUTH_THROTTLE:-1}"

# F5 — Stress E2E support: tenant ids are non-secret (UUIDs), exported
# here with safe defaults so the stress endpoints can validate
# `target_tenant_id`. The destructive flag (E2E_ALLOW_DESTRUCTIVE_STRESS)
# is *intentionally* omitted from these defaults — it must be set
# externally (e.g. .local/.stress_env or Replit Secrets) for any
# stress operation to run. Fail-closed.
export E2E_STRESS_TENANT_ID="${E2E_STRESS_TENANT_ID:-23377306-a501-4232-adc8-8aea50e243c0}"
export PILOT_TENANT_ID="${PILOT_TENANT_ID:-5bad4a34-6ee3-4566-9053-741b7375a9cf}"
# Optional opt-in env file (gitignored). Used during F5/F6 stress runs.
if [ -f "$(dirname "$0")/../.local/.stress_env" ]; then
  echo "ℹ️  Loading .local/.stress_env (stress E2E opt-in)"
  set -a
  # shellcheck disable=SC1091
  . "$(dirname "$0")/../.local/.stress_env"
  set +a
fi

cd "$(dirname "$0")"
# Production deployment expects port 5000 (mapped to external 80).
# Local dev keeps 8000 (the Backend API workflow's waitForPort).
if [ -n "$REPLIT_DEPLOYMENT" ]; then
  PORT="${PORT:-5000}"
  # Replit autoscale port-open timeout (~60s) is shorter than our heavy
  # bootstrap (control plane + outbox + event bus + CM indexes). Defer
  # bootstrap to a background task so uvicorn opens the port immediately.
  export DEFER_STARTUP_BOOTSTRAP="${DEFER_STARTUP_BOOTSTRAP:-1}"
else
  PORT="${PORT:-8000}"
fi

# WeasyPrint (PDF export) ve diğer native-lib bağımlı paketler libgobject/glib,
# pango, cairo gibi paylaşımlı kütüphaneleri dlopen ile yükler. Replit dev
# shell'inde bunlar gcc/NIX_LDFLAGS fallback'i ile bulunur; ancak VM deployment
# runtime'ında C derleyici yoktur ve LD_LIBRARY_PATH otomatik doldurulmaz ->
# "OSError: cannot load library 'libgobject-2.0-0'" (/api/reports/builder/export/pdf).
# Çözüm: native lib dizinlerini NIX_LDFLAGS'taki -L yollarından türet (nix store
# hash'lerinden bağımsız, nixpkgs bump'larına dayanıklı) ve LD_LIBRARY_PATH'e ekle.
if [ -n "$NIX_LDFLAGS" ]; then
  NIX_LIB_DIRS="$(printf '%s\n' $NIX_LDFLAGS | sed -n 's/^-L//p' | paste -sd: -)"
  if [ -n "$NIX_LIB_DIRS" ]; then
    export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$NIX_LIB_DIRS"
    # Deploy loglarından doğrulanabilir olsun: türetme çalıştı mı, kaç dizin?
    echo "LD_LIBRARY_PATH NIX_LDFLAGS'tan türetildi ($(printf '%s' "$NIX_LIB_DIRS" | tr ':' '\n' | wc -l) dizin; WeasyPrint native lib çözümü)"
  fi
else
  echo "UYARI: NIX_LDFLAGS tanımsız -> LD_LIBRARY_PATH türetilemedi; WeasyPrint PDF export (libgobject) başarısız olabilir."
fi

# Use explicit .pythonlibs python to avoid PATH ambiguity in deployment.
PYTHON_BIN="${PYTHON_BIN:-/home/runner/workspace/.pythonlibs/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python"
fi

# Celery worker + beat (Task #362). Night audit now runs as a per-tenant Celery
# flow: a once-a-minute beat dispatcher (night_audit_dispatch_task) enqueues
# per-tenant hardened audits at each tenant's LOCAL configured time, executed by
# the worker (night_audit_for_tenant). In production these run as dedicated K8s /
# docker-compose worker+beat containers; on Replit (no separate worker process)
# we start them here so the audit actually fires for the pilot. Without this,
# retiring the in-process asyncio loop would mean the audit never triggers.
# Requires Redis as the broker; skipped (with a clear log) if Redis is absent.
if [ "${SYROCE_START_CELERY:-1}" = "1" ] && [ -n "$REDIS_URL" ]; then
  CELERY_CONCURRENCY="${CELERY_WORKER_CONCURRENCY:-2}"
  "$PYTHON_BIN" -m celery -A celery_app worker \
    --loglevel="${CELERY_LOGLEVEL:-info}" \
    --concurrency="$CELERY_CONCURRENCY" \
    --logfile /tmp/celery-worker.log --pidfile /tmp/celery-worker.pid &
  "$PYTHON_BIN" -m celery -A celery_app beat \
    --loglevel="${CELERY_LOGLEVEL:-info}" \
    --logfile /tmp/celery-beat.log --pidfile /tmp/celery-beat.pid \
    --schedule /tmp/celerybeat-schedule &
  echo "✅ Celery worker (concurrency=$CELERY_CONCURRENCY) + beat started (night audit dispatcher active)"
else
  echo "ℹ️  Celery başlatılmadı (Redis yok veya SYROCE_START_CELERY=0); gece denetimi tetiklenmeyecek."
fi

exec "$PYTHON_BIN" -m uvicorn server:app --host 0.0.0.0 --port "$PORT"
