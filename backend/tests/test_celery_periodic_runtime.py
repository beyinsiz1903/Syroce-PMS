import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

import celery_tasks


class _CountCollection:
    async def count_documents(self, _query):
        return 1


class _HealthChecks:
    def __init__(self):
        self.insert_one = AsyncMock()


class _HealthDb:
    def __init__(self):
        self.command = AsyncMock(return_value={"ok": 1})
        self.health_checks = _HealthChecks()

    def __getitem__(self, _name):
        return _CountCollection()


@pytest.mark.asyncio
async def test_database_health_check_uses_motor_sync_close(monkeypatch):
    db = _HealthDb()
    client = types.SimpleNamespace(close=Mock())
    monkeypatch.setattr(celery_tasks, "get_db", lambda: (db, client))

    result = await celery_tasks._database_health_check_async()

    assert result["status"] == "healthy"
    client.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_periodic_cache_warm_uses_worker_runtime_modules(monkeypatch):
    warm_dashboard = AsyncMock()
    warm_room = AsyncMock()
    cache_module = types.ModuleType("cache_manager")
    cache_module.warm_dashboard_cache = warm_dashboard
    cache_module.warm_room_cache = warm_room
    monkeypatch.setitem(sys.modules, "cache_manager", cache_module)

    users = types.SimpleNamespace(distinct=AsyncMock(return_value=["tenant-a"]))
    db = types.SimpleNamespace(users=users)
    client = types.SimpleNamespace(close=Mock())
    monkeypatch.setattr(celery_tasks, "get_db", lambda: (db, client))

    result = await celery_tasks._warm_cache_async()

    assert result["success"] is True
    warm_dashboard.assert_awaited_once_with("tenant-a", db)
    warm_room.assert_awaited_once_with("tenant-a", db)
    client.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_periodic_cache_warm_closes_client_after_failure(monkeypatch):
    cache_module = types.ModuleType("cache_manager")
    cache_module.warm_dashboard_cache = AsyncMock(side_effect=RuntimeError("failed"))
    cache_module.warm_room_cache = AsyncMock()
    monkeypatch.setitem(sys.modules, "cache_manager", cache_module)

    users = types.SimpleNamespace(distinct=AsyncMock(return_value=["tenant-a"]))
    client = types.SimpleNamespace(close=Mock())
    monkeypatch.setattr(
        celery_tasks,
        "get_db",
        lambda: (types.SimpleNamespace(users=users), client),
    )

    result = await celery_tasks._warm_cache_async()

    assert result["success"] is False
    client.close.assert_called_once_with()


def test_worker_prefork_children_have_explicit_application_path():
    repo_root = Path(__file__).resolve().parents[2]
    dockerfile = (repo_root / "worker" / "Dockerfile").read_text()

    assert "ENV PYTHONPATH=/app" in dockerfile
    assert "COPY backend/ ." in dockerfile


def test_motor_clients_are_never_awaited_during_close():
    source = Path(celery_tasks.__file__).read_text()

    assert "await client.close()" not in source
