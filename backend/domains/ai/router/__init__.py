"""
Aggregator package — auto-split from router.py.
Public API: from domains.ai.router import router
"""
from fastapi import APIRouter

from .core_chat import router as _core_chat_r
from .pricing_reputation import router as _pricing_reputation_r
from .concierge_social import router as _concierge_social_r
from .predictions import router as _predictions_r
from .autopilot_reco import router as _autopilot_reco_r
from .guest_intel import router as _guest_intel_r
from .ops import router as _ops_r
from .feedback import router as _feedback_r
from .ml_training import router as _ml_training_r

router = APIRouter()
router.include_router(_core_chat_r)
router.include_router(_pricing_reputation_r)
router.include_router(_concierge_social_r)
router.include_router(_predictions_r)
router.include_router(_autopilot_reco_r)
router.include_router(_guest_intel_r)
router.include_router(_ops_r)
router.include_router(_feedback_r)
router.include_router(_ml_training_r)
