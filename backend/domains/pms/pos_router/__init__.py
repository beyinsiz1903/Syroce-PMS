"""
Aggregator package — auto-split from pos_router.py.
Public API: from domains.pms.pos_router import router
"""
from fastapi import APIRouter

from .frontdesk import router as _frontdesk_r
from .gm_forecast import router as _gm_forecast_r
from .housekeeping import router as _housekeeping_r
from .maintenance import router as _maintenance_r
from .pos_admin import router as _pos_admin_r
from .pos_core import router as _pos_core_r
from .revenue_mobile import router as _revenue_mobile_r

router = APIRouter()
router.include_router(_pos_core_r)
router.include_router(_pos_admin_r)
router.include_router(_gm_forecast_r)
router.include_router(_frontdesk_r)
router.include_router(_revenue_mobile_r)
router.include_router(_housekeeping_r)
router.include_router(_maintenance_r)
