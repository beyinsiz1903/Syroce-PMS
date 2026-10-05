"""Ensure the go-live status UI never exposes connection credentials."""

import pytest

from infra.config_activation import ConfigActivationWorkflow
from infra.production_config import ProductionConfigValidator


@pytest.mark.parametrize(
    ("variable", "value", "in_production_config"),
    [
        ("MONGO_URL", "mongodb+srv://demo_user:db-secret@cluster.example.net/hotel", True),
        ("REDIS_URL", "rediss://default:redis-secret@cache.example.net:25061/0", True),
        ("CELERY_BROKER_URL", "redis://worker:queue-secret@queue.example.net:6379/0", False),
    ],
)
def test_connection_strings_are_masked_in_every_golive_config_view(monkeypatch, variable, value, in_production_config):
    monkeypatch.setenv(variable, value)

    production_masked = ProductionConfigValidator().validate_all()["categories"]
    activation_masked = ConfigActivationWorkflow().validate_all()["categories"]

    activation_entry = next(
        item
        for category in activation_masked.values()
        for item in category["variables"]
        if item["variable"] == variable
    )

    entries = [activation_entry]
    if in_production_config:
        entries.append(
            next(
                item
                for category in production_masked.values()
                for item in category["variables"]
                if item["variable"] == variable
            )
        )

    for entry in entries:
        assert entry["masked_value"] != value
        assert "secret" not in entry["masked_value"]
