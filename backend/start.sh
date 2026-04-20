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
  mkdir -p /tmp/mongodb-data
  if ! mongod --version > /dev/null 2>&1; then
    echo "ERROR: mongod not found in PATH"
    exit 1
  fi
  if ! python -c "import pymongo; pymongo.MongoClient('localhost', 27017, serverSelectionTimeoutMS=1000).admin.command('ping')" 2>/dev/null; then
    mongod --dbpath /tmp/mongodb-data --port 27017 --fork --logpath /tmp/mongod.log
    sleep 2
  fi
fi

# Redis disabled in Replit environment to avoid port 6379 conflict with external proxy port 80.
# Backend gracefully falls back when REDIS_URL is unset.
echo "ℹ️  Redis devre dışı (Replit port çakışması). Backend fallback modunda çalışacak."

cd "$(dirname "$0")"
exec python -m uvicorn server:app --host 0.0.0.0 --port 8000
