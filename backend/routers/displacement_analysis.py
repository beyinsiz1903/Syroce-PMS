"""
Displacement Analysis Router
All endpoints under /api/displacement/
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v73 Bug DI
from modules.revenue_management.displacement_engine import DisplacementEngine

try:
    from cache_manager import cached
except ImportError:  # pragma: no cover

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


router = APIRouter(prefix="/api/displacement", tags=["displacement-analysis"])
engine = DisplacementEngine()


class DisplacementRequest(BaseModel):
    check_in: str = Field(..., description="Check-in date (YYYY-MM-DD)")
    check_out: str = Field(..., description="Check-out date (YYYY-MM-DD)")
    rooms_requested: int = Field(..., ge=1, le=500)
    proposed_rate: float = Field(..., gt=0)
    group_name: str = ""
    ancillary_per_room: float = Field(0, ge=0)
    commission_pct: float = Field(0, ge=0, le=100)


class ScenarioItem(BaseModel):
    name: str = ""
    rate: float = Field(..., gt=0)
    ancillary: float = Field(0, ge=0)
    commission: float = Field(0, ge=0, le=100)


class CompareRequest(BaseModel):
    check_in: str = Field(..., description="Check-in date (YYYY-MM-DD)")
    check_out: str = Field(..., description="Check-out date (YYYY-MM-DD)")
    rooms_requested: int = Field(..., ge=1, le=500)
    scenarios: list[ScenarioItem] = Field(..., min_length=1, max_length=5)


@router.post("/analyze")
async def analyze_displacement(
    req: DisplacementRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v101 DW
):
    try:
        result = await engine.analyze_displacement(
            tenant_id=current_user.tenant_id,
            check_in=req.check_in,
            check_out=req.check_out,
            rooms_requested=req.rooms_requested,
            proposed_rate=req.proposed_rate,
            group_name=req.group_name,
            ancillary_per_room=req.ancillary_per_room,
            commission_pct=req.commission_pct,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Analysis computation failed")


@router.get("/market-overview")
@cached(ttl=120, key_prefix="displacement_market_overview")  # Sprint 33
async def market_overview(
    days: int = Query(14, ge=1, le=60),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v73 Bug DI: displacement = stratejik
):
    return await engine.get_market_overview(current_user.tenant_id, days)


@router.post("/compare")
async def compare_scenarios(
    req: CompareRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v101 DW
):
    scenarios = [s.model_dump() for s in req.scenarios]
    return await engine.compare_scenarios(
        tenant_id=current_user.tenant_id,
        check_in=req.check_in,
        check_out=req.check_out,
        rooms_requested=req.rooms_requested,
        scenarios=scenarios,
    )


@router.post("/save")
async def save_analysis(
    req: DisplacementRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v101 DW
):
    analysis = await engine.analyze_displacement(
        tenant_id=current_user.tenant_id,
        check_in=req.check_in,
        check_out=req.check_out,
        rooms_requested=req.rooms_requested,
        proposed_rate=req.proposed_rate,
        group_name=req.group_name,
        ancillary_per_room=req.ancillary_per_room,
        commission_pct=req.commission_pct,
    )
    if "error" in analysis:
        raise HTTPException(status_code=400, detail=analysis["error"])
    result = await engine.save_analysis(current_user.tenant_id, analysis, current_user.email)
    return result


@router.get("/history")
async def get_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    return await engine.get_history(current_user.tenant_id, limit)
