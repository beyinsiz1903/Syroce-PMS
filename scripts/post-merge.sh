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

if [ -f backend/requirements.txt ]; then
  python -m pip install -q --disable-pip-version-check -r backend/requirements.txt || true
fi

if [ -f quick-id/requirements.txt ]; then
  python -m pip install -q --disable-pip-version-check -r quick-id/requirements.txt || true
fi

echo "[post-merge] Done."
