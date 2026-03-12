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
- **AI / ML**: Yapay Zeka ve Makine Ogrenmesi
- **Revenue**: Gelir Yonetimi ve Fiyatlandirma
- **Channel Manager**: OTA Kanal Yonetimi
- **Sales / CRM**: Satis ve Musteri Iliskileri

### API Kimlik Dogrulama
Tum API istekleri `Authorization: Bearer <token>` header'i gerektirir.
Token almak icin `/api/auth/login` endpoint'ini kullanin.
        """,
        version="3.2.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        default_response_class=ORJSONResponse,
        openapi_tags=[
            {"name": "PMS / Dashboard", "description": "Dashboard, KPI ve Executive raporlari"},
            {"name": "PMS / Front Desk", "description": "Check-in, Check-out, Walk-in, Folio islemleri"},
            {"name": "PMS / Housekeeping", "description": "Temizlik gorevleri, oda durumu, personel performansi"},
            {"name": "PMS / Night Audit", "description": "Gece auditi, log kayitlari, OTA sync loglari"},
            {"name": "PMS / Notifications", "description": "Bildirimler, inbox, sistem uyarilari"},
            {"name": "PMS / Groups", "description": "Grup ve blok rezervasyonlari"},
            {"name": "PMS / Calendar", "description": "Takvim, rate code yonetimi, kanal miks"},
            {"name": "PMS / Approvals", "description": "Onay surecleri, butce yonetimi"},
            {"name": "PMS / POS & F&B", "description": "POS islemleri, mutfak siparisleri, F&B yonetimi"},
            {"name": "PMS / Maintenance", "description": "Bakim, onarim, IoT sensor yonetimi"},
            {"name": "PMS / Operations", "description": "Coklu tesis, HR, odeme, envanter islemleri"},
            {"name": "AI / ML", "description": "Yapay zeka chat, tahminleme, ML modelleri, sosyal medya analizi"},
            {"name": "Revenue / Pricing", "description": "Fiyatlandirma, rate planlari, gelir yonetimi, RMS"},
            {"name": "Guest / Messaging", "description": "WhatsApp, SMS, e-posta mesajlasma"},
            {"name": "Guest / Operations", "description": "Misafir profili, sadakat programi, NPS, tercihler"},
            {"name": "Channel Manager / Operations", "description": "OTA baglantilari, oda eslestirme, envanter senkronizasyonu"},
            {"name": "Sales / CRM", "description": "Satis, kurumsal musteri, lead yonetimi"},
            {"name": "Admin / Operations", "description": "Tenant yonetimi, abonelik, RBAC, sistem ayarlari"},
            {"name": "Channel Manager / Hardening", "description": "CM runtime status, drift detection, reconciliation, provider health"},
            {"name": "Workers / Hardening", "description": "Queue health, stuck tasks, failure archive, retry summary"},
            {"name": "Security / Hardening", "description": "Audit status, rate limiting, credential check, tenant guard"},
            {"name": "Observability / Runtime", "description": "Runtime metrics, alerts, system health aggregation"},
        ],
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
