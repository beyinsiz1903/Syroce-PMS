"""Finance routers package — aggregates all split sub-routers."""

from fastapi import APIRouter

from . import (
    accounting,
    cashiering,
    dashboards,
    folio,
    general_ledger,
    integrations,
    invoices,
    konaklama_vergisi,
    mobile,
)

router = APIRouter(prefix="/api", tags=["finance"])

for _sub in (
    integrations,
    folio,
    general_ledger,
    invoices,
    accounting,
    mobile,
    dashboards,
    cashiering,
    konaklama_vergisi,
):
    router.include_router(_sub.router)

__all__ = ["router"]
