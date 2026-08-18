import asyncio
from pathlib import Path

import pytest
import yaml

from core import database

POOL_ENV_NAMES = (
    "MONGO_MAX_POOL_SIZE",
    "MONGO_MIN_POOL_SIZE",
    "MONGO_MAX_CONNECTING",
    "MONGO_MAX_IDLE_TIME_MS",
)


class FakeLoop:
    def __init__(self):
        self.closed = False

    def is_closed(self):
        return self.closed


class FakeMotorClient:
    instances = []

    def __init__(self, url, **kwargs):
        self.url = url
        self.kwargs = kwargs
        self.close_count = 0
        self.instances.append(self)

    def close(self):
        self.close_count += 1


@pytest.fixture(autouse=True)
def clear_pool_environment(monkeypatch):
    for name in POOL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    FakeMotorClient.instances.clear()


def test_pool_defaults_are_bounded():
    assert database.get_mongo_pool_options() == {
        "maxPoolSize": 20,
        "minPoolSize": 0,
        "maxConnecting": 2,
        "maxIdleTimeMS": 30000,
    }


def test_pool_environment_overrides_are_deterministic(monkeypatch):
    monkeypatch.setenv("MONGO_MAX_POOL_SIZE", "12")
    monkeypatch.setenv("MONGO_MIN_POOL_SIZE", "1")
    monkeypatch.setenv("MONGO_MAX_CONNECTING", "3")
    monkeypatch.setenv("MONGO_MAX_IDLE_TIME_MS", "15000")

    assert database.get_mongo_pool_options() == {
        "maxPoolSize": 12,
        "minPoolSize": 1,
        "maxConnecting": 3,
        "maxIdleTimeMS": 15000,
    }


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("MONGO_MAX_POOL_SIZE", "invalid", "must be an integer"),
        ("MONGO_MAX_POOL_SIZE", "0", "must be >= 1"),
        ("MONGO_MIN_POOL_SIZE", "-1", "must be >= 0"),
    ],
)
def test_invalid_pool_environment_fails_closed(monkeypatch, name, value, message):
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match=message):
        database.get_mongo_pool_options()


def test_minimum_pool_cannot_exceed_maximum(monkeypatch):
    monkeypatch.setenv("MONGO_MAX_POOL_SIZE", "4")
    monkeypatch.setenv("MONGO_MIN_POOL_SIZE", "5")

    with pytest.raises(RuntimeError, match="must not exceed"):
        database.get_mongo_pool_options()


def test_proxy_closes_all_loop_clients_once(monkeypatch):
    first_loop = FakeLoop()
    second_loop = FakeLoop()
    current_loop = first_loop
    monkeypatch.setattr(database, "AsyncIOMotorClient", FakeMotorClient)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: current_loop)
    proxy = database.LoopAwareMongoClientProxy("mongodb://example")

    first_client = proxy._get_current_client()
    current_loop = second_loop
    second_client = proxy._get_current_client()

    proxy.close()
    proxy.close()

    assert first_client.close_count == 1
    assert second_client.close_count == 1
    assert proxy._clients == {}
    with pytest.raises(RuntimeError, match="proxy is closed"):
        proxy._get_current_client()


def test_proxy_prunes_clients_owned_by_closed_event_loops(monkeypatch):
    first_loop = FakeLoop()
    second_loop = FakeLoop()
    current_loop = first_loop
    monkeypatch.setattr(database, "AsyncIOMotorClient", FakeMotorClient)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: current_loop)
    proxy = database.LoopAwareMongoClientProxy("mongodb://example")

    stale_client = proxy._get_current_client()
    first_loop.closed = True
    current_loop = second_loop
    active_client = proxy._get_current_client()

    assert stale_client.close_count == 1
    assert active_client.close_count == 0
    assert first_loop not in proxy._clients
    assert proxy._clients[second_loop] is active_client


def test_digitalocean_pool_budget_matches_runtime_contract():
    app_spec = Path(__file__).resolve().parents[2] / ".do" / "app.yaml"
    config = yaml.safe_load(app_spec.read_text(encoding="utf-8"))
    runtime_env = {item["key"]: item.get("value") for item in config["envs"]}

    assert runtime_env["MONGO_MAX_POOL_SIZE"] == "20"
    assert runtime_env["MONGO_MIN_POOL_SIZE"] == "0"
    assert runtime_env["MONGO_MAX_CONNECTING"] == "2"
    assert runtime_env["MONGO_MAX_IDLE_TIME_MS"] == "30000"
