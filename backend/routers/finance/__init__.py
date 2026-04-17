"""Finance routers package — aggregates all split sub-routers."""
from fastapi import APIRouter

from . import integrations, folio, invoices, accounting, mobile, dashboards, cashiering

router = APIRouter(prefix="/api", tags=["finance"])

for _sub in (integrations, folio, invoices, accounting, mobile, dashboards, cashiering):
    router.include_router(_sub.router)

__all__ = ["router"]
