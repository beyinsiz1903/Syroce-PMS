"""
Aggregator package — auto-split from b2b_api.py.
Public API: from routers.b2b_api import router
"""
from fastapi import APIRouter

from .api_keys import router as _api_keys_r
from .booking_engine import router as _booking_engine_r
from .connect_requests import router as _connect_requests_r
from .folio import router as _folio_r
from .groups import router as _groups_r
from .guest_journey import router as _guest_journey_r
from .guests import router as _guests_r
from .housekeeping import router as _housekeeping_r
from .identity import router as _identity_r
from .kbs import router as _kbs_r
from .lost_found import router as _lost_found_r
from .services import router as _services_r
from .wake_up import router as _wake_up_r
from .webhooks import router as _webhooks_r

router = APIRouter()
router.include_router(_api_keys_r)
router.include_router(_connect_requests_r)
router.include_router(_booking_engine_r)
router.include_router(_webhooks_r)
router.include_router(_guests_r)
router.include_router(_housekeeping_r)
router.include_router(_kbs_r)
router.include_router(_identity_r)
router.include_router(_lost_found_r)
router.include_router(_wake_up_r)
router.include_router(_guest_journey_r)
router.include_router(_services_r)
router.include_router(_groups_r)
router.include_router(_folio_r)
