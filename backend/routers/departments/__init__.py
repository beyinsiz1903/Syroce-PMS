"""
Aggregator package — auto-split from departments.py.
Public API: from routers.departments import router
"""
from fastapi import APIRouter

from .dashboards import router as _dashboards_r
from .bookings import router as _bookings_r
from .housekeeping import router as _housekeeping_r
from .rms_rates import router as _rms_rates_r
from .reports import router as _reports_r
from .pos import router as _pos_r
from .misc import router as _misc_r

router = APIRouter()
router.include_router(_dashboards_r)
router.include_router(_bookings_r)
router.include_router(_housekeeping_r)
router.include_router(_rms_rates_r)
router.include_router(_reports_r)
router.include_router(_pos_r)
router.include_router(_misc_r)
