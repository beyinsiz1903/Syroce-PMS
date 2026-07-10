"""
Syroce PMS - Database Connection
Centralized MongoDB connection management.

TI-003: The `db` object is a TenantAwareDBProxy that auto-scopes
queries based on the current request's tenant context (set by middleware).

For system operations (startup, health), use `_raw_db` directly.
"""

import os
from pathlib import Path

import certifi
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms")
db_name = os.environ.get("DB_NAME", "hotel_pms")

# Optimized connection pool for high concurrency (550 rooms, 300+ daily transactions)
client = AsyncIOMotorClient(
    mongo_url,
    tlsCAFile=certifi.where() if mongo_url.startswith("mongodb+srv://") else None,
    maxPoolSize=500,
    minPoolSize=50,
    maxIdleTimeMS=45000,
    serverSelectionTimeoutMS=3000,
    connectTimeoutMS=5000,
    socketTimeoutMS=20000,
    retryWrites=True,
    retryReads=True,
    maxConnecting=10,
)

# Raw database — use ONLY for system operations (startup, health, auth bootstrap)
_raw_db = client[db_name]

# Tenant-aware proxy — auto-injects tenant_id when context is available
from core.tenant_db import TenantAwareDBProxy  # noqa: E402

db = TenantAwareDBProxy(_raw_db)
