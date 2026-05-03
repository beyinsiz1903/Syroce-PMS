"""Hotel Services Router — AGGREGATOR (R-split 2026-05-03).
Eski 1900-satırlık dosya 5 sub-module'e bölündü; URL'ler aynı (prefix /api/pms
burada uygulanır).
"""
import logging
from fastapi import APIRouter

logger = logging.getLogger("routers.hotel_services")
router = APIRouter(prefix="/api/pms", tags=["hotel-services"])

from .hotel_services_pkg.housekeeping_settings import sub_router as _hk
from .hotel_services_pkg.wakeup_lostfound import sub_router as _wk
from .hotel_services_pkg.invoices import sub_router as _inv
from .hotel_services_pkg.group_folio import sub_router as _gf
from .hotel_services_pkg.reservations_misc import sub_router as _rm

for _r in (_hk, _wk, _inv, _gf, _rm):
    router.include_router(_r)
