#!/bin/bash
set -e

export BACKEND_PORT=8099
export DB_NAME="${DB_NAME:-syroce-kimlik}"
export JWT_ALGORITHM="${JWT_ALGORITHM:-HS256}"
export JWT_EXPIRE_HOURS="${JWT_EXPIRE_HOURS:-24}"
export CORS_ORIGINS="${CORS_ORIGINS:-*}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export FRONTEND_URL="${FRONTEND_URL:-http://localhost:5000}"
export QUICKID_SERVICE_KEY="${QUICKID_SERVICE_KEY:-}"

# Backend ile aynı JWT_SECRET kullan (cross-service token doğrulama için)
if [ -z "$JWT_SECRET" ]; then
  export JWT_SECRET="$(openssl rand -hex 32)"
  echo "⚠️  JWT_SECRET tanımlı değil, geçici bir tane üretildi (her restartta değişir)"
fi

# MongoDB: Atlas öncelikli, yoksa backend'in başlattığı yerel mongo'ya bağlan
if [ -n "$MONGO_ATLAS_URI" ]; then
  export MONGO_URL="$MONGO_ATLAS_URI"
  echo "✅ Quick-ID MongoDB: Atlas Cloud (DB: $DB_NAME)"
else
  # Backend yerel mongo'yu başlatmış olabilir; ona bağlan
  for i in 1 2 3 4 5; do
    if python -c "import pymongo; pymongo.MongoClient('localhost', 27017, serverSelectionTimeoutMS=1000).admin.command('ping')" 2>/dev/null; then
      break
    fi
    echo "⏳ Yerel MongoDB bekleniyor (deneme $i/5)..."
    sleep 2
  done
  if ! python -c "import pymongo; pymongo.MongoClient('localhost', 27017, serverSelectionTimeoutMS=1000).admin.command('ping')" 2>/dev/null; then
    # Kendi başına başlat
    mkdir -p /tmp/mongodb-data
    mongod --dbpath /tmp/mongodb-data --port 27017 --fork --logpath /tmp/mongod.log 2>/dev/null || true
    sleep 2
  fi
  export MONGO_URL="mongodb://localhost:27017"
  echo "✅ Quick-ID MongoDB: localhost:27017 (DB: $DB_NAME)"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "✅ Quick-ID başlatılıyor: port=$BACKEND_PORT, DB=$DB_NAME"
cd "$SCRIPT_DIR/backend"
export PYTHONPATH="$SCRIPT_DIR/backend"
exec python server.py
