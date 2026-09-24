from unittest.mock import MagicMock, call

from core import report_cache


def test_financial_report_cache_invalidation_uses_glob_safe_prefixes(monkeypatch):
    cache = MagicMock()
    monkeypatch.setattr(report_cache, "cache", cache)

    report_cache.invalidate_financial_report_caches("tenant-1")

    assert cache.invalidate_tenant_cache.call_args_list == [
        call("tenant-1", "folio_revenue_by_category_v2"),
        call("tenant-1", "reports_basic_dashboard_v2"),
    ]
