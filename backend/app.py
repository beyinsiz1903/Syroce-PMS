"""
app.py — FastAPI Application Factory

Creates the FastAPI instance and mounts static files.
This is the single source of truth for the application object.
server.py imports from here and orchestrates bootstrap.
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import ORJSONResponse, FileResponse


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""

    application = FastAPI(
        title="RoomOps Platform - Otel Yonetim Sistemi",
        description="""
## RoomOps PMS - Kapsamli Otel Yonetim Platformu

### Temel Moduller
- **PMS**: Oda, Rezervasyon, Check-in/Check-out Yonetimi
- **Housekeeping**: Temizlik ve Oda Bakim Yonetimi
- **Finance**: Fatura, Folio, Muhasebe
- **Reports**: Raporlama ve Analitik

### API Kimlik Dogrulama
Tum API istekleri `Authorization: Bearer <token>` header'i gerektirir.
Token almak icin `/api/auth/login` endpoint'ini kullanin.
        """,
        version="3.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        default_response_class=ORJSONResponse,
    )

    # ── Deployment health check (lightweight, no DB/Redis) ──────────
    @application.get("/health", include_in_schema=False)
    @application.get("/health/", include_in_schema=False)
    async def deployment_health_check():
        return {"status": "healthy"}

    # ── Screenshots download ────────────────────────────────────────
    @application.get("/api/download/screenshots", include_in_schema=False)
    async def download_screenshots_zip():
        zip_path = Path("/app/backend/Syroce_PMS_AppStore_Screenshots.zip")
        if not zip_path.exists():
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Screenshots ZIP not found")
        return FileResponse(
            path=str(zip_path),
            filename="Syroce_PMS_AppStore_Screenshots.zip",
            media_type="application/zip",
        )

    # ── Static file serving (uploads) ───────────────────────────────
    upload_dir = Path(os.environ.get("UPLOAD_DIR", "/app/backend/uploads"))
    upload_dir.mkdir(parents=True, exist_ok=True)
    application.mount("/api/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")

    return application
