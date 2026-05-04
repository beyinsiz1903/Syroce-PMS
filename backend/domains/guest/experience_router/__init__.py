"""
Aggregator package — auto-split from experience_router.py.
Public API: from domains.guest.experience_router import router
"""
from fastapi import APIRouter

from .crm_guest import router as _crm_guest_r
from .feedback import router as _feedback_r
from .guest_app import router as _guest_app_r
from .logs import router as _logs_r
from .messaging import router as _messaging_r
from .reviews import router as _reviews_r
from .rms import router as _rms_r
from .upsell import router as _upsell_r

router = APIRouter()
router.include_router(_crm_guest_r)
router.include_router(_upsell_r)
router.include_router(_messaging_r)
router.include_router(_rms_r)
router.include_router(_reviews_r)
router.include_router(_feedback_r)
router.include_router(_guest_app_r)
router.include_router(_logs_r)
