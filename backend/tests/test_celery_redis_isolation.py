import ast
from pathlib import Path

from redis_ssl import resolve_celery_redis_urls


def test_unrouted_tasks_use_worker_default_queue():
    source = Path(__file__).parents[1].joinpath("celery_app.py").read_text()
    tree = ast.parse(source)
    configured_queues = []

    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        for keyword in call.keywords:
            if keyword.arg == "task_default_queue":
                configured_queues.append(ast.literal_eval(keyword.value))

    assert configured_queues == ["default"]


def test_celery_uses_explicit_broker_and_result_backend_urls():
    cache, broker, result = resolve_celery_redis_urls(
        {
            "REDIS_URL": "redis://cache.internal:6379/0",
            "CELERY_BROKER_URL": "redis://broker.internal:6379/0",
            "CELERY_RESULT_BACKEND_URL": "redis://results.internal:6379/0",
        }
    )

    assert cache == "redis://cache.internal:6379/0"
    assert broker == "redis://broker.internal:6379/0"
    assert result == "redis://results.internal:6379/0"


def test_celery_result_backend_follows_explicit_broker_by_default():
    cache, broker, result = resolve_celery_redis_urls(
        {
            "REDIS_URL": "redis://cache.internal:6379/0",
            "CELERY_BROKER_URL": "redis://broker.internal:6379/0",
        }
    )

    assert cache == "redis://cache.internal:6379/0"
    assert broker == "redis://broker.internal:6379/0"
    assert result == broker


def test_celery_preserves_single_redis_fallback():
    cache, broker, result = resolve_celery_redis_urls({})

    assert cache == "redis://localhost:6379/0"
    assert broker == cache
    assert result == cache


def test_blank_overrides_do_not_disable_fallback():
    cache, broker, result = resolve_celery_redis_urls(
        {
            "REDIS_URL": "redis://cache.internal:6379/0",
            "CELERY_BROKER_URL": "  ",
            "CELERY_RESULT_BACKEND_URL": "",
        }
    )

    assert broker == cache
    assert result == cache
