"""
Aggregator package — auto-split from dashboard_router.py.
Public API: from domains.pms.dashboard_router import router
"""

from fastapi import APIRouter

from .dashboard_core import router as _dashboard_core_r
from .executive import router as _executive_r
from .gm import router as _gm_r

router = APIRouter()
router.include_router(_dashboard_core_r)
router.include_router(_executive_r)
router.include_router(_gm_r)
