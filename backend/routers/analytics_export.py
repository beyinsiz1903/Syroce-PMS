"""
Analytics Export Router.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from core.security import get_current_user
from models.schemas import User
import io

router = APIRouter(prefix="/api/reports/export", tags=["analytics-export"])

_service = None


def _get_service():
    global _service
    if _service is None:
        from server import db
        from modules.analytics_export.service import AnalyticsExportService
        _service = AnalyticsExportService(db)
    return _service


@router.get("/available")
async def get_available_reports(current_user: User = Depends(get_current_user)):
    svc = _get_service()
    reports = await svc.get_available_reports()
    return {"reports": reports}


class ExportReq(BaseModel):
    report_type: str
    export_format: str = "csv"
    filters: dict = {}


@router.post("/generate")
async def generate_export(req: ExportReq, current_user: User = Depends(get_current_user)):
    svc = _get_service()
    result = await svc.create_export(
        current_user.tenant_id, req.report_type, req.export_format, req.filters, current_user.id,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Export failed"))
    # return data inline (content field)
    return {
        "success": True,
        "job_id": result.get("job_id"),
        "report_type": result.get("report_type"),
        "format": result.get("format"),
        "row_count": result.get("row_count"),
        "headers": result.get("headers"),
        "rows": result.get("rows"),
    }


@router.post("/download")
async def download_export(req: ExportReq, current_user: User = Depends(get_current_user)):
    svc = _get_service()
    result = await svc.create_export(
        current_user.tenant_id, req.report_type, req.export_format, req.filters, current_user.id,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Export failed"))

    content = result.get("content", "")
    media = "text/csv"
    ext = "csv"
    if req.export_format == "json":
        media = "application/json"
        ext = "json"

    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type=media,
        headers={"Content-Disposition": f"attachment; filename={req.report_type}.{ext}"},
    )


@router.get("/history")
async def get_export_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    svc = _get_service()
    history = await svc.get_export_history(current_user.tenant_id, limit)
    return {"history": history}
