"""Shared invalidation for reports derived from financial ledger writes."""

from __future__ import annotations

try:
    from cache_manager import cache
except ImportError:  # pragma: no cover - minimal workers/tests
    cache = None


def invalidate_financial_report_caches(tenant_id: str) -> None:
    if cache is None:
        return
    for prefix in ("folio_revenue_by_category_v2", "reports_basic_dashboard_v2"):
        cache.invalidate_tenant_cache(tenant_id, prefix)
