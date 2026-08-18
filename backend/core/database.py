"""
Syroce PMS - Database Connection
Centralized MongoDB connection management.

TI-003: The `db` object is a TenantAwareDBProxy that auto-scopes
queries based on the current request's tenant context (set by middleware).

For system operations (startup, health), use `_raw_db` directly.
"""

import os
from pathlib import Path
from threading import Lock

import certifi
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms")
db_name = os.environ.get("DB_NAME", "hotel_pms")


def _read_pool_setting(name: str, default: int, *, minimum: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError:
        raise RuntimeError(f"{name} must be an integer") from None

    if value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}")
    return value


def get_mongo_pool_options() -> dict[str, int]:
    """Return the bounded per-process MongoDB connection pool budget."""
    max_pool_size = _read_pool_setting("MONGO_MAX_POOL_SIZE", 20, minimum=1)
    min_pool_size = _read_pool_setting("MONGO_MIN_POOL_SIZE", 0, minimum=0)
    max_connecting = _read_pool_setting("MONGO_MAX_CONNECTING", 2, minimum=1)
    max_idle_time_ms = _read_pool_setting("MONGO_MAX_IDLE_TIME_MS", 30000, minimum=1)

    if min_pool_size > max_pool_size:
        raise RuntimeError("MONGO_MIN_POOL_SIZE must not exceed MONGO_MAX_POOL_SIZE")

    return {
        "maxPoolSize": max_pool_size,
        "minPoolSize": min_pool_size,
        "maxConnecting": max_connecting,
        "maxIdleTimeMS": max_idle_time_ms,
    }


class LoopAwareMongoClientProxy:
    def __init__(self, url, **kwargs):
        self._url = url
        self._kwargs = kwargs
        self._clients = {}
        self._lock = Lock()
        self._closed = False

    @staticmethod
    def _unique_clients(clients):
        seen = set()
        for client_instance in clients:
            marker = id(client_instance)
            if marker in seen:
                continue
            seen.add(marker)
            yield client_instance

    def _get_current_client(self):
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        stale_clients = []
        with self._lock:
            if self._closed:
                raise RuntimeError("MongoDB client proxy is closed")

            for registered_loop, registered_client in list(self._clients.items()):
                if registered_loop is not None and registered_loop is not loop and registered_loop.is_closed():
                    stale_clients.append(registered_client)
                    del self._clients[registered_loop]

            client_instance = self._clients.get(loop)
            if client_instance is None:
                client_instance = AsyncIOMotorClient(self._url, **self._kwargs)
                self._clients[loop] = client_instance

        for stale_client in self._unique_clients(stale_clients):
            stale_client.close()
        return client_instance

    def close(self):
        """Close every loop-bound client exactly once."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            clients = list(self._clients.values())
            self._clients.clear()

        for client_instance in self._unique_clients(clients):
            client_instance.close()

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


# Bound every process and event loop to a conservative, configurable pool budget.
client = LoopAwareMongoClientProxy(
    mongo_url,
    tlsCAFile=certifi.where() if mongo_url.startswith("mongodb+srv://") else None,
    **get_mongo_pool_options(),
    serverSelectionTimeoutMS=3000,
    connectTimeoutMS=5000,
    socketTimeoutMS=20000,
    retryWrites=True,
    retryReads=True,
)

# Raw database — use ONLY for system operations (startup, health, auth bootstrap)
_raw_db = LoopAwareDatabaseProxy(client, db_name)


def get_motor_database():
    """Return the underlying AsyncIOMotorDatabase instance directly.
    Required for strict type-checking components like Motor GridFSBucket."""
    return client._get_current_client()[db_name]


# Tenant-aware proxy — auto-injects tenant_id when context is available
from core.tenant_db import TenantAwareDBProxy  # noqa: E402

db = TenantAwareDBProxy(_raw_db)
