"""Keep the go-live secret-leak signal actionable rather than noisy."""

from infra import production_config


def test_known_runtime_secret_is_not_reported_as_a_leak(monkeypatch):
    monkeypatch.setattr(
        production_config.os,
        "environ",
        {"QUICKID_SERVICE_KEY": "runtime-managed-secret-value-0123456789"},
    )

    result = production_config.ProductionConfigValidator().detect_leaked_secrets()

    assert result["status"] == "clean"
    assert result["suspicious_count"] == 0


def test_unknown_sensitive_runtime_variable_remains_actionable(monkeypatch):
    monkeypatch.setattr(
        production_config.os,
        "environ",
        {"UNRECOGNISED_SERVICE_TOKEN": "unexpected-secret-value-0123456789"},
    )

    result = production_config.ProductionConfigValidator().detect_leaked_secrets()

    assert result["status"] == "review_needed"
    assert result["suspicious_variables"] == [
        {
            "variable": "UNRECOGNISED_SERVICE_TOKEN",
            "reason": "Name matches sensitive pattern but not in managed config",
            "length": len("unexpected-secret-value-0123456789"),
        }
    ]
