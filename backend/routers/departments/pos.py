"""
pos

Auto-split sub-router (shared imports/classes inlined).
"""

"""
Department-Specific Endpoints Router
Front Office, Housekeeping Manager, Finance, Revenue, F&B, Maintenance,
Sales, HR, IT/Security department dashboards.
Extracted from server.py for modularity.
"""
import logging

logger = logging.getLogger(__name__)
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import RolePermissionService, require_op

_role_perm = RolePermissionService()


def _enforce(role: str, op: str):
    """Bug CU (v60) — Departments/Reports/Rates/POS RBAC zorunlu."""
    _role_perm.enforce_permission(role, op)


try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
except ImportError:
    Workbook = None

try:
    from cache_manager import cache, cached
except ImportError:
    cache = None  # type: ignore

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


security = HTTPBearer()


# ==================== DEPARTMENT-SPECIFIC ENDPOINTS ====================

# rbac-allow: cache-rbac — FO dashboard operasyonel, hotel staff geneli görür (FO/HK/manager/admin)

# rbac-allow: cache-rbac — HK dashboard operasyonel, FO/HK/manager/admin görür


# NOTE: /ai/dashboard/briefing duplicate removed (R10b) — canonical implementation
# lives in `domains/ai/endpoints.py::get_daily_briefing` with @cached(ttl=300) and
# parallel `_asyncio.gather` over 4 collections.


# rbac-allow: cache-rbac — booking için müsait odalar operasyonel (FO/HK/manager)


# rbac-allow: cache-rbac — HK aktif temizlik timer'ları operasyonel (HK/FO/manager)


# rbac-allow: cache-rbac — task kanban operasyonel cross-role (FO/HK/maintenance/manager)

router = APIRouter(prefix="/api", tags=["departments"])


# ── GET /pos/auto-post-settings ──
@router.get("/pos/auto-post-settings")
@cached(ttl=600, key_prefix="pos_auto_post")  # Cache for 10 min
async def get_pos_auto_post_settings(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v84 DT: POS finansal config
):
    """
    Get POS auto-post settings for the tenant
    """
    settings = await db.pos_settings.find_one({"tenant_id": current_user.tenant_id, "type": "auto_post"})

    if not settings:
        # Default settings
        return {"mode": "realtime", "batch_interval": 15, "last_sync": None}

    return {"mode": settings.get("mode", "realtime"), "batch_interval": settings.get("batch_interval", 15), "last_sync": settings.get("last_sync")}


# ── POST /pos/auto-post-settings ──
@router.post("/pos/auto-post-settings")
async def update_pos_auto_post_settings(settings_data: dict, current_user: User = Depends(get_current_user)):
    """
    Update POS auto-post settings
    """
    _enforce(current_user.role, "manage_pos_settings")  # Bug CU
    await db.pos_settings.update_one(
        {"tenant_id": current_user.tenant_id, "type": "auto_post"},
        {
            "$set": {
                "mode": settings_data.get("mode", "realtime"),
                "batch_interval": settings_data.get("batch_interval", 15),
                "updated_at": datetime.now(UTC).isoformat(),
                "updated_by": current_user.id,
            }
        },
        upsert=True,
    )

    return {"message": "Settings updated successfully"}


# ── POST /pos/manual-sync ──
@router.post("/pos/manual-sync")
async def manual_pos_sync(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v99 DW
):
    """
    Manually trigger POS charges sync to folios
    """
    # Get all pending POS charges
    pending_charges = await db.pos_charges.find({"tenant_id": current_user.tenant_id, "posted_to_folio": False, "status": "closed"}).to_list(1000)

    posted_count = 0

    for charge in pending_charges:
        try:
            # Post to folio
            folio_charge = {
                "id": str(uuid.uuid4()),
                "folio_id": charge["folio_id"],
                "tenant_id": current_user.tenant_id,
                "description": charge.get("description", "POS Charge"),
                "charge_category": charge.get("outlet", "restaurant"),
                "date": charge["charge_date"],
                "quantity": 1,
                "unit_price": charge["total"],
                "total": charge["total"],
                "tax_amount": charge.get("tax", 0),
                "voided": False,
                "line_items": charge.get("items", []),  # Include POS line items
                "created_at": datetime.now(UTC).isoformat(),
                "created_by": current_user.id,
            }

            await db.folio_charges.insert_one(folio_charge)

            # Mark as posted
            await db.pos_charges.update_one({"_id": charge["_id"]}, {"$set": {"posted_to_folio": True, "posted_at": datetime.now(UTC).isoformat()}})

            posted_count += 1
        except Exception as e:
            logger.info(f"Failed to post POS charge {charge.get('id')}: {str(e)}")
            continue

    # Update last sync time
    await db.pos_settings.update_one({"tenant_id": current_user.tenant_id, "type": "auto_post"}, {"$set": {"last_sync": datetime.now(UTC).isoformat()}}, upsert=True)

    return {"posted_count": posted_count, "message": f"Successfully posted {posted_count} POS charges to folios"}


# ── POST /pos/manual-post ──
@router.post("/pos/manual-post")
async def manual_pos_post(post_data: dict, current_user: User = Depends(get_current_user)):
    """
    Manual post of POS charge via QR/barcode (fallback when integration fails)
    """
    _enforce(current_user.role, "post_charge")  # Bug CU
    charge_id = post_data.get("charge_id")
    folio_id = post_data.get("folio_id")
    method = post_data.get("method", "manual")

    # Get POS charge
    charge = await db.pos_charges.find_one({"id": charge_id, "tenant_id": current_user.tenant_id})

    if not charge:
        raise HTTPException(status_code=404, detail="POS charge not found")

    # Check if already posted
    if charge.get("posted_to_folio"):
        raise HTTPException(status_code=409, detail="Charge already posted to folio")

    # Post to folio
    folio_charge = {
        "id": str(uuid.uuid4()),
        "folio_id": folio_id,
        "tenant_id": current_user.tenant_id,
        "description": charge.get("description", "POS Charge - Manual Post"),
        "charge_category": charge.get("outlet", "restaurant"),
        "date": charge["charge_date"],
        "quantity": 1,
        "unit_price": charge["total"],
        "total": charge["total"],
        "tax_amount": charge.get("tax", 0),
        "voided": False,
        "line_items": charge.get("items", []),
        "manual_post": True,
        "post_method": method,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.id,
    }

    await db.folio_charges.insert_one(folio_charge)

    # Mark as posted
    await db.pos_charges.update_one({"_id": charge["_id"]}, {"$set": {"posted_to_folio": True, "posted_at": datetime.now(UTC).isoformat(), "post_method": method}})

    return {"total": charge["total"], "description": charge.get("description"), "folio_id": folio_id, "posted_at": datetime.now(UTC).isoformat()}
