"""A tenant administrator's product-wide module health centre."""

from fastapi import APIRouter, Depends

from core.security import get_current_user
from models.schemas import User
from modules.pms_core.module_health_service import ModuleHealthService
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/module-health", tags=["Module Health"])
service = ModuleHealthService()


@router.get("")
async def get_module_health(
    current_user: User = Depends(get_current_user),
    _permission: None = Depends(require_op("view_system_diagnostics")),
):
    """Return installation, licence, integration, error and usage truth per module."""
    return await service.get_snapshot(current_user.tenant_id)
