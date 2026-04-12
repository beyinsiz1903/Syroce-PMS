#!/bin/bash
set -e

mkdir -p /tmp/mongodb-data /tmp/redis-data

if ! mongod --version > /dev/null 2>&1; then
  echo "ERROR: mongod not found in PATH"
  exit 1
fi

if ! redis-server --version > /dev/null 2>&1; then
  echo "ERROR: redis-server not found in PATH"
  exit 1
fi

if ! python -c "import pymongo; pymongo.MongoClient('localhost', 27017, serverSelectionTimeoutMS=1000).admin.command('ping')" 2>/dev/null; then
  echo "Starting MongoDB..."
  mongod --dbpath /tmp/mongodb-data --port 27017 --fork --logpath /tmp/mongod.log
  sleep 2
fi

if ! redis-cli -p 6379 ping > /dev/null 2>&1; then
  echo "Starting Redis..."
  redis-server --daemonize yes --dir /tmp/redis-data --port 6379
  sleep 1
fi

cd "$(dirname "$0")"
exec python -m uvicorn server:app --host 0.0.0.0 --port 8000
