"""
Aggregator package — auto-split from analytics_router.py.
Public API: from domains.revenue.analytics_router import router
"""
from fastapi import APIRouter

from .gm import router as _gm_r
from .revenue import router as _revenue_r
from .channel_mgr import router as _channel_mgr_r
from .frontdesk import router as _frontdesk_r
from .pos_inventory import router as _pos_inventory_r
from .maintenance import router as _maintenance_r
from .housekeeping import router as _housekeeping_r
from .crm import router as _crm_r
from .approvals import router as _approvals_r
from .notifications import router as _notifications_r
from .monitoring import router as _monitoring_r
from .security import router as _security_r

router = APIRouter()
router.include_router(_gm_r)
router.include_router(_revenue_r)
router.include_router(_channel_mgr_r)
router.include_router(_frontdesk_r)
router.include_router(_pos_inventory_r)
router.include_router(_maintenance_r)
router.include_router(_housekeeping_r)
router.include_router(_crm_r)
router.include_router(_approvals_r)
router.include_router(_notifications_r)
router.include_router(_monitoring_r)
router.include_router(_security_r)
