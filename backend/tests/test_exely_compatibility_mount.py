from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bootstrap import router_registry

pytestmark = pytest.mark.exely_failure_stress

_MODULE = "domains.channel_manager.providers.exely.exely_webhook_router"
_ENV_KEYS = ("APP_ENV", "ENVIRONMENT", "NODE_ENV")


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize("key", _ENV_KEYS)
@pytest.mark.parametrize("value", ["production", "prod", "live", "PRODUCTION"])
def test_exely_compatibility_webhook_is_not_mountable_in_production(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    assert router_registry._should_mount_router(_MODULE) is False


def test_production_flag_wins_over_conflicting_development_flag(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert router_registry._should_mount_router(_MODULE) is False


@pytest.mark.parametrize("value", ["", "development", "test", "staging", "stress"])
def test_non_production_compatibility_test_surface_remains_available(monkeypatch, value):
    monkeypatch.setenv("APP_ENV", value)
    assert router_registry._should_mount_router(_MODULE) is True


def test_unrelated_router_is_always_mountable(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    assert router_registry._should_mount_router("domains.channel_manager.providers.exely.exely_router") is True


def test_production_registry_skips_import_and_mount(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(router_registry, "_EXTRACTED_ROUTERS", [(_MODULE, "router", ["Exely Webhooks"], None, None)])
    monkeypatch.setattr(router_registry, "_OPTIONAL_ROUTERS", [])
    safe_import = MagicMock()
    monkeypatch.setattr(router_registry, "_safe_import", safe_import)
    app = SimpleNamespace(include_router=MagicMock())

    list(router_registry._iter_register(app, None))

    safe_import.assert_not_called()
    app.include_router.assert_not_called()
