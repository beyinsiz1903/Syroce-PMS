"""
Accounting domain router.
Migrated from backend/_legacy/accounting_endpoints.py (O5).
Re-exports the legacy router so existing imports continue to work.
"""
from _legacy.accounting_endpoints import api_router as router

__all__ = ["router"]
