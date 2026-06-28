"""
Aggregator package — auto-split from pos_fnb_router.py.
Public API: from domains.pms.pos_fnb_router import router
"""

from fastapi import APIRouter

from .fnb_reports import router as _fnb_reports_r
from .kitchen import router as _kitchen_r
from .marketplace import router as _marketplace_r
from .pos_core import router as _pos_core_r
from .pos_mobile import router as _pos_mobile_r

router = APIRouter()
router.include_router(_kitchen_r)
router.include_router(_marketplace_r)
router.include_router(_pos_core_r)
router.include_router(_fnb_reports_r)
router.include_router(_pos_mobile_r)
