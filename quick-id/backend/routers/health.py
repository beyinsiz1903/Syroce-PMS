"""Health & rate-limit info endpoints."""
from fastapi import APIRouter

from db import client

router = APIRouter()


async def _health_payload():
    """Ortak sağlık çıktısı — root /health ve /api/health için aynı yanıt."""
    db_status = "healthy"
    try:
        await client.admin.command("ping")
    except Exception:
        db_status = "unhealthy"
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "service": "Quick ID Reader",
        "version": "3.1.0",
        "database": db_status,
    }


@router.get("/", tags=["Sağlık"], summary="Servis kök bilgisi", include_in_schema=False)
async def root():
    """Servis kök sayfası — yön bulmak için kısa bilgi."""
    return {
        "service": "Quick ID Reader",
        "version": "3.1.0",
        "docs": "/api/docs",
        "health": "/health",
        "health_api": "/api/health",
    }


@router.get("/health", tags=["Sağlık"], summary="Sağlık kontrolü (kısa yol)", include_in_schema=False)
async def health_short():
    """k8s/load-balancer probe'ları için kısa /health yolu."""
    return await _health_payload()


@router.get("/api/health", tags=["Sağlık"], summary="Sistem sağlık kontrolü")
async def health():
    return await _health_payload()


@router.get("/api/rate-limits", tags=["Sağlık"], summary="Rate limit bilgileri")
async def get_rate_limits():
    """Return rate limit configuration for the frontend"""
    return {
        "limits": {
            "scan": {"limit": 15, "window": "dakika", "description": "Kimlik tarama (AI)"},
            "login": {"limit": 5, "window": "dakika", "description": "Giriş denemesi"},
            "guest_create": {"limit": 30, "window": "dakika", "description": "Misafir oluşturma"},
        },
        "note": "Limitler kullanıcı bazında uygulanır. Her kullanıcının kendi limiti vardır.",
    }
