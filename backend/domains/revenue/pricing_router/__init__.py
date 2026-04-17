"""Aggregator package for pricing_router.

Auto-generated split of legacy pricing_router.py into sub-modules.
External imports (`from domains.revenue.pricing_router import router`) continue to work.
"""
from fastapi import APIRouter

from .rms import router as _rms_router
from .rates import router as _rates_router
from .contracted_rates import router as _contracted_rates_router
from .ai_pricing import router as _ai_pricing_router
from .revenue_mobile import router as _revenue_mobile_router
from .revenue_analysis import router as _revenue_analysis_router
from .anomaly import router as _anomaly_router

router = APIRouter()
router.include_router(_rms_router)
router.include_router(_rates_router)
router.include_router(_contracted_rates_router)
router.include_router(_ai_pricing_router)
router.include_router(_revenue_mobile_router)
router.include_router(_revenue_analysis_router)
router.include_router(_anomaly_router)

__all__ = ['router']
