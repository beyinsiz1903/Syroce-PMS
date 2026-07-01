"""Monitoring endpoints."""
from fastapi import APIRouter, Depends, Query

from auth import require_admin, require_auth
from db import db
from monitoring import (
    get_ai_cost_summary, get_error_log, get_monitoring_dashboard, get_scan_statistics,
)

router = APIRouter()


@router.get("/api/monitoring/dashboard", tags=["Monitoring"], summary="Monitoring dashboard",
            description="Scan sayısı, başarı oranı, hata izleme, oda durumu")
async def monitoring_dashboard(user=Depends(require_admin)):
    return await get_monitoring_dashboard(db)


@router.get("/api/monitoring/scan-stats", tags=["Monitoring"], summary="Tarama istatistikleri")
async def scan_statistics(days: int = Query(30, ge=1, le=365), user=Depends(require_auth)):
    return await get_scan_statistics(db, days=days)


@router.get("/api/monitoring/error-log", tags=["Monitoring"], summary="Hata izleme",
            description="Son hataları ve hata türlerini listeler")
async def error_log(
    limit: int = Query(50, ge=1, le=200),
    days: int = Query(7, ge=1, le=90),
    user=Depends(require_auth),
):
    return await get_error_log(db, limit=limit, days=days)


@router.get("/api/monitoring/ai-costs", tags=["Monitoring"], summary="AI API maliyet raporu",
            description="GPT-4o API kullanım maliyeti takibi")
async def ai_cost_report(days: int = Query(30, ge=1, le=365), user=Depends(require_admin)):
    return await get_ai_cost_summary(db, days=days)
