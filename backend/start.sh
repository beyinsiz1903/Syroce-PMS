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

cd "$(dirname "$0")"
exec python -m uvicorn server:app --host 0.0.0.0 --port 8000
