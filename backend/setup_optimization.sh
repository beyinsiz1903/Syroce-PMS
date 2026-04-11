#!/bin/bash

echo "=================================="
echo "🚀 Hotel PMS Optimization Setup"
echo "=================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Create indexes
echo -e "${YELLOW}Step 1: Creating MongoDB Indexes...${NC}"
python3 /app/backend/db_optimization.py
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Indexes created successfully${NC}"
else
    echo "❌ Error creating indexes"
    exit 1
fi
echo ""

# Step 2: Test Redis connection
echo -e "${YELLOW}Step 2: Testing Redis Connection...${NC}"
python3 <<EOF
import redis
import os

redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
try:
    client = redis.from_url(redis_url, socket_connect_timeout=5)
    client.ping()
    print("✅ Redis connection successful")
except Exception as e:
    print(f"⚠️  Redis not available: {e}")
    print("   Cache and rate limiting will use fallback mode")
EOF
echo ""

# Step 3: Test Celery
echo -e "${YELLOW}Step 3: Testing Celery Configuration...${NC}"
cd /app/backend
celery -A celery_app inspect ping --timeout=5 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Celery workers are running${NC}"
else
    echo "⚠️  Celery workers not running"
    echo "   Background jobs will not execute"
    echo "   To start workers: celery -A celery_app worker --loglevel=info"
fi
echo ""

# Step 4: Verify system resources
echo -e "${YELLOW}Step 4: Checking System Resources...${NC}"
python3 <<EOF
import psutil

cpu = psutil.cpu_count()
mem = psutil.virtual_memory()
disk = psutil.disk_usage('/')

print(f"  CPU Cores: {cpu}")
print(f"  Total RAM: {round(mem.total / (1024**3), 2)} GB")
print(f"  Available RAM: {round(mem.available / (1024**3), 2)} GB")
print(f"  Disk Space: {round(disk.free / (1024**3), 2)} GB free")

if mem.percent > 80:
    print("  ⚠️  Warning: High memory usage")
if disk.percent > 80:
    print("  ⚠️  Warning: Low disk space")

print("✅ System resources check complete")
EOF
echo ""

echo "=================================="
echo "✨ Optimization Setup Complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Restart backend: sudo supervisorctl restart backend"
echo "2. Start Celery worker (optional): celery -A celery_app worker -l info"
echo "3. Start Celery beat (optional): celery -A celery_app beat -l info"
echo "4. Monitor with Flower (optional): celery -A celery_app flower"
echo ""
