#!/bin/bash
set -e

echo "[post-merge] Starting setup..."

if [ -f frontend/package.json ]; then
  if [ -d frontend/node_modules ]; then
    cd frontend && npm install --no-audit --no-fund --silent && cd ..
  else
    cd frontend && npm install --no-audit --no-fund && cd ..
  fi
fi

if [ -f backend/requirements/all.txt ]; then
  # Phase 8.1 of requirements split (May 2026): install via the split aggregate
  # (`requirements/all.txt`) instead of the legacy `requirements.txt`. The two
  # are kept in lock-step by check_requirements_split_parity.py; switching to
  # the split aggregate is forward-compatible with Phase 8.2 (legacy deletion).
  python -m pip install -q --disable-pip-version-check -r backend/requirements/all.txt || true
fi

if [ -f quick-id/requirements.txt ]; then
  python -m pip install -q --disable-pip-version-check -r quick-id/requirements.txt || true
fi

echo "[post-merge] Done."
