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
#
# Edge-front topology (deployment ONLY): a Caddy reverse proxy owns the
# EXTERNAL port (HTTP/2, HSTS, warm-up gate) while uvicorn runs on an INTERNAL
# port. NOTE: Caddy used to file_server the hashed SPA bundles (/js,/assets,
# /logos) straight from disk, but on this Reserved-VM the Caddy file_server
# stat()s files correctly yet FAILS to flush their bodies (GET -> edge 502),
# producing a white screen even with an intact on-disk build. uvicorn reads +
# delivers the same files fine, so ALL static is now reverse_proxied to uvicorn
# (see the Caddyfile rationale block below). Caddy still stamps cache/SW headers
# and owns the warm-up gate. Tradeoff: static delivery shares uvicorn's single
# worker again, so watch for event-loop starvation under heavy load. Dev is
# unchanged: uvicorn binds the port directly and Vite serves the frontend on
# its own port.
if [ -n "$REPLIT_DEPLOYMENT" ]; then
  EXTERNAL_PORT="${PORT:-5000}"
  UVICORN_PORT="${SYROCE_UVICORN_INTERNAL_PORT:-8001}"
  UVICORN_HOST="127.0.0.1"
  # Replit autoscale port-open timeout (~60s) is shorter than our heavy
  # bootstrap (control plane + outbox + event bus + CM indexes). Defer
  # bootstrap to a background task so uvicorn opens the port immediately.
  export DEFER_STARTUP_BOOTSTRAP="${DEFER_STARTUP_BOOTSTRAP:-1}"
else
  EXTERNAL_PORT="${PORT:-8000}"
  UVICORN_PORT="${PORT:-8000}"
  UVICORN_HOST="0.0.0.0"
fi
# Port that Celery's deferred-start loop (and, in deployment, the supervisor)
# waits on. ALWAYS the uvicorn port: Celery's heavy `-A celery_app` import
# must not race the uvicorn boot window. In deployment this is the INTERNAL
# port — Caddy opens the external port near-instantly, so waiting on the
# external port would defeat the boot-starvation guard.
WAIT_PORT="$UVICORN_PORT"

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

# WeasyPrint native-lib resolvability guard (PDF export). The NIX_LDFLAGS
# derivation above is enough in the dev Nix shell, but the Reserved-VM deploy
# runtime has been observed to leave glib/pango/cairo unreachable (PDF endpoints
# 503 with "cannot load library 'libgobject-2.0-0'") even though the packages
# ARE declared in replit.nix and the derivation ran. A cheap dlopen probe
# (honors LD_LIBRARY_PATH exactly like WeasyPrint's loader, ~0.5s, no slow
# render) decides whether a LAST-resort Nix-store lib-dir lookup is needed.
# NO-OP on the working path; the store glob is bounded by `timeout` so it can
# never blow the deploy port-open window. The final echo makes the next deploy
# log conclusive about PDF readiness.
_pdf_libs_ok() {
  "$PYTHON_BIN" - <<'PY' 2>/dev/null
import ctypes, sys
for _l in ("libgobject-2.0.so.0", "libpango-1.0.so.0", "libpangocairo-1.0.so.0",
           "libcairo.so.2", "libgdk_pixbuf-2.0.so.0", "libfontconfig.so.1"):
    try:
        ctypes.CDLL(_l)
    except OSError:
        sys.exit(1)
sys.exit(0)
PY
}
if ! _pdf_libs_ok; then
  echo "UYARI: WeasyPrint native kütüphaneleri LD_LIBRARY_PATH ile yüklenemedi -> Nix store fallback deneniyor (bounded)"
  _wp_lib_dirs="$(timeout 20 bash -c '
    dirs=""
    for _p in glib pango cairo gdk-pixbuf harfbuzz fontconfig freetype libffi; do
      for _d in /nix/store/*-"$_p"-[0-9]*/lib; do
        [ -d "$_d" ] && dirs="${dirs:+$dirs:}$_d"
      done
    done
    printf "%s" "$dirs"
  ' 2>/dev/null || true)"
  if [ -n "$_wp_lib_dirs" ]; then
    export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$_wp_lib_dirs"
  fi
fi
if _pdf_libs_ok; then
  echo "WeasyPrint native lib kontrolü: gobject/pango/cairo YÜKLENEBİLİYOR (native lib hazır; PDF render font/CSS/iş-kuralı hataları için ayrıca doğrulanmalı)"
else
  echo "HATA: WeasyPrint native lib kontrolü BAŞARISIZ -> PDF export (beo.pdf, reports/builder/export/pdf) 503 verecek; replit.nix glib/pango/cairo + LD_LIBRARY_PATH'i incele"
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

  _start_celery() {
    "$PYTHON_BIN" -m celery -A celery_app worker \
      --loglevel="${CELERY_LOGLEVEL:-info}" \
      --concurrency="$CELERY_CONCURRENCY" \
      --logfile /tmp/celery-worker.log --pidfile /tmp/celery-worker.pid &
    "$PYTHON_BIN" -m celery -A celery_app beat \
      --loglevel="${CELERY_LOGLEVEL:-info}" \
      --logfile /tmp/celery-beat.log --pidfile /tmp/celery-beat.pid \
      --schedule /tmp/celerybeat-schedule &
  }

  if [ -n "$REPLIT_DEPLOYMENT" ]; then
    # In deployment, uvicorn races a platform port-open deadline. Celery's
    # `-A celery_app` import pulls in the whole app (and ML modules via
    # importlib); started concurrently it starves uvicorn for CPU on a
    # constrained deploy VM, roughly tripling the time to open the port
    # (~7s -> ~21s observed in deploy logs). That occasionally exceeds the
    # deadline -> "required port 5000 never opened" -> restart loop, during
    # which the edge proxy serves a bare "Internal Server Error" because no
    # healthy backend is listening. The night-audit dispatcher runs once a
    # minute and is NOT boot-critical, so defer the workers until the port is
    # accepting connections. A bounded fallback still launches Celery if the
    # port is never observed open, so the audit cannot be silently disabled.
    # Tune the cap with SYROCE_CELERY_PORT_WAIT (seconds). (Dev has no
    # port-open deadline, so it keeps the original immediate start below.)
    CELERY_PORT_WAIT="${SYROCE_CELERY_PORT_WAIT:-120}"
    (
      _ready=0
      for _ in $(seq 1 "$CELERY_PORT_WAIT"); do
        if ( exec 3<>"/dev/tcp/127.0.0.1/$WAIT_PORT" ) 2>/dev/null; then
          _ready=1
          break
        fi
        sleep 1
      done
      if [ "$_ready" = "1" ]; then
        echo "✅ Port $WAIT_PORT open — starting Celery worker (concurrency=$CELERY_CONCURRENCY) + beat (deferred to protect port-open window)"
      else
        echo "⚠️  Port $WAIT_PORT not observed open after ${CELERY_PORT_WAIT}s — starting Celery anyway (night audit must run)"
      fi
      _start_celery
    ) &
    echo "ℹ️  Celery startup deferred until port $WAIT_PORT is open (night audit dispatcher will activate shortly after boot)"
  else
    _start_celery
    echo "✅ Celery worker (concurrency=$CELERY_CONCURRENCY) + beat started (night audit dispatcher active)"
  fi
else
  echo "ℹ️  Celery başlatılmadı (Redis yok veya SYROCE_START_CELERY=0); gece denetimi tetiklenmeyecek."
fi

# ── Server launch ───────────────────────────────────────────────
if [ -n "$REPLIT_DEPLOYMENT" ]; then
  # Deployment: Caddy static-front + uvicorn on an internal port, supervised
  # by THIS script (PID1). If EITHER process exits, kill the other and exit
  # nonzero so the platform restarts the whole deployment — this avoids the
  # "Caddy alive, API dead, but the deployment still looks healthy" failure
  # mode (which would serve static but 502 every API call).
  FRONTEND_BUILD_ABS="${FRONTEND_BUILD_DIR:-/home/runner/workspace/frontend/build}"
  CADDYFILE="${SYROCE_CADDYFILE:-/tmp/syroce.Caddyfile}"

  # 0) Fail fast on a missing/incomplete SPA build. Otherwise Caddy would
  #    happily front a live API while serving 404 for every hashed chunk
  #    (= white screen) — better to exit and let the platform surface the
  #    bad deploy than to serve a half-broken app.
  if [ ! -d "$FRONTEND_BUILD_ABS/js" ] || [ ! -d "$FRONTEND_BUILD_ABS/assets" ]; then
    echo "ERROR: SPA build missing/incomplete at $FRONTEND_BUILD_ABS (no js/ or assets/) — refusing to start static-front"
    exit 1
  fi
  # 0b) Dirs present is NOT enough. A deploy-time bundler/write hiccup can leave
  #     0-byte js chunks on disk (dirs exist, files empty), or index.html can
  #     reference an entry chunk that was never written. Caddy would then serve
  #     empty JS or 404 the entry chunk = white screen while the deploy looks
  #     healthy. Verify (a) >=1 js chunk and ZERO empty (0-byte) chunks, and
  #     (b) every /js chunk referenced by index.html exists and is non-empty.
  #     Otherwise refuse to start so the platform keeps the previous good build.
  _js_total=$(find "$FRONTEND_BUILD_ABS/js" -name '*.js' 2>/dev/null | wc -l | tr -d ' ')
  _js_empty=$(find "$FRONTEND_BUILD_ABS/js" -name '*.js' -size 0 2>/dev/null | wc -l | tr -d ' ')
  if [ "$_js_total" -eq 0 ] || [ "$_js_empty" -ne 0 ]; then
    echo "ERROR: SPA build has empty/zero js chunks at $FRONTEND_BUILD_ABS/js (total=$_js_total empty=$_js_empty) — refusing to start static-front (would serve white screen)"
    exit 1
  fi
  if [ ! -f "$FRONTEND_BUILD_ABS/index.html" ]; then
    echo "ERROR: SPA index.html missing at $FRONTEND_BUILD_ABS — refusing to start static-front"
    exit 1
  fi
  _js_refs=$(grep -oE '/js/[A-Za-z0-9._-]+\.js' "$FRONTEND_BUILD_ABS/index.html" 2>/dev/null | sort -u)
  if [ -z "$_js_refs" ]; then
    echo "ERROR: index.html references no /js chunks at $FRONTEND_BUILD_ABS — refusing to start static-front"
    exit 1
  fi
  _ref_bad=0
  while IFS= read -r _r; do
    [ -n "$_r" ] || continue
    if [ ! -s "$FRONTEND_BUILD_ABS$_r" ]; then
      echo "ERROR: index.html references missing/empty chunk: $_r"
      _ref_bad=1
    fi
  done <<EOF
$_js_refs
EOF
  if [ "$_ref_bad" -ne 0 ]; then
    echo "ERROR: SPA entry/referenced chunks missing or empty at $FRONTEND_BUILD_ABS — refusing to start static-front (would serve white screen)"
    exit 1
  fi
  echo "✅ SPA build verified: $_js_total js chunks, 0 empty, all index.html /js refs present+nonempty"

  # 1) uvicorn on the internal port. --proxy-headers trusted only from the
  #    local Caddy hop (127.0.0.1) so the forwarded client IP still drives
  #    rate limiting / audit, exactly as when uvicorn sat behind the edge.
  "$PYTHON_BIN" -m uvicorn server:app \
    --host "$UVICORN_HOST" --port "$UVICORN_PORT" \
    --proxy-headers --forwarded-allow-ips=127.0.0.1 &
  UVICORN_PID=$!

  # 2) Wait for uvicorn to ACCEPT connections before binding the external
  #    port, so the platform never observes external 502s during boot. With
  #    DEFER_STARTUP_BOOTSTRAP the socket opens in a few seconds (heavy
  #    bootstrap continues behind the warm-up gate). Bounded: if uvicorn
  #    never opens (or dies) we exit and let the platform restart rather
  #    than front a dead backend.
  UVICORN_BOOT_WAIT="${SYROCE_UVICORN_BOOT_WAIT:-55}"
  _uv_up=0
  for _ in $(seq 1 "$UVICORN_BOOT_WAIT"); do
    if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
      echo "ERROR: uvicorn exited during boot (before opening port $UVICORN_PORT)"
      exit 1
    fi
    if ( exec 3<>"/dev/tcp/127.0.0.1/$UVICORN_PORT" ) 2>/dev/null; then
      _uv_up=1
      break
    fi
    sleep 1
  done
  if [ "$_uv_up" != "1" ]; then
    echo "ERROR: uvicorn internal port $UVICORN_PORT not open after ${UVICORN_BOOT_WAIT}s — exiting for platform restart"
    kill "$UVICORN_PID" 2>/dev/null || true
    exit 1
  fi
  echo "✅ uvicorn up on ${UVICORN_HOST}:${UVICORN_PORT} — generating Caddy static-front for :${EXTERNAL_PORT}"

  # 3) Generate the Caddyfile. Caddy is the edge-facing front (HTTP/2, HSTS,
  #    warm-up gate) but it does NOT serve static files from disk: on this
  #    Reserved-VM the Caddy file_server stat()s files correctly (HEAD 200 with
  #    the right content-length + etag) yet FAILS to deliver the body for /js/*
  #    and build-root files (GET returns an edge 502 / connection reset), while
  #    delivering only the single /assets css. The build on disk is intact
  #    (rebuilt clean, 0 empty, source-hash matched) and it is NOT compression
  #    (Accept-Encoding: identity also 502s; there is no `encode` directive).
  #    uvicorn, by contrast, reads+delivers index.html from the same build dir
  #    fine through the reverse_proxy path. So every static handler below now
  #    reverse_proxies to uvicorn, whose _CachedStaticFiles mounts (/js,/assets,
  #    /logos) + SPA 404-handler serve the bytes. We KEEP Caddy's `file`
  #    matchers + header directives for route/cache policy only: @immutable_existing
  #    stamps the year-cache on assets that EXIST (a missing chunk stays a real
  #    404, never cached); @service_worker keeps no-cache + Service-Worker-Allowed;
  #    @root_static keeps its exclusions so /, *.html, /api, /ws, /graphql and the
  #    SPA fallback stay uvicorn-owned. NO `encode` anywhere — it must never wrap
  #    reverse_proxy or it would buffer streaming CSV/PDF exports and the KBS SSE
  #    text/event-stream feed. If uvicorn-proxied /js ALSO 502s after deploy, the
  #    failure is VM filesystem/snapshot data-block corruption, not the server.
  cat > "$CADDYFILE" <<CADDY
{
        auto_https off
        admin off
}

:${EXTERNAL_PORT} {
        root * ${FRONTEND_BUILD_ABS}

        @immutable_existing {
                path /js/* /assets/*
                file
        }
        header @immutable_existing Cache-Control "public, max-age=31536000, immutable"

        @logos_existing {
                path /logos/*
                file
        }
        header @logos_existing Cache-Control "public, max-age=3600"

        handle /js/* {
                reverse_proxy 127.0.0.1:${UVICORN_PORT}
        }
        handle /assets/* {
                reverse_proxy 127.0.0.1:${UVICORN_PORT}
        }
        handle /logos/* {
                reverse_proxy 127.0.0.1:${UVICORN_PORT}
        }

        # The service worker is proxied to uvicorn (its 404-handler serves the
        # root /service-worker.js file) but Caddy still STAMPS no-cache + the
        # Service-Worker-Allowed scope around the proxied response. Without
        # no-cache a previously-registered (and possibly stale/broken) SW could
        # never refetch a newer version -> browsers stayed stuck on a cached
        # broken shell (= white screen) even after the bundle itself was fixed.
        # no-cache forces the browser to revalidate the SW script every load so
        # a fixed SW self-heals. The `file` matcher is intentionally NOT used
        # here so Caddy proxies the request regardless of its broken disk read.
        @service_worker path /service-worker.js
        handle @service_worker {
                header Cache-Control "no-cache, no-store, must-revalidate"
                header Service-Worker-Allowed "/"
                reverse_proxy 127.0.0.1:${UVICORN_PORT}
        }

        # Other root-level static files (favicons, robots.txt, splash/preview
        # images) also live in the build root. They are proxied to uvicorn (its
        # SPA 404-handler serves any EXISTING root file) with a modest cache TTL
        # stamped by Caddy. "/", *.html and /api,/ws,/graphql still fall through
        # to the final handle so the no-store index.html shell, security headers
        # and SPA 404 fallback stay server-side. The `file` matcher keeps this
        # block scoped to paths that exist on disk, so SPA routes like
        # /dashboard skip it and reach uvicorn's index.html fallback.
        @root_static {
                file
                not path / *.html /api /api/* /ws* /graphql*
        }
        handle @root_static {
                header Cache-Control "public, max-age=3600"
                reverse_proxy 127.0.0.1:${UVICORN_PORT}
        }

        handle {
                reverse_proxy 127.0.0.1:${UVICORN_PORT}
        }
}
CADDY

  if ! caddy validate --config "$CADDYFILE" --adapter caddyfile; then
    echo "ERROR: Caddyfile validation failed — exiting (uvicorn will be torn down)"
    kill "$UVICORN_PID" 2>/dev/null || true
    exit 1
  fi

  # 4) Start Caddy on the external port.
  caddy run --config "$CADDYFILE" --adapter caddyfile &
  CADDY_PID=$!
  echo "✅ Caddy front on :${EXTERNAL_PORT} -> uvicorn 127.0.0.1:${UVICORN_PORT} (all static reverse-proxied to uvicorn; Caddy file_server bypassed)"

  # 5) Supervisor: forward termination, and if EITHER child exits, tear the
  #    other down and exit nonzero so the platform restarts cleanly. `|| true`
  #    keeps `set -e` from skipping the teardown when a child exits nonzero.
  _shutdown() {
    trap - TERM INT
    kill "$UVICORN_PID" "$CADDY_PID" 2>/dev/null || true
  }
  trap _shutdown TERM INT
  wait -n "$UVICORN_PID" "$CADDY_PID" || true
  echo "ERROR: a supervised process exited (uvicorn=$UVICORN_PID caddy=$CADDY_PID) — tearing down for platform restart"
  _shutdown
  exit 1
else
  # Dev: uvicorn binds the port directly (Vite serves the SPA separately).
  exec "$PYTHON_BIN" -m uvicorn server:app --host "$UVICORN_HOST" --port "$UVICORN_PORT"
fi
