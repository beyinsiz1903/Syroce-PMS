"""Finance routers package — aggregates all split sub-routers."""

from fastapi import APIRouter, Depends

from modules.pms_core.module_scope_service import require_module_scope

from . import (
    accounting,
    cashiering,
    dashboards,
    folio,
    integrations,
    invoices,
    konaklama_vergisi,
    mobile,
    open_banking,
)

router = APIRouter(prefix="/api", tags=["finance"])

# Keep the finance umbrella split by business module. This prevents a QA user
# with one explicit module_scope from inheriting every endpoint just because
# the routers share the historical /api finance aggregator.
for _sub in (integrations, accounting, mobile, dashboards, open_banking):
    router.include_router(
        _sub.router,
        dependencies=[Depends(require_module_scope("finance"))],
    )

for _sub in (folio, cashiering):
    router.include_router(
        _sub.router,
        dependencies=[Depends(require_module_scope("cashier"))],
    )

for _sub in (invoices, konaklama_vergisi):
    router.include_router(
        _sub.router,
        dependencies=[Depends(require_module_scope("invoice"))],
    )

__all__ = ["router"]
