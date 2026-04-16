#!/bin/bash
set -e

export BACKEND_PORT=8099
export MONGO_URL="${MONGO_ATLAS_URI}"
export DB_NAME="syroce-kimlik"
export JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 32)}"
export JWT_ALGORITHM="${JWT_ALGORITHM:-HS256}"
export JWT_EXPIRE_HOURS="${JWT_EXPIRE_HOURS:-24}"
export CORS_ORIGINS="${CORS_ORIGINS:-*}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export FRONTEND_URL="${FRONTEND_URL:-http://localhost:5000}"
export QUICKID_SERVICE_KEY="${QUICKID_SERVICE_KEY:-}"

if [ -z "$MONGO_URL" ]; then
  echo "❌ MONGO_ATLAS_URI tanımlı değil!"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "✅ Quick-ID başlatılıyor: port=$BACKEND_PORT, DB=$DB_NAME"
cd "$SCRIPT_DIR/backend"
export PYTHONPATH="$SCRIPT_DIR/backend"
exec python server.py
