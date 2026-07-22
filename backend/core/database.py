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

class LoopAwareMongoClientProxy:
    def __init__(self, url, **kwargs):
        self._url = url
        self._kwargs = kwargs
        self._clients = {}

    def _get_current_client(self):
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        loop_id = id(loop)
        if loop_id not in self._clients:
            self._clients[loop_id] = AsyncIOMotorClient(self._url, **self._kwargs)
        return self._clients[loop_id]

    def __getattr__(self, name):
        return getattr(self._get_current_client(), name)

    def __getitem__(self, name):
        return self._get_current_client()[name]

class LoopAwareDatabaseProxy:
    def __init__(self, client_proxy, db_name):
        self._client_proxy = client_proxy
        self._db_name = db_name

    def __getattr__(self, name):
        return getattr(self._client_proxy._get_current_client()[self._db_name], name)

    def __getitem__(self, name):
        return self._client_proxy._get_current_client()[self._db_name][name]

# Optimized connection pool for high concurrency (550 rooms, 300+ daily transactions)
client = LoopAwareMongoClientProxy(
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
_raw_db = LoopAwareDatabaseProxy(client, db_name)

# Tenant-aware proxy — auto-injects tenant_id when context is available
from core.tenant_db import TenantAwareDBProxy  # noqa: E402

db = TenantAwareDBProxy(_raw_db)
