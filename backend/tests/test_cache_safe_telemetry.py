import logging
from pathlib import Path

import pytest
import redis

from advanced_cache import AdvancedCacheManager
from cache_manager import CacheManager

SENSITIVE_KEY = "cache:tenant-sensitive-id:na_business_date:sensitive-digest"
SENSITIVE_ERROR = "connection-sensitive-marker"


class FailingRedis:
    def __init__(self, exc: Exception):
        self.exc = exc

    def get(self, _key):
        raise self.exc

    def info(self):
        raise self.exc


def _cache_manager(client) -> CacheManager:
    manager = CacheManager.__new__(CacheManager)
    manager.client = client
    manager.enabled = True
    manager.backend = "redis"
    return manager


def _operation_records(caplog, operation: str):
    return [record for record in caplog.records if getattr(record, "cache_operation", None) == operation]


def test_transient_cache_get_failure_is_redacted_and_fail_open(caplog):
    manager = _cache_manager(FailingRedis(redis.exceptions.ConnectionError(SENSITIVE_ERROR)))

    with caplog.at_level(logging.WARNING, logger="cache_manager"):
        result = manager.get(SENSITIVE_KEY)

    assert result is None
    assert SENSITIVE_KEY not in caplog.text
    assert SENSITIVE_ERROR not in caplog.text
    records = _operation_records(caplog, "get")
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].exception_type == "ConnectionError"


def test_unexpected_cache_get_failure_remains_error_but_is_redacted(caplog):
    manager = _cache_manager(FailingRedis(RuntimeError(SENSITIVE_ERROR)))

    with caplog.at_level(logging.ERROR, logger="cache_manager"):
        result = manager.get(SENSITIVE_KEY)

    assert result is None
    assert SENSITIVE_KEY not in caplog.text
    assert SENSITIVE_ERROR not in caplog.text
    records = _operation_records(caplog, "get")
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert records[0].exception_type == "RuntimeError"


def test_cache_health_response_does_not_expose_backend_message():
    manager = _cache_manager(FailingRedis(redis.exceptions.ConnectionError(SENSITIVE_ERROR)))

    result = manager.health_check()

    assert result["status"] == "unhealthy"
    assert result["exception_type"] == "ConnectionError"
    assert SENSITIVE_ERROR not in repr(result)


@pytest.mark.asyncio
async def test_advanced_cache_get_failure_is_redacted_and_fail_open(caplog):
    manager = AdvancedCacheManager(FailingRedis(redis.exceptions.ConnectionError(SENSITIVE_ERROR)))

    with caplog.at_level(logging.WARNING, logger="advanced_cache"):
        result = await manager.get(SENSITIVE_KEY)

    assert result is None
    assert SENSITIVE_KEY not in caplog.text
    assert SENSITIVE_ERROR not in caplog.text
    records = _operation_records(caplog, "get")
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].exception_type == "ConnectionError"


def test_cache_sources_do_not_restore_raw_key_or_exception_logging():
    backend_root = Path(__file__).parents[1]
    source = "\n".join((backend_root / filename).read_text() for filename in ("cache_manager.py", "advanced_cache.py"))

    for forbidden in (
        "for key {key}",
        "tenant {tenant_id}",
        "tenant_repr=",
        "{cache_key}",
        "error: {e}",
        '"error": str(',
    ):
        assert forbidden not in source
