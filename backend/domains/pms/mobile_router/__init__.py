"""
Aggregator package — auto-split from mobile_router.py.
Public API: from domains.pms.mobile_router import router
"""
from fastapi import APIRouter

from .dashboard import router as _dashboard_r
from .frontdesk import router as _frontdesk_r
from .housekeeping import router as _housekeeping_r
from .hub import router as _hub_r
from .maintenance import router as _maintenance_r
from .notifications import router as _notifications_r
from .pos import router as _pos_r
from .search import router as _search_r

router = APIRouter()
router.include_router(_dashboard_r)
router.include_router(_notifications_r)
router.include_router(_frontdesk_r)
router.include_router(_housekeeping_r)
router.include_router(_maintenance_r)
router.include_router(_pos_r)
router.include_router(_hub_r)
router.include_router(_search_r)
