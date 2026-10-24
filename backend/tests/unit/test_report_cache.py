from unittest.mock import MagicMock, call

import pytest

from core import report_cache


def test_financial_report_cache_invalidation_uses_glob_safe_prefixes(monkeypatch):
    cache = MagicMock()
    monkeypatch.setattr(report_cache, "cache", cache)

    report_cache.invalidate_financial_report_caches("tenant-1")

    assert cache.invalidate_tenant_cache.call_args_list == [
        call("tenant-1", "folio_revenue_by_category_v2", include_role_variants=True),
        call("tenant-1", "posted_revenue_category_v3", include_role_variants=True),
        call("tenant-1", "reports_basic_dashboard_v5", include_role_variants=True),
    ]


def test_dashboard_and_write_invalidation_share_one_cache_namespace():
    import inspect

    from routers.reports_pkg import dashboard_lists

    source = inspect.getsource(dashboard_lists._basic_dashboard_impl)
    assert "key_prefix=BASIC_DASHBOARD_CACHE_PREFIX" in source


async def test_actual_role_aware_decorator_is_invalidated_without_touching_other_tenants(monkeypatch):
    from types import SimpleNamespace

    import cache_manager

    memory = object.__new__(cache_manager.CacheManager)
    memory.enabled = True
    memory.backend = "memory"
    memory.client = cache_manager._InMemoryTTLStore()
    monkeypatch.setattr(cache_manager, "cache", memory)
    monkeypatch.setattr(report_cache, "cache", memory)
    reads = 0

    @cache_manager.cached(key_prefix=report_cache.BASIC_DASHBOARD_CACHE_PREFIX, role_aware=True)
    async def report(current_user):
        nonlocal reads
        reads += 1
        return {"reads": reads}

    admin = SimpleNamespace(tenant_id="tenant-1", role="admin")
    manager = SimpleNamespace(tenant_id="tenant-1", role="manager")
    other = SimpleNamespace(tenant_id="tenant-2", role="admin")
    assert await report(admin) == await report(admin) == {"reads": 1}
    assert await report(manager) == {"reads": 2}
    assert await report(other) == {"reads": 3}
    memory.set("cache:tenant-1:unrelated:report", {"keep": True})
    report_cache.invalidate_financial_report_caches("tenant-1")
    assert await report(admin) == {"reads": 4}
    assert await report(manager) == {"reads": 5}
    assert await report(other) == {"reads": 3}
    assert memory.get("cache:tenant-1:unrelated:report") == {"keep": True}


@pytest.mark.parametrize("tenant,prefix", [("*", "reports"), ("tenant-1:r=admin", "reports"), ("tenant-1", "reports:*"), ("tenant-1", "*")])
def test_role_variant_invalidation_does_not_weaken_tenant_or_entity_guards(tenant, prefix):
    import cache_manager

    manager = object.__new__(cache_manager.CacheManager)
    manager.enabled = True
    manager.client = MagicMock()
    assert manager.invalidate_tenant_cache(tenant, prefix, include_role_variants=True) is False
    manager.client.keys.assert_not_called()
