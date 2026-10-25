"""Shared invalidation for reports derived from financial ledger writes."""

from __future__ import annotations

try:
    from cache_manager import cache
except ImportError:  # pragma: no cover - minimal workers/tests
    cache = None

BASIC_DASHBOARD_CACHE_PREFIX = "reports_basic_dashboard_v5"
RECEIVABLE_REPORT_CACHE_PREFIXES = ("report_company_aging_v4", "report_finance_snapshot_v4")


def invalidate_receivable_report_caches(tenant_id: str) -> None:
    if cache is None:
        return
    for prefix in RECEIVABLE_REPORT_CACHE_PREFIXES:
        cache.invalidate_tenant_cache(tenant_id, prefix, include_role_variants=True)


def invalidate_financial_report_caches(tenant_id: str) -> None:
    if cache is None:
        return
    for prefix in ("folio_revenue_by_category_v2", "posted_revenue_category_v3", BASIC_DASHBOARD_CACHE_PREFIX):
        cache.invalidate_tenant_cache(tenant_id, prefix, include_role_variants=True)
