#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Syroce PMS — Post-Deploy Smoke Test (Pilot Readiness)
# ──────────────────────────────────────────────────────────────────────
# 6 adımlı kontrol — deploy bittikten sonra ~1 dakikada koşar.
# Pilot Readiness checklist hard-blocker #2 (DevOps) için sahibinin
# elindeki tek-tıklık doğrulama betiği.
#
# Adımlar:
#   1) GET  /health/ready                          → 200 + status=ready
#   2) POST /api/auth/login                        → access_token döner
#   3) GET  /api/pms/bookings?limit=1              → 200 (tenant-scoped)
#   4) POST /api/pms-core/cancel  (write-check)    → opsiyonel
#   5) GET  /api/production-golive/readiness       → status & score eşiği
#   6) Sentry / observability                       → /summary üzerinden
#
# Kullanım:
#   BASE_URL=https://api.example.com \
#   ADMIN_EMAIL=admin@hotel.com ADMIN_PASSWORD=... \
#   bash deploy/smoke.sh
#
# Env değişkenleri (defaults):
#   BASE_URL              http://localhost:8000
#   ADMIN_EMAIL           demo@hotel.com
#   ADMIN_PASSWORD        demo123
#   READINESS_THRESHOLD   70           (overall_score >= bu değer → PASS)
#   READINESS_REQUIRE     READY        (status DEGRADED de OK ise: NOT_READY)
#   SKIP_WRITE_CHECKS     0            (1 → adım 4'ü atla; read-only smoke)
#   READY_RETRIES         15           (her biri 2s → 30s)
#   CURL_TIMEOUT          10           (saniye, request başına)
#
# Exit kodları:
#   0  → tüm kritik adımlar PASS
#   1  → en az bir kritik adım FAIL (deploy reddedilmeli)
#   Adım 4 (write-check) ve adım 6 (Sentry) WARN'da exit 0 kalır;
#   ENABLE_STRICT_SMOKE=1 set ile WARN da FAIL sayılır.
# ──────────────────────────────────────────────────────────────────────

set -uo pipefail

# ── Renkli log helper'ları (deploy.sh formatıyla uyumlu) ────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

ok()    { echo -e "${GREEN}[PASS]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; }
info()  { echo -e "${BLUE}[*]${NC} $1"; }
step()  { echo -e "\n${CYAN}── Step $1/6 — $2 ──${NC}"; }

# ── Konfigürasyon ──────────────────────────────────────────────────
BASE_URL="${BASE_URL:-http://localhost:8000}"
ADMIN_EMAIL="${ADMIN_EMAIL:-demo@hotel.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-demo123}"
READINESS_THRESHOLD="${READINESS_THRESHOLD:-70}"
READINESS_REQUIRE="${READINESS_REQUIRE:-READY}"  # READY | DEGRADED | NOT_READY
SKIP_WRITE_CHECKS="${SKIP_WRITE_CHECKS:-0}"
READY_RETRIES="${READY_RETRIES:-15}"
CURL_TIMEOUT="${CURL_TIMEOUT:-10}"
ENABLE_STRICT_SMOKE="${ENABLE_STRICT_SMOKE:-0}"

BASE_URL="${BASE_URL%/}"  # strip trailing slash

# Counters
PASS_COUNT=0; FAIL_COUNT=0; WARN_COUNT=0
declare -a FAILED_STEPS

# ── jq dependency check ────────────────────────────────────────────
if ! command -v jq &>/dev/null; then
    fail "jq required (apt-get install -y jq)"
    exit 1
fi
if ! command -v curl &>/dev/null; then
    fail "curl required"
    exit 1
fi

echo "════════════════════════════════════════════════════════════"
echo "  Syroce PMS — Post-Deploy Smoke"
echo "  Target  : $BASE_URL"
echo "  Admin   : $ADMIN_EMAIL"
echo "  Score≥  : $READINESS_THRESHOLD   Status= : $READINESS_REQUIRE"
echo "════════════════════════════════════════════════════════════"

# ──────────────────────────────────────────────────────────────────
# Step 1 — /health/ready
# ──────────────────────────────────────────────────────────────────
step 1 "Liveness/Readiness probe"

READY_OK=0
for attempt in $(seq 1 "$READY_RETRIES"); do
    BODY=$(curl -sS --max-time "$CURL_TIMEOUT" -o /tmp/smoke_ready.json \
                 -w "%{http_code}" "$BASE_URL/health/ready" 2>/dev/null || echo "000")
    if [ "$BODY" = "200" ]; then
        STATUS=$(jq -r '.status // ""' /tmp/smoke_ready.json 2>/dev/null || echo "")
        if [ "$STATUS" = "ready" ]; then
            ok "Ready (HTTP 200, status=ready) — attempt=$attempt"
            READY_OK=1
            PASS_COUNT=$((PASS_COUNT+1))
            break
        fi
    fi
    info "Waiting for readiness... (attempt $attempt/$READY_RETRIES, last=$BODY)"
    sleep 2
done

if [ "$READY_OK" -ne 1 ]; then
    fail "/health/ready did not return 200+status=ready within $((READY_RETRIES*2))s"
    FAIL_COUNT=$((FAIL_COUNT+1))
    FAILED_STEPS+=("1: readiness probe")
fi

# ──────────────────────────────────────────────────────────────────
# Step 2 — Admin login
# ──────────────────────────────────────────────────────────────────
step 2 "Admin login"

LOGIN_HTTP=$(curl -sS --max-time "$CURL_TIMEOUT" -o /tmp/smoke_login.json \
    -w "%{http_code}" -H "Content-Type: application/json" \
    -X POST "$BASE_URL/api/auth/login" \
    -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" 2>/dev/null || echo "000")

TOKEN=""
if [ "$LOGIN_HTTP" = "200" ]; then
    TOKEN=$(jq -r '.access_token // ""' /tmp/smoke_login.json 2>/dev/null || echo "")
fi

if [ -n "$TOKEN" ] && [ "$TOKEN" != "null" ]; then
    TOKEN_PREVIEW="${TOKEN:0:8}…${TOKEN: -4}"
    ok "Login OK (token=$TOKEN_PREVIEW)"
    PASS_COUNT=$((PASS_COUNT+1))
    AUTH_HEADER="Authorization: Bearer $TOKEN"
else
    fail "Login failed (HTTP $LOGIN_HTTP) — cannot continue authenticated checks"
    FAIL_COUNT=$((FAIL_COUNT+1))
    FAILED_STEPS+=("2: login")
    AUTH_HEADER="Authorization: Bearer __no_token__"
fi

# ──────────────────────────────────────────────────────────────────
# Step 3 — GET /api/pms/bookings?limit=1
# ──────────────────────────────────────────────────────────────────
step 3 "Bookings list (read-path + tenant scope)"

if [ -z "$TOKEN" ]; then
    warn "Skipping (no token)"
    WARN_COUNT=$((WARN_COUNT+1))
else
    BK_HTTP=$(curl -sS --max-time "$CURL_TIMEOUT" -o /tmp/smoke_bookings.json \
        -w "%{http_code}" -H "$AUTH_HEADER" \
        "$BASE_URL/api/pms/bookings?limit=1" 2>/dev/null || echo "000")
    if [ "$BK_HTTP" = "200" ]; then
        # response either {bookings:[…]} or [] — handle both
        BK_TYPE=$(jq -r 'type' /tmp/smoke_bookings.json 2>/dev/null || echo "?")
        ok "Bookings 200 (response type=$BK_TYPE)"
        PASS_COUNT=$((PASS_COUNT+1))
    else
        fail "GET /api/pms/bookings → HTTP $BK_HTTP"
        FAIL_COUNT=$((FAIL_COUNT+1))
        FAILED_STEPS+=("3: bookings list")
    fi
fi

# ──────────────────────────────────────────────────────────────────
# Step 4 — Reservation cancel write-path probe (OPTIONAL)
# ──────────────────────────────────────────────────────────────────
# Cancel a guaranteed-non-existent booking_id: we expect a deterministic
# 4xx (NOT 5xx). This proves the write router is wired without mutating
# real production data — pilot-safe.
step 4 "Cancel write-path (deterministic 4xx on bogus id)"

if [ "$SKIP_WRITE_CHECKS" = "1" ]; then
    info "Skipped (SKIP_WRITE_CHECKS=1)"
elif [ -z "$TOKEN" ]; then
    warn "Skipping (no token)"
    WARN_COUNT=$((WARN_COUNT+1))
else
    CANCEL_HTTP=$(curl -sS --max-time "$CURL_TIMEOUT" -o /tmp/smoke_cancel.json \
        -w "%{http_code}" -H "Content-Type: application/json" -H "$AUTH_HEADER" \
        -X POST "$BASE_URL/api/pms-core/cancel" \
        -d '{"booking_id":"smoke-bogus-id-do-not-exist","reason":"smoke probe"}' 2>/dev/null || echo "000")
    # Accept 400 / 404 / 422 — all confirm router reached + tenant scope rejected
    case "$CANCEL_HTTP" in
        400|404|422)
            ok "Cancel write-path reachable (HTTP $CANCEL_HTTP — bogus id rejected, expected)"
            PASS_COUNT=$((PASS_COUNT+1))
            ;;
        2*)
            fail "Cancel returned 2xx for bogus id — write-path leak (HTTP $CANCEL_HTTP)"
            FAIL_COUNT=$((FAIL_COUNT+1))
            FAILED_STEPS+=("4: cancel write-path leak")
            ;;
        5*|000)
            warn "Cancel returned $CANCEL_HTTP (5xx/network) — investigate but not pilot-blocker"
            WARN_COUNT=$((WARN_COUNT+1))
            if [ "$ENABLE_STRICT_SMOKE" = "1" ]; then
                FAIL_COUNT=$((FAIL_COUNT+1))
                FAILED_STEPS+=("4: cancel write-path 5xx (strict)")
            fi
            ;;
        *)
            warn "Cancel returned unexpected HTTP $CANCEL_HTTP"
            WARN_COUNT=$((WARN_COUNT+1))
            ;;
    esac
fi

# ──────────────────────────────────────────────────────────────────
# Step 5 — Production go-live readiness
# ──────────────────────────────────────────────────────────────────
step 5 "/api/production-golive/readiness"

if [ -z "$TOKEN" ]; then
    warn "Skipping (no token)"
    WARN_COUNT=$((WARN_COUNT+1))
else
    R_HTTP=$(curl -sS --max-time "$CURL_TIMEOUT" -o /tmp/smoke_readiness.json \
        -w "%{http_code}" -H "$AUTH_HEADER" \
        "$BASE_URL/api/production-golive/readiness" 2>/dev/null || echo "000")
    if [ "$R_HTTP" = "200" ]; then
        # Real shape (May 2026): {readiness: "READY|DEGRADED|NOT_READY",
        # readiness_score: 0-100, checks: {<name>: {status, ...}}, ...}
        # Backward-compat fallbacks kept for safety.
        R_STATUS=$(jq -r '(.readiness // .status // .overall_status // "?")' /tmp/smoke_readiness.json 2>/dev/null || echo "?")
        R_SCORE=$(jq -r '((.readiness_score // .overall_score // .score // 0) | floor)' /tmp/smoke_readiness.json 2>/dev/null || echo "0")
        info "status=$R_STATUS  score=$R_SCORE  threshold=$READINESS_THRESHOLD"

        # Status gate
        STATUS_OK=0
        case "$READINESS_REQUIRE" in
            READY)        [ "$R_STATUS" = "READY" ] && STATUS_OK=1 ;;
            DEGRADED)     [ "$R_STATUS" = "READY" ] || [ "$R_STATUS" = "DEGRADED" ] && STATUS_OK=1 ;;
            NOT_READY|*)  STATUS_OK=1 ;;  # accept anything
        esac

        # Score gate
        SCORE_OK=0
        if [ "$R_SCORE" -ge "$READINESS_THRESHOLD" ] 2>/dev/null; then SCORE_OK=1; fi

        if [ "$STATUS_OK" = "1" ] && [ "$SCORE_OK" = "1" ]; then
            ok "Readiness PASS (status=$R_STATUS score=$R_SCORE ≥ $READINESS_THRESHOLD)"
            PASS_COUNT=$((PASS_COUNT+1))
        else
            fail "Readiness FAIL — status=$R_STATUS (need $READINESS_REQUIRE) score=$R_SCORE (need ≥$READINESS_THRESHOLD)"
            FAIL_COUNT=$((FAIL_COUNT+1))
            FAILED_STEPS+=("5: readiness gate")
            # Show top 3 failed sub-checks if structure exposes them
            # Surface only genuinely-bad sub-checks. Treat these as PASS-equivalent:
            # PASS, ok, healthy, connected, active, ready, configured, enabled.
            jq -r '
                (.checks // .sub_checks // {})
                | to_entries
                | map(select(
                    (.value.status // "?")
                    | ascii_downcase
                    | IN("pass","ok","healthy","connected","active","ready","configured","enabled","up") | not
                  ))
                | .[0:5]
                | .[] | "    - \(.key): \(.value.status // "?")"
            ' /tmp/smoke_readiness.json 2>/dev/null || true
        fi
    else
        fail "/api/production-golive/readiness → HTTP $R_HTTP"
        FAIL_COUNT=$((FAIL_COUNT+1))
        FAILED_STEPS+=("5: readiness endpoint")
    fi
fi

# ──────────────────────────────────────────────────────────────────
# Step 6 — Sentry / observability sanity
# ──────────────────────────────────────────────────────────────────
# Use the go-live summary endpoint (cached 60s) and inspect
# observability.sentry.* — non-blocking by default since Sentry being
# inactive is a config issue, not a runtime failure.
step 6 "Sentry / observability sanity"

if [ -z "$TOKEN" ]; then
    warn "Skipping (no token)"
    WARN_COUNT=$((WARN_COUNT+1))
else
    S_HTTP=$(curl -sS --max-time "$CURL_TIMEOUT" -o /tmp/smoke_summary.json \
        -w "%{http_code}" -H "$AUTH_HEADER" \
        "$BASE_URL/api/production-golive/summary" 2>/dev/null || echo "000")
    if [ "$S_HTTP" = "200" ]; then
        SENTRY_ACTIVE=$(jq -r '
            (.observability.sentry.active
             // .observability.sentry.status
             // .observability.sentry.enabled
             // false)' /tmp/smoke_summary.json 2>/dev/null || echo "false")
        if [ "$SENTRY_ACTIVE" = "true" ] || [ "$SENTRY_ACTIVE" = "active" ] || [ "$SENTRY_ACTIVE" = "ok" ]; then
            ok "Sentry active per /summary"
            PASS_COUNT=$((PASS_COUNT+1))
        else
            warn "Sentry not reported active (value=$SENTRY_ACTIVE) — verify SENTRY_DSN env in Replit Secrets"
            WARN_COUNT=$((WARN_COUNT+1))
            if [ "$ENABLE_STRICT_SMOKE" = "1" ]; then
                FAIL_COUNT=$((FAIL_COUNT+1))
                FAILED_STEPS+=("6: sentry inactive (strict)")
            fi
        fi
    else
        warn "/summary returned HTTP $S_HTTP — manual Sentry check required (https://sentry.io)"
        WARN_COUNT=$((WARN_COUNT+1))
    fi
fi

# ──────────────────────────────────────────────────────────────────
# Verdict
# ──────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Smoke Verdict"
echo "════════════════════════════════════════════════════════════"
echo -e "  ${GREEN}PASS${NC}: $PASS_COUNT   ${YELLOW}WARN${NC}: $WARN_COUNT   ${RED}FAIL${NC}: $FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
    echo ""
    fail "Smoke FAILED — failed steps:"
    for s in "${FAILED_STEPS[@]}"; do echo "    • $s"; done
    echo ""
    echo "Deploy MUST be rolled back or pilot postponed."
    exit 1
fi

if [ "$WARN_COUNT" -gt 0 ]; then
    echo ""
    warn "Smoke PASSED with warnings ($WARN_COUNT) — review above before pilot go-live."
    echo "Set ENABLE_STRICT_SMOKE=1 to treat warnings as failures."
fi

ok "Smoke PASSED — deploy is pilot-ready."
exit 0
