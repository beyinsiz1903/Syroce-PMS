"""REPORTS Router — AGGREGATOR (R-split 2026-05-03).
Eski 1887-satırlık dosya 4 sub-module'e bölündü. URL'ler aynı.
"""
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["reports"])

from .reports_pkg.dashboard_lists import sub_router as _dl
from .reports_pkg.flash_email import sub_router as _fe
from .reports_pkg.night_audit import sub_router as _na
from .reports_pkg.standard_reports import sub_router as _sr

for _r in (_fe, _sr, _dl, _na):
    router.include_router(_r)
