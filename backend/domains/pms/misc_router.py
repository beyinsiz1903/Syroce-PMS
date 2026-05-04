"""PMS / Operations Domain Router — AGGREGATOR (R-split 2026-05-03).
Eski 2024-satırlık dosya 8 sub-module'e bölündü. URL'ler aynı (prefix /api
burada uygulanır, sub-router'lar prefix'siz).
"""
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["PMS / Operations"])

from .misc.analytics_network import sub_router as _analytics
from .misc.companies import sub_router as _companies
from .misc.complaints import sub_router as _complaints
from .misc.hr import sub_router as _hr
from .misc.inventory_export import sub_router as _inv
from .misc.mobile import sub_router as _mobile
from .misc.payments_folio import sub_router as _payments
from .misc.properties import sub_router as _props

for _r in (_complaints, _payments, _mobile, _hr, _companies, _inv, _props, _analytics):
    router.include_router(_r)
