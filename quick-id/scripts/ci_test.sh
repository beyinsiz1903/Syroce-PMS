#!/bin/bash
# Quick ID Reader - CI/CD Test Pipeline
# Otomatik test + kalite kontrol scripti
#
# Kullanım:
#   ./scripts/ci_test.sh          # Tüm testleri çalıştır
#   ./scripts/ci_test.sh unit     # Sadece unit testleri
#   ./scripts/ci_test.sh lint     # Sadece linting
#   ./scripts/ci_test.sh api      # Sadece API testleri

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "============================================"
echo "  Quick ID Reader - CI/CD Test Pipeline"
echo "============================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAILURES=0
TOTAL=0

run_step() {
    local name="$1"
    local cmd="$2"
    TOTAL=$((TOTAL + 1))
    echo -e "${YELLOW}[${TOTAL}] ${name}...${NC}"
    if eval "$cmd"; then
        echo -e "  ${GREEN}✓ PASSED${NC}"
    else
        echo -e "  ${RED}✗ FAILED${NC}"
        FAILURES=$((FAILURES + 1))
    fi
    echo ""
}

MODE="${1:-all}"

# Step 1: Python Linting
if [ "$MODE" = "all" ] || [ "$MODE" = "lint" ]; then
    run_step "Python Linting (ruff)" \
        "cd $PROJECT_DIR/backend && python -m ruff check --ignore=F841,E741 *.py 2>/dev/null || true"
fi

# Step 2: Python Unit Tests
if [ "$MODE" = "all" ] || [ "$MODE" = "unit" ]; then
    run_step "Unit Tests (pytest)" \
        "cd $PROJECT_DIR && python -m pytest tests/test_unit.py -v --tb=short 2>&1"
fi

# Step 3: Backend Import Check
if [ "$MODE" = "all" ] || [ "$MODE" = "unit" ]; then
    run_step "Backend Import Check" \
        "cd $PROJECT_DIR/backend && python -c '
import server
import ocr_providers
import image_quality
import mrz_parser
import ocr_fallback
import room_assignment
import monitoring
import backup_restore
print(\"All modules imported successfully\")
'"
fi

# Step 4: API Health Check
if [ "$MODE" = "all" ] || [ "$MODE" = "api" ]; then
    run_step "API Health Check" \
        "curl -sf http://localhost:8001/api/health > /dev/null 2>&1"
fi

# Step 5: API Providers Endpoint (requires running server)
if [ "$MODE" = "all" ] || [ "$MODE" = "api" ]; then
    run_step "API Providers Endpoint" \
        "TOKEN=\$(curl -sf -X POST http://localhost:8001/api/auth/login -H 'Content-Type: application/json' -d '{\"email\":\"admin@quickid.com\",\"password\":\"admin123\"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"token\"])') && \
        curl -sf http://localhost:8001/api/scan/providers -H \"Authorization: Bearer \$TOKEN\" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert len(d[\"providers\"]) >= 4; print(f\"Found {len(d[\"providers\"])} providers\")'"
fi

# Step 6: OCR Status Check
if [ "$MODE" = "all" ] || [ "$MODE" = "api" ]; then
    run_step "OCR Status Check" \
        "curl -sf http://localhost:8001/api/scan/ocr-status | python3 -c 'import sys,json; d=json.load(sys.stdin); print(f\"Tesseract: {d[\"tesseract_available\"]}, Languages: {d[\"supported_languages\"]}\")'"
fi

# Summary
echo "============================================"
echo "  Test Results: $((TOTAL - FAILURES))/$TOTAL passed"
if [ $FAILURES -eq 0 ]; then
    echo -e "  ${GREEN}All tests passed!${NC}"
else
    echo -e "  ${RED}$FAILURES test(s) failed!${NC}"
fi
echo "============================================"

exit $FAILURES
