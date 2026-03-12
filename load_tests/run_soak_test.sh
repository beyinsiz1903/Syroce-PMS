#!/bin/bash
# ============================================================
# Staging Soak Test Runner — Syroce Hotel PMS
# ============================================================
# Kullanım:
#   ./load_tests/run_soak_test.sh [süre] [kullanıcı_sayısı]
#   ./load_tests/run_soak_test.sh 30m 20     # 30 dakika, 20 kullanıcı
#   ./load_tests/run_soak_test.sh 12h 15     # 12 saat, 15 kullanıcı
# ============================================================

DURATION=${1:-"30m"}
USERS=${2:-"20"}
SPAWN_RATE=${3:-"2"}
HOST="http://localhost:8001"
REPORT_DIR="/app/test_reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "============================================================"
echo "  SYROCE HOTEL PMS — STAGING SOAK TEST"
echo "============================================================"
echo "  Duration:    $DURATION"
echo "  Users:       $USERS"
echo "  Spawn Rate:  $SPAWN_RATE/s"
echo "  Host:        $HOST"
echo "  Start Time:  $(date)"
echo "============================================================"

# Create report directory
mkdir -p "$REPORT_DIR"

# Start system monitor in background
echo "[1/3] Starting system monitor..."
SOAK_API_URL=$HOST SOAK_MONITOR_INTERVAL=30 python /app/load_tests/soak_monitor.py &
MONITOR_PID=$!
echo "  Monitor PID: $MONITOR_PID"

# Wait for monitor to start
sleep 2

# Run locust soak test
echo "[2/3] Starting Locust soak test..."
SOAK_USERS=$USERS SOAK_DURATION=$DURATION locust \
  -f /app/load_tests/soak_test_staging.py \
  --headless \
  --host "$HOST" \
  --csv="${REPORT_DIR}/soak_${TIMESTAMP}" \
  --html="${REPORT_DIR}/soak_${TIMESTAMP}_report.html" \
  --only-summary \
  2>&1 | tee "${REPORT_DIR}/soak_${TIMESTAMP}_stdout.log"

LOCUST_EXIT=$?

# Stop system monitor
echo "[3/3] Stopping system monitor..."
kill $MONITOR_PID 2>/dev/null
wait $MONITOR_PID 2>/dev/null

# Generate combined report
echo ""
echo "============================================================"
echo "  SOAK TEST COMPLETE"
echo "============================================================"
echo "  Exit Code:     $LOCUST_EXIT"
echo "  End Time:      $(date)"
echo "  Reports:"
echo "    - HTML:      ${REPORT_DIR}/soak_${TIMESTAMP}_report.html"
echo "    - CSV Stats: ${REPORT_DIR}/soak_${TIMESTAMP}_stats.csv"
echo "    - System:    ${REPORT_DIR}/soak_system_metrics.json"
echo "    - Final:     ${REPORT_DIR}/soak_final_report.json"
echo "    - Stdout:    ${REPORT_DIR}/soak_${TIMESTAMP}_stdout.log"
echo "============================================================"

exit $LOCUST_EXIT
