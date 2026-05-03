"""
app.py — FastAPI Application Factory

Creates the FastAPI instance and mounts static files.
This is the single source of truth for the application object.
server.py imports from here and orchestrates bootstrap.
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, ORJSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles


def _unique_operation_id(route: "APIRoute") -> str:
    """Tag + method + path-based operation_id so every route gets a unique OpenAPI id."""

    def _safe(value: str) -> str:
        return "".join(c if c.isalnum() else "_" for c in value).strip("_").lower()

    tag = route.tags[0] if route.tags else "default"
    methods = "_".join(sorted(route.methods or ["any"])).lower()
    return f"{_safe(tag)}__{methods}__{_safe(route.path)}"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""

    application = FastAPI(
        generate_unique_id_function=_unique_operation_id,
        title="Syroce PMS - Otel Yönetim Sistemi",
        description="""
## Syroce PMS - Kapsamlı Otel Yönetim Platformu

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
    _backend_dir = Path(__file__).parent
    @application.get("/api/download/screenshots", include_in_schema=False)
    async def download_screenshots_zip():
        zip_path = _backend_dir / "Syroce_PMS_AppStore_Screenshots.zip"
        if not zip_path.exists():
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Screenshots ZIP not found")
        return FileResponse(
            path=str(zip_path),
            filename="Syroce_PMS_AppStore_Screenshots.zip",
            media_type="application/zip",
        )

    # ── Static file serving (uploads) ───────────────────────────────
    upload_dir = Path(os.environ.get("UPLOAD_DIR", str(_backend_dir / "uploads")))
    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
        application.mount("/api/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")
    except (PermissionError, OSError) as e:
        import logging
        logging.getLogger(__name__).warning("Upload static mount failed (%s): %s", upload_dir, e)

    # ── OpenAPI schema cache ────────────────────────────────────────
    # With ~2435 paths, FastAPI's default openapi() rebuild costs ~1.5s per request
    # (called by /docs, /redoc, /api/openapi.json). Cache the generated dict so the
    # second and later calls are served from memory.
    from fastapi.openapi.utils import get_openapi as _get_openapi

    def _cached_openapi():
        if application.openapi_schema is None:
            application.openapi_schema = _get_openapi(
                title=application.title,
                version=application.version,
                description=application.description,
                routes=application.routes,
                tags=application.openapi_tags,
                servers=application.servers,
            )
        return application.openapi_schema

    application.openapi = _cached_openapi  # type: ignore[assignment]

    return application
