"""Aggregator package for rms_router.

Auto-generated split of legacy rms_router.py into sub-modules.
External imports (`from domains.revenue.rms_router import router`) continue to work.
"""

from fastapi import APIRouter

from .comp_set import router as _comp_set_router
from .dashboards import router as _dashboards_router
from .demand_forecast import router as _demand_forecast_router
from .housekeeping_inventory import router as _housekeeping_inventory_router
from .notifications_mobile import router as _notifications_mobile_router
from .pricing_strategy import router as _pricing_strategy_router
from .revenue_reports import router as _revenue_reports_router
from .sales import router as _sales_router
from .security_mobile import router as _security_mobile_router

router = APIRouter()
router.include_router(_comp_set_router)
router.include_router(_pricing_strategy_router)
router.include_router(_demand_forecast_router)
router.include_router(_sales_router)
router.include_router(_revenue_reports_router)
router.include_router(_security_mobile_router)
router.include_router(_housekeeping_inventory_router)
router.include_router(_notifications_mobile_router)
router.include_router(_dashboards_router)

__all__ = ["router"]
