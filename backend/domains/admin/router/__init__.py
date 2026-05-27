"""
Aggregator package — auto-split from router.py.
Public API: from domains.admin.router import router
"""
from fastapi import APIRouter

from .compliance import router as _compliance_r
from .demo import router as _demo_r
from .hotel import router as _hotel_r
from .leads import router as _leads_r
from .ops import router as _ops_r
from .pilot_fixtures import router as _pilot_fixtures_r
from .rbac import router as _rbac_r
from .sla import router as _sla_r
from .stress import router as _stress_r
from .subscription import router as _subscription_r
from .system import router as _system_r
from .tenants import router as _tenants_r
from .users import router as _users_r

router = APIRouter()
router.include_router(_rbac_r)
router.include_router(_tenants_r)
router.include_router(_users_r)
router.include_router(_subscription_r)
router.include_router(_hotel_r)
router.include_router(_demo_r)
router.include_router(_leads_r)
router.include_router(_sla_r)
router.include_router(_system_r)
router.include_router(_compliance_r)
router.include_router(_ops_r)
router.include_router(_stress_r)
router.include_router(_pilot_fixtures_r)
