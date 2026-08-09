from scripts.safe_startup_log_diagnosis import diagnose


def test_missing_dependency_is_reported_without_raw_log() -> None:
    raw = """
    Traceback (most recent call last):
      File "/app/domains/example.py", line 42, in <module>
        import example_runtime
    ModuleNotFoundError: No module named 'example_runtime'
    guest=Sensitive Person reservation=ABC123 token=secret-value
    """

    result = diagnose(raw)

    assert result == {
        "application_frames": [{"file": "domains/example.py", "line": 42}],
        "classification": "MISSING_RUNTIME_DEPENDENCY",
        "config_key_mentions": [],
        "exception_types": ["ModuleNotFoundError"],
        "log_line_count_class": "LOW",
        "missing_modules": ["example_runtime"],
    }
    rendered = str(result)
    assert "Sensitive Person" not in rendered
    assert "ABC123" not in rendered
    assert "secret-value" not in rendered


def test_configuration_failure_reports_key_names_only() -> None:
    result = diagnose("RuntimeError: JWT_SECRET must be configured; MONGO_URL is missing")

    assert result["classification"] == "CONFIGURATION_ERROR"
    assert result["config_key_mentions"] == ["JWT_SECRET", "MONGO_URL"]
    assert result["exception_types"] == ["RuntimeError"]


def test_database_connectivity_is_classified_without_endpoint() -> None:
    result = diagnose("ServerSelectionTimeoutError while connecting to mongodb://sensitive-host")

    assert result["classification"] == "DATABASE_CONNECTIVITY"
    assert "sensitive-host" not in str(result)


def test_unknown_log_fails_closed_as_unclassified() -> None:
    result = diagnose("container stopped before health check")

    assert result["classification"] == "UNCLASSIFIED_STARTUP_FAILURE"
    assert result["missing_modules"] == []
    assert result["exception_types"] == []
