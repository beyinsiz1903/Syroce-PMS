"""Quick ID Reader API — FastAPI app entry.

Refactor R3a: split monolithic server.py into:
  - db.py          : Mongo client + collections
  - schemas.py     : Pydantic request models + constants (MAX_IMAGE_BASE64_LENGTH, ID_EXTRACTION_PROMPT)
  - middleware.py  : SecurityHeaders / CSRF / RequestSizeLimit + exception handlers
  - helpers.py     : serialize_doc, image-validate, audit, throttle, find_duplicates, extract_id_data
This file keeps only app construction + lifespan + route handlers.
"""
from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from dotenv import load_dotenv
import os
import json
import base64
import re
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from bson import ObjectId
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
import qrcode
import io

load_dotenv()

# ===== Structured Logging Setup =====
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("quickid")

# Suppress cosmetic passlib bcrypt-version detection warning.
logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.ERROR)
logging.getLogger("passlib").setLevel(logging.ERROR)

# --- Local module imports (R3a split). Order matters: load_dotenv() above must
# run first so DB/env-dependent modules see their environment. noqa: E402 below.
from db import db, guests_col, scans_col, audit_col, users_col  # noqa: E402
from schemas import (  # noqa: E402
    MAX_IMAGE_BASE64_LENGTH,
    ScanRequest, GuestCreate, GuestUpdate,
    LoginRequest, UserCreate, UserUpdate, PasswordChange,
    SettingsUpdate, RightsRequestCreate, RightsRequestProcess,
    FaceCompareRequest, LivenessCheckRequest,
    TcKimlikValidateRequest, EmniyetBildirimiRequest,
    PropertyCreate, PropertyUpdate, KioskSessionCreate,
    PreCheckinCreate, PreCheckinScanRequest, OfflineSyncRequest,
    RoomCreate, RoomUpdate, RoomAssignRequest, AutoAssignRequest,
    GroupCheckinRequest, GuestPhotoRequest,
    BackupCreateRequest, BackupRestoreRequest,
)
from helpers import (  # noqa: E402
    get_user_or_ip, serialize_doc, _validate_image_payload,
    extract_id_data, find_duplicates,
    create_audit_log, create_auth_audit_log, compute_field_diffs,
    _chgpw_throttle_check, _chgpw_throttle_reset,
)
from middleware import (  # noqa: E402
    SecurityHeadersMiddleware, CSRFProtectionMiddleware, RequestSizeLimitMiddleware,
    rate_limit_handler, generic_exception_handler,
)

# --- External feature modules (unchanged) ---
from auth import (  # noqa: E402
    hash_password, verify_password, create_token,
    require_auth, require_admin, security,
    validate_password_strength, check_account_lockout, record_login_attempt,
    unlock_account, ACCOUNT_LOCKOUT_THRESHOLD,
)
from kvkk import get_settings, update_settings, run_data_cleanup, anonymize_guest  # noqa: E402
from kvkk_compliance import (  # noqa: E402
    create_rights_request, list_rights_requests, process_rights_request,
    get_guest_data_for_access, export_guest_data_portable,
    generate_verbis_report, get_data_inventory, get_retention_warnings,
    calculate_confidence_score,
)
from tc_kimlik import validate_tc_kimlik, generate_emniyet_bildirimi, is_foreign_guest  # noqa: E402
from biometric import compare_faces, check_liveness, get_liveness_challenge  # noqa: E402
from multi_property import (  # noqa: E402
    create_property, list_properties, get_property, update_property,
    create_kiosk_session, update_kiosk_activity, get_kiosk_sessions,
    store_offline_data, get_pending_syncs, process_sync,
    create_precheckin_token, get_precheckin_token, use_precheckin_token, list_precheckin_tokens,
)
from image_quality import assess_image_quality, preprocess_image_for_ocr  # noqa: E402
from mrz_parser import parse_mrz_from_text, detect_and_parse_mrz  # noqa: E402
from room_assignment import (  # noqa: E402
    create_room, list_rooms, get_room, update_room,
    assign_room, release_room, auto_assign_room, get_room_stats,
    ROOM_TYPES, ROOM_STATUSES,
)
from monitoring import (  # noqa: E402
    get_scan_statistics, get_error_log, track_ai_cost,
    get_ai_cost_summary, get_monitoring_dashboard,
)
from backup_restore import (  # noqa: E402
    create_backup, list_backups, restore_backup, get_backup_schedule,
)
from ocr_fallback import ocr_scan_document, is_tesseract_available  # noqa: E402
from ocr_providers import (  # noqa: E402
    list_providers, get_provider_info, extract_with_provider,
    smart_scan, get_provider_stats, estimate_scan_cost,
    get_smart_provider_chain, update_provider_health, PROVIDERS,
)
from pdf_reports import generate_form_c_pdf, generate_guest_list_pdf  # noqa: E402
from email_service import (  # noqa: E402
    notify_checkin, notify_checkout, notify_kvkk_request,
    get_email_log, get_email_status, send_email,
)

# --- Rate limiter ---
from rate_limit import limiter  # shared singleton (also used by routers/*)

# --- FastAPI app ---
app = FastAPI(
    title="Quick ID Reader API",
    description="""
## Otel Kimlik Okuyucu Sistemi API

Quick ID Reader, otel resepsiyon operasyonları için geliştirilmiş kimlik tarama ve misafir yönetim sistemidir.

### Özellikler:
- **AI Kimlik Tarama**: GPT-4o Vision ile kimlik belgelerinden otomatik bilgi çıkarımı
- **Misafir Yönetimi**: CRUD, check-in/check-out, toplu tarama
- **KVKK Uyumluluğu**: Tam 6698 sayılı kanun uyumluluğu
- **Güvenlik**: JWT auth, RBAC, rate limiting, denetim izi

### Kimlik Doğrulama:
Tüm korumalı endpoint'ler Bearer token gerektirir:
```
Authorization: Bearer <jwt_token>
```

### Varsayılan Hesaplar:
- **Admin**: admin@quickid.com / admin123
- **Resepsiyon**: resepsiyon@quickid.com / resepsiyon123
    """,
    version="3.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    openapi_tags=[
        {"name": "Sağlık", "description": "Sistem sağlık kontrolleri"},
        {"name": "Kimlik Doğrulama", "description": "Giriş, token yönetimi"},
        {"name": "Kullanıcı Yönetimi", "description": "Admin kullanıcı CRUD işlemleri"},
        {"name": "Tarama", "description": "AI kimlik tarama ve inceleme kuyruğu"},
        {"name": "Misafirler", "description": "Misafir CRUD, check-in/check-out"},
        {"name": "Biyometrik", "description": "Yüz eşleştirme ve canlılık testi"},
        {"name": "TC Kimlik", "description": "TC Kimlik No doğrulama ve Emniyet bildirimi"},
        {"name": "Ön Check-in", "description": "QR kod ile misafir ön check-in"},
        {"name": "Multi-Property", "description": "Çoklu tesis/otel yönetimi"},
        {"name": "Kiosk", "description": "Self-servis kiosk modu"},
        {"name": "Offline Sync", "description": "Çevrimdışı senkronizasyon"},
        {"name": "Denetim İzi", "description": "Audit trail ve değişiklik geçmişi"},
        {"name": "Dashboard", "description": "İstatistikler ve genel bakış"},
        {"name": "Dışa Aktarım", "description": "CSV/JSON veri dışa aktarımı"},
        {"name": "KVKK Ayarları", "description": "KVKK/GDPR yapılandırma"},
        {"name": "KVKK Uyumluluk", "description": "Hak talepleri, VERBİS, veri envanteri"},
        {"name": "API Rehberi", "description": "Entegrasyon rehberi ve dokümantasyon"},
        {"name": "Oda Yönetimi", "description": "Oda atama ve yönetimi"},
        {"name": "Grup Check-in", "description": "Toplu misafir kaydı"},
        {"name": "Monitoring", "description": "Sistem izleme ve metrikler"},
        {"name": "Yedekleme", "description": "Veritabanı yedekleme ve geri yükleme"},
        {"name": "OCR", "description": "Offline OCR ve görüntü işleme"},
    ],
)
app.state.limiter = limiter

# --- Exception handlers ---
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# --- CORS whitelist ---
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "")
REPLIT_DEV_DOMAIN = os.environ.get("REPLIT_DEV_DOMAIN", "")
if CORS_ORIGINS == "*":
    cors_origins_list = ["*"]
elif CORS_ORIGINS:
    cors_origins_list = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
else:
    cors_origins_list = [
        "http://localhost:3000",
        "http://localhost:5000",
        "http://0.0.0.0:5000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5000",
    ]
    if REPLIT_DEV_DOMAIN:
        cors_origins_list.append(f"https://{REPLIT_DEV_DOMAIN}")

# --- Middleware (added in reverse-execution order: last added runs first) ---
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFProtectionMiddleware, cors_origins_list=cors_origins_list)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# --- OpenAI key (used in extract_id_data via llm_client) ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


# ===== STARTUP: Create default admin =====
@app.on_event("startup")
async def startup_tasks():
    """Startup: create indexes + default users"""
    # ===== MongoDB Indexes =====
    import logging
    logger = logging.getLogger("quickid.startup")

    # v50 Round-3: Pillow MUST be available — _validate_image_payload depends
    # on PIL.Image.verify() to defeat magic-byte-only forgeries. Silent
    # ImportError fallback would re-open Bug CK class. Fail-fast at boot.
    try:
        from PIL import Image  # noqa: F401
    except ImportError as e:
        logger.error("FATAL: Pillow not installed — guest photo validator degraded. Install: pip install Pillow")
        raise RuntimeError("Pillow is required for image upload validation") from e

    try:
        # Users - email unique index
        await users_col.create_index("email", unique=True, background=True)

        # Guests - performance indexes
        await guests_col.create_index("id_number", background=True)
        await guests_col.create_index("status", background=True)
        await guests_col.create_index("created_at", background=True)
        await guests_col.create_index([("first_name", 1), ("last_name", 1)], background=True)
        await guests_col.create_index([("status", 1), ("created_at", -1)], background=True)

        # Scans - performance indexes
        await scans_col.create_index("created_at", background=True)
        await scans_col.create_index("status", background=True)
        await scans_col.create_index("scanned_by", background=True)
        await scans_col.create_index("review_status", background=True)
        await scans_col.create_index([("created_at", -1), ("status", 1)], background=True)

        # Audit logs - performance indexes
        await audit_col.create_index("guest_id", background=True)
        await audit_col.create_index("created_at", background=True)
        await audit_col.create_index("action", background=True)
        await audit_col.create_index([("guest_id", 1), ("created_at", -1)], background=True)
        # v49 Round-1: indexes for new auth-category queries via /api/audit/auth.
        await audit_col.create_index([("category", 1), ("created_at", -1)], background=True)
        await audit_col.create_index([("category", 1), ("actor_id", 1), ("created_at", -1)], background=True)
        await audit_col.create_index([("category", 1), ("target_id", 1), ("created_at", -1)], background=True)

        # Login attempts - account lockout
        lockout_col = db["login_attempts"]
        await lockout_col.create_index("email", background=True)
        await lockout_col.create_index([("email", 1), ("success", 1), ("timestamp", -1)], background=True)
        # TTL index: auto-delete old attempts after 24 hours
        try:
            await lockout_col.create_index("timestamp", name="ttl_cleanup", expireAfterSeconds=86400, background=True)
        except Exception:
            pass  # TTL index already exists or conflict

        # Rooms
        rooms_col = db["rooms"]
        await rooms_col.create_index("room_number", unique=True, background=True)
        await rooms_col.create_index("status", background=True)
        await rooms_col.create_index("property_id", background=True)

        # Properties
        await db["properties"].create_index("name", background=True)

        # Emniyet bildirimleri
        await db["emniyet_bildirimleri"].create_index("guest_id", background=True)
        await db["emniyet_bildirimleri"].create_index("created_at", background=True)

        # KVKK rights requests
        await db["kvkk_rights_requests"].create_index("status", background=True)
        await db["kvkk_rights_requests"].create_index("created_at", background=True)

        # AI cost tracking
        await db["ai_cost_tracking"].create_index("created_at", background=True)
        await db["ai_cost_tracking"].create_index("model", background=True)

        # Biometric matches
        await db["biometric_matches"].create_index("created_at", background=True)

        # Offline sync
        await db["offline_sync"].create_index("status", background=True)
        await db["offline_sync"].create_index("property_id", background=True)

        logger.info("✅ MongoDB indexes created successfully")
    except Exception as e:
        logger.warning(f"⚠️ Index creation warning: {e}")

    # ===== Default Users (v107 Bug DAH, architect P0 — REVISED, no plaintext password leak) =====
    # Eski davranış: startup'ta admin@quickid.com/admin123 + resepsiyon@quickid.com/resepsiyon123 otomatik seed.
    # İlk DAH fix denemesi: random password üret + LOG → architect 2. tur P0: log leak (operator log
    # erişimi olan herkes hesabı ele geçirir). Bu turda **plaintext password ASLA log'a/dosyaya yazılmaz**.
    #
    # 3 yol:
    #   1. SEED_DEFAULT_USERS=1 (dev only)        → known passwords seed (log OK, dev)
    #   2. BOOTSTRAP_ADMIN_PASSWORD env (prod)    → env'den oku, hash'le, log'da SADECE "seeded from env"
    #      (ek olarak BOOTSTRAP_RECEPTION_PASSWORD reception için)
    #   3. Hiçbir env yok                         → admin yoksa SKIP seed + warning log
    #      (operator önceden env set eder veya mongo'dan manuel ekler — password güvenli iletme yolu yok)
    #
    # Legacy rotation (mevcut admin/admin123 kurulumları):
    #   - bcrypt match → password_hash random unrecoverable + is_active=False + force_password_change=True
    #   - log'da "DISABLED — re-enable via admin reset-password or set BOOTSTRAP env + redeploy"
    #   - Hesap effectively kilitlenir; operator başka admin ile reset eder veya env set + redeploy.
    import secrets as _secrets

    seed_flag = os.environ.get("SEED_DEFAULT_USERS", "").lower() in ("1", "true", "yes")
    is_prod = os.environ.get("ENV", "").lower() == "production"

    if seed_flag and is_prod:
        raise RuntimeError(
            "SEED_DEFAULT_USERS=1 production ortamında reddedildi (default credential takeover riski). "
            "Production'da BOOTSTRAP_ADMIN_PASSWORD env set edin veya admin user'ı mongo'dan manuel oluşturun."
        )

    async def _seed_or_rotate(email: str, name: str, role: str, legacy_pw: str, env_var: str | None):
        """Seed user if missing (only if dev seed flag OR explicit env password); else rotate legacy.

        Plaintext password ASLA log'a/dosyaya yazılmaz.
          - SEED_DEFAULT_USERS=1: legacy_pw ile seed (dev only, log uyarı verir)
          - env_var set: env'den oku, hash'le, log'da SADECE "seeded from env"
          - Aksi: SKIP + warning (operator önceden env set etmeli veya mongo manuel)
        Legacy rotation: bcrypt match → password disable (random) + is_active=False.
        """
        existing = await users_col.find_one({"email": email})
        bootstrap_pw = os.environ.get(env_var) if env_var else None

        if not existing:
            # bootstrap_managed=True marker: bu hesap startup tarafından yönetiliyor.
            # Operator manuel oluşturduğu user'larda bu flag yok → reactivation predicate
            # tetiklenmez (architect 5. tur narrowing).
            if seed_flag:
                pw = legacy_pw
                logger.warning(f"⚠️ SEED_DEFAULT_USERS=1: {email} seeded with known DEV password (DEV ONLY, do not use in prod).")
                await users_col.insert_one({
                    "email": email, "password_hash": hash_password(pw), "name": name, "role": role,
                    "is_active": True, "force_password_change": False,
                    "bootstrap_managed": True,
                    "created_at": datetime.now(timezone.utc),
                })
            elif bootstrap_pw:
                logger.info(f"🔑 {email} seeded from {env_var} env (force_password_change=True).")
                await users_col.insert_one({
                    "email": email, "password_hash": hash_password(bootstrap_pw), "name": name, "role": role,
                    "is_active": True, "force_password_change": True,
                    "bootstrap_managed": True,
                    "created_at": datetime.now(timezone.utc),
                })
            else:
                logger.warning(
                    f"⚠️ {email} not seeded — set {env_var} env (production) or SEED_DEFAULT_USERS=1 (dev). "
                    f"Otherwise create the user manually via mongo or another admin's reset-password endpoint."
                )
            return

        # v107 Bug DAH P0 (architect 4th round): bootstrap recovery dead-end fix.
        # Önceki davranış: legacy rotate ilk deploy'da user'ı disabled bıraktı; ikinci
        # deploy'da BOOTSTRAP env set edilse bile `verify_password(legacy_pw)` False
        # döner → reactivate skip → operator permanent locked.
        # Yeni davranış (operator-friendly):
        #   (a) bootstrap_pw set + (legacy match VEYA is_active=False VEYA force_password_change=True)
        #       → unconditionally rotate to env password + reactivate. Bu, ilk-rotate-sonra-redeploy
        #         senaryosunu kapsar. Active operator-set password'lere dokunulmaz (3 koşulun
        #         hepsi False olur).
        #   (b) bootstrap_pw yok + legacy match → disable (random hash + is_active=False).
        # v107 EK-3 round-5 (architect medium): predicate narrowing.
        # `bootstrap_managed=True` marker: yalnızca startup tarafından seed/rotate edilmiş
        # bootstrap hesaplarını otomatik reactivate ederiz. Operator manuel disable etmiş
        # bir bootstrap user `bootstrap_managed`'i temizleyebilir (örn. mongo shell ile
        # `$unset: {bootstrap_managed: ""}`) → BOOTSTRAP env hala set olsa bile reactive
        # edilmez. Yeni manuel oluşturulmuş user'lar zaten `bootstrap_managed` taşımaz.
        is_bootstrap_managed = bool(existing.get("bootstrap_managed"))
        is_disabled_or_forced = (
            existing.get("is_active") is False
            or existing.get("force_password_change") is True
        )
        legacy_match = verify_password(legacy_pw, existing.get("password_hash", ""))

        if bootstrap_pw and not seed_flag and legacy_match:
            # Legacy known-DEV password match → her zaman rotate (eski admin/admin123).
            # Bu hesap bootstrap_managed olmasa da ZARARLIYDI; rotate güvenliği artırır.
            await users_col.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "password_hash": hash_password(bootstrap_pw),
                    "is_active": True,
                    "force_password_change": True,
                    "bootstrap_managed": True,
                }},
            )
            logger.info(f"🔑 LEGACY {email} (had known DEV password) rotated to {env_var} env value (force_password_change=True).")
        elif bootstrap_pw and not seed_flag and is_disabled_or_forced and is_bootstrap_managed:
            # Bootstrap-managed disabled hesap → BOOTSTRAP env ile reactivate.
            # bootstrap_managed=False olan disabled hesaplar (operator kasıtlı disable)
            # otomatik açılmaz.
            await users_col.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "password_hash": hash_password(bootstrap_pw),
                    "is_active": True,
                    "force_password_change": True,
                }},
            )
            logger.info(f"🔑 BOOTSTRAP-MANAGED {email} (was disabled/force_change) rotated to {env_var} env value.")
        elif not bootstrap_pw and not seed_flag and legacy_match:
            disabled_token = _secrets.token_urlsafe(64)
            await users_col.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "password_hash": hash_password(disabled_token),
                    "is_active": False,
                    "force_password_change": True,
                    "bootstrap_managed": True,
                }},
            )
            logger.warning(
                f"🚨 LEGACY {email} had known DEV password — DISABLED (is_active=False, random unrecoverable hash). "
                f"To re-enable: set {env_var} env + redeploy, OR have another admin reset via /api/users/{{id}}/reset-password."
            )

    await _seed_or_rotate("admin@quickid.com", "Admin", "admin", "admin123", "BOOTSTRAP_ADMIN_PASSWORD")
    await _seed_or_rotate("resepsiyon@quickid.com", "Resepsiyon", "reception", "resepsiyon123", "BOOTSTRAP_RECEPTION_PASSWORD")

    # ===== Background Scheduler: Auto-Backup & KVKK Cleanup =====
    import asyncio

    async def scheduled_tasks():
        """Arka planda çalışan zamanlanmış görevler"""
        while True:
            try:
                await asyncio.sleep(6 * 3600)  # Her 6 saatte bir çalış

                # 1) Otomatik KVKK Temizliği
                settings = await get_settings(db)
                if settings.get("auto_cleanup_enabled"):
                    try:
                        result = await run_data_cleanup(db)
                        logger.info(f"🧹 Otomatik KVKK temizliği: {result}")
                    except Exception as e:
                        logger.error(f"❌ KVKK temizlik hatası: {e}")

                # 2) Otomatik Yedekleme (günde 1 kez - 24 saatte bir)
                last_backup_check = getattr(scheduled_tasks, '_last_backup', None)
                now = datetime.now(timezone.utc)
                if last_backup_check is None or (now - last_backup_check).total_seconds() > 24 * 3600:
                    try:
                        backup_result = await create_backup(db, created_by="system_auto", description="Otomatik günlük yedek")
                        scheduled_tasks._last_backup = now
                        logger.info(f"💾 Otomatik yedekleme tamamlandı: {backup_result.get('backup_id', 'unknown')}")
                    except Exception as e:
                        logger.error(f"❌ Otomatik yedekleme hatası: {e}")

                # 3) Eski soft-deleted misafirleri temizle (30 günden eski)
                try:
                    cutoff = now - timedelta(days=30)
                    deleted_result = await guests_col.delete_many({
                        "status": "deleted",
                        "deleted_at": {"$lt": cutoff}
                    })
                    if deleted_result.deleted_count > 0:
                        logger.info(f"🗑️ {deleted_result.deleted_count} eski silinen misafir kalıcı olarak temizlendi")
                except Exception as e:
                    logger.error(f"❌ Silinen misafir temizlik hatası: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Zamanlanmış görev hatası: {e}")
                await asyncio.sleep(60)  # Hata durumunda 1 dakika bekle

    # Background task başlat
    asyncio.create_task(scheduled_tasks())
    logger.info("⏰ Zamanlanmış görevler başlatıldı (6 saatlik döngü)")


# ===== AUTH ROUTES =====

# ===== R3b routers (split from monolithic server.py) =====
from routers.health import router as health_router  # noqa: E402
from routers.auth import router as auth_router  # noqa: E402
from routers.users import router as users_router  # noqa: E402
from routers.settings import router as settings_router  # noqa: E402

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(settings_router)
from routers.biometric import router as biometric_router  # noqa: E402
from routers.precheckin import router as precheckin_router  # noqa: E402
from routers.properties import router as properties_router  # noqa: E402
from routers.kiosk import router as kiosk_router  # noqa: E402
from routers.sync import router as sync_router  # noqa: E402
from routers.monitoring import router as monitoring_router  # noqa: E402

app.include_router(biometric_router)
app.include_router(precheckin_router)
app.include_router(properties_router)
app.include_router(kiosk_router)
app.include_router(sync_router)
app.include_router(monitoring_router)



# ===== SCAN ENDPOINTS =====
@app.post("/api/scan", tags=["Tarama"], summary="Kimlik belgesi tara (çoklu provider)",
          description="AI ile kimlik belgesini tarayıp bilgi çıkarır. Provider seçimi: gpt-4o, gpt-4o-mini, gemini-flash, tesseract, auto. Görüntü kalite kontrolü + MRZ parsing + Confidence score.")
@limiter.limit("15/minute")
async def scan_id(request: Request, scan_req: ScanRequest, user=Depends(require_auth)):
    try:
        # Step 0: Image size + content validation (v50 Round-3: shared validator)
        _validate_image_payload(scan_req.image_base64)
        if len(scan_req.image_base64) > MAX_IMAGE_BASE64_LENGTH:
            raise HTTPException(
                status_code=413,
                detail=f"Görüntü boyutu çok büyük. Maksimum {MAX_IMAGE_BASE64_LENGTH // (1024*1024)}MB izin verilir."
            )

        # Per-request API keys (PMS proxy upstream'inden gelir)
        per_req_keys = {
            "openai": request.headers.get("X-OpenAI-Key"),
            "gemini": request.headers.get("X-Gemini-Key"),
        }
        per_req_keys = {k: v for k, v in per_req_keys.items() if v}

        # Step 1: Image quality check (geliştirilmiş)
        quality = assess_image_quality(scan_req.image_base64)
        quality_score = quality.get("overall_score", 70)

        if quality.get("quality_checked") and not quality.get("pass", True):
            # Kalite çok düşükse uyarı dön ama yine de tara
            pass

        # Step 2: Provider seçimi
        requested_provider = scan_req.provider
        use_smart = scan_req.smart_mode if scan_req.smart_mode is not None else True

        if requested_provider == "tesseract":
            # Doğrudan Tesseract OCR kullan
            ocr_result = ocr_scan_document(scan_req.image_base64)
            if not ocr_result.get("success"):
                raise Exception(ocr_result.get("error", "OCR hatası"))

            documents = ocr_result.get("documents", [])
            extracted = {"documents": documents, "document_count": len(documents)}
            used_provider = "tesseract"
            provider_info = {"name": "Tesseract OCR", "cost": 0, "speed": "fast"}
            response_time = 0
        elif use_smart and not requested_provider:
            # Akıllı tarama: kaliteye göre provider seç
            scan_result = await smart_scan(
                scan_req.image_base64,
                quality_score=quality_score,
                api_keys=per_req_keys or None,
            )
            if not scan_result.get("success"):
                raise Exception(scan_result.get("error", "Tüm AI sağlayıcılar başarısız"))

            extracted = {
                "documents": scan_result.get("documents", []),
                "document_count": scan_result.get("document_count", 0),
            }
            documents = extracted["documents"]
            used_provider = scan_result.get("provider", "unknown")
            provider_info = {
                "name": scan_result.get("provider_name", used_provider),
                "cost": scan_result.get("estimated_cost", 0),
                "response_time": scan_result.get("response_time", 0),
                "fallback_used": scan_result.get("fallback_used", False),
                "original_provider": scan_result.get("original_provider", ""),
                "provider_chain": scan_result.get("provider_chain", []),
            }
            response_time = scan_result.get("response_time", 0)
        elif requested_provider and requested_provider in PROVIDERS:
            # Belirli provider kullan
            scan_result = await extract_with_provider(requested_provider, scan_req.image_base64, api_keys=per_req_keys or None)
            extracted = {
                "documents": scan_result.get("documents", []),
                "document_count": scan_result.get("document_count", 0),
            }
            documents = extracted["documents"]
            used_provider = requested_provider
            provider_info = {
                "name": scan_result.get("provider_name", used_provider),
                "cost": scan_result.get("estimated_cost", 0),
                "response_time": scan_result.get("response_time", 0),
            }
            response_time = scan_result.get("response_time", 0)
        else:
            # Varsayılan: eski yöntem (GPT-4o)
            extracted = await extract_id_data(scan_req.image_base64)
            documents = extracted.get("documents", [])
            used_provider = "gpt-4o"
            provider_info = {"name": "GPT-4o", "cost": 0.015}
            response_time = 0

        document_count = extracted.get("document_count", len(documents))

        # Step 3: Calculate confidence score
        confidence = calculate_confidence_score(extracted)

        # Step 4: MRZ parsing from raw text (geliştirilmiş)
        mrz_results = []
        for doc in documents:
            raw_text = doc.get("raw_extracted_text", "")
            if raw_text:
                mrz = parse_mrz_from_text(raw_text)
                if mrz.get("mrz_detected"):
                    mrz_results.append(mrz)
                    # Enrich document data with MRZ info
                    mrz_data = mrz["mrz_data"]
                    if mrz_data.get("first_name") and not doc.get("first_name"):
                        doc["first_name"] = mrz_data["first_name"]
                    if mrz_data.get("last_name") and not doc.get("last_name"):
                        doc["last_name"] = mrz_data["last_name"]
                    if mrz_data.get("birth_date") and not doc.get("birth_date"):
                        doc["birth_date"] = mrz_data["birth_date"]
                    if mrz_data.get("expiry_date") and not doc.get("expiry_date"):
                        doc["expiry_date"] = mrz_data["expiry_date"]
                    if mrz_data.get("passport_number") and not doc.get("document_number"):
                        doc["document_number"] = mrz_data["passport_number"]
                    if mrz_data.get("document_number") and not doc.get("document_number"):
                        doc["document_number"] = mrz_data["document_number"]

        # Step 5: Track AI cost
        try:
            provider_cost = provider_info.get("cost", 0.01)
            await track_ai_cost(db, model=used_provider, operation="id_scan",
                              input_tokens=1000, output_tokens=500,
                              estimated_cost=provider_cost)
        except Exception:
            pass

        scan_doc = {
            "extracted_data": extracted,
            "document_count": document_count,
            "is_valid": any(d.get("is_valid", False) for d in documents),
            "document_type": documents[0].get("document_type", "other") if documents else "other",
            "created_at": datetime.now(timezone.utc),
            "status": "completed",
            "warnings": [],
            "scanned_by": user.get("email"),
            "confidence_score": confidence.get("overall_score", 0),
            "confidence_level": confidence.get("confidence_level", "low"),
            "review_status": "needs_review" if confidence.get("review_needed") else "auto_approved",
            "image_quality": quality,
            "mrz_results": mrz_results,
            "provider": used_provider,
            "provider_info": provider_info,
        }
        for doc in documents:
            scan_doc["warnings"].extend(doc.get("warnings", []))

        # Add quality warnings
        if quality.get("warnings"):
            scan_doc["warnings"].extend(quality["warnings"])

        result = await scans_col.insert_one(scan_doc)
        scan_doc["_id"] = result.inserted_id

        return {
            "success": True,
            "scan": serialize_doc(scan_doc),
            "extracted_data": extracted,
            "document_count": document_count,
            "documents": documents,
            "confidence": confidence,
            "image_quality": quality,
            "mrz_results": mrz_results,
            "provider": used_provider,
            "provider_info": provider_info,
        }
    except HTTPException:
        raise
    except Exception as e:
        error_str = str(e)

        # Auto-fallback: AI başarısız olursa Tesseract dene
        tesseract_result = None
        if is_tesseract_available() and scan_req.provider != "tesseract":
            try:
                tesseract_result = ocr_scan_document(scan_req.image_base64)
                if tesseract_result.get("success"):
                    documents = tesseract_result.get("documents", [])
                    scan_doc = {
                        "extracted_data": {"documents": documents, "document_count": len(documents)},
                        "document_count": len(documents),
                        "is_valid": any(d.get("is_valid", False) for d in documents),
                        "created_at": datetime.now(timezone.utc),
                        "status": "completed_fallback",
                        "source": "tesseract_ocr_fallback",
                        "scanned_by": user.get("email"),
                        "confidence_level": "low",
                        "confidence_score": 40,
                        "review_status": "needs_review",
                        "image_quality": quality if 'quality' in dir() else {},
                        "warnings": [
                            f"AI tarama başarısız oldu ({error_str}). Tesseract OCR ile tarandı.",
                            "Offline OCR sonuçları - doğrulama gerekli.",
                        ],
                        "provider": "tesseract",
                        "provider_info": {"name": "Tesseract OCR (Fallback)", "cost": 0},
                        "original_error": error_str,
                    }
                    await scans_col.insert_one(scan_doc)

                    return {
                        "success": True,
                        "scan": serialize_doc(scan_doc),
                        "documents": documents,
                        "document_count": len(documents),
                        "confidence": {"overall_score": 40, "confidence_level": "low", "review_needed": True},
                        "image_quality": quality if 'quality' in dir() else {},
                        "mrz_results": [],
                        "provider": "tesseract",
                        "provider_info": {"name": "Tesseract OCR (Fallback)", "cost": 0},
                        "fallback_used": True,
                        "original_error": error_str,
                        "message": "AI tarama başarısız, Tesseract OCR ile tarandı. Sonuçları kontrol edin.",
                    }
            except Exception:
                pass

        # Fallback rehberi
        fallback_guidance = []
        if "timeout" in error_str.lower() or "connection" in error_str.lower():
            fallback_guidance = [
                "Bağlantı hatası oluştu. Lütfen tekrar deneyin.",
                "İnternet bağlantınızı kontrol edin.",
                "Offline OCR modunu deneyin.",
            ]
        elif "rate" in error_str.lower() or "limit" in error_str.lower():
            fallback_guidance = [
                "İstek limiti aşıldı. Lütfen biraz bekleyin.",
                "Daha ucuz bir provider deneyin (GPT-4o-mini veya Gemini Flash).",
            ]
        else:
            fallback_guidance = [
                "Kimlik belgesi okunamadı. Lütfen şunları deneyin:",
                "1. Belgeyi düz bir yüzeye yerleştirin",
                "2. Flaş kullanarak fotoğraf çekin",
                "3. Belgenin tamamının görünür olduğundan emin olun",
                "4. Parlama ve gölge olmadığından emin olun",
                "5. Daha iyi aydınlatma altında tekrar deneyin",
                "6. Offline OCR modunu deneyin",
                "7. Farklı bir AI sağlayıcı seçin",
            ]
        scan_doc = {
            "status": "failed",
            "error": error_str,
            "created_at": datetime.now(timezone.utc),
            "scanned_by": user.get("email"),
            "fallback_guidance": fallback_guidance,
        }
        await scans_col.insert_one(scan_doc)
        raise HTTPException(status_code=500, detail={
            "message": f"Tarama başarısız: {error_str}",
            "fallback_guidance": fallback_guidance,
            "can_retry": True,
        })

@app.get("/api/scans", tags=["Tarama"], summary="Tarama geçmişi")
async def get_scans(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), user=Depends(require_auth)):
    skip = (page - 1) * limit
    total = await scans_col.count_documents({})
    cursor = scans_col.find({}).sort("created_at", -1).skip(skip).limit(limit)
    scans = [serialize_doc(doc) async for doc in cursor]
    return {"scans": scans, "total": total, "page": page, "limit": limit}

@app.get("/api/scans/review-queue", tags=["Tarama"], summary="İnceleme kuyruğu",
         description="Düşük güvenilirlik puanlı taramaları listeler")
async def get_review_queue(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    review_status: Optional[str] = Query(None, description="needs_review, auto_approved, reviewed"),
    user=Depends(require_auth)
):
    query = {}
    if review_status:
        query["review_status"] = review_status
    else:
        query["review_status"] = "needs_review"

    skip = (page - 1) * limit
    total = await scans_col.count_documents(query)
    cursor = scans_col.find(query).sort("created_at", -1).skip(skip).limit(limit)
    scans = [serialize_doc(doc) async for doc in cursor]
    return {"scans": scans, "total": total, "page": page, "limit": limit}

@app.patch("/api/scans/{scan_id}/review", tags=["Tarama"], summary="Tarama inceleme durumu güncelle")
async def update_scan_review(scan_id: str, review_status: str = Query(..., description="reviewed, needs_review"), user=Depends(require_auth)):
    try:
        oid = ObjectId(scan_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz tarama ID")
    if review_status not in ("reviewed", "needs_review", "auto_approved"):
        raise HTTPException(status_code=400, detail="Geçersiz inceleme durumu")
    result = await scans_col.update_one(
        {"_id": oid},
        {"$set": {"review_status": review_status, "reviewed_at": datetime.now(timezone.utc), "reviewed_by": user.get("email")}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404)
    doc = await scans_col.find_one({"_id": oid})
    return {"success": True, "scan": serialize_doc(doc)}


# ===== GUEST ENDPOINTS =====
@app.get("/api/guests/check-duplicate")
@limiter.limit("60/minute")
async def check_duplicate(
    request: Request,
    id_number: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    birth_date: Optional[str] = None,
    user=Depends(require_auth)
):
    duplicates = await find_duplicates(id_number, first_name, last_name, birth_date)
    return {"has_duplicates": len(duplicates) > 0, "duplicates": duplicates, "count": len(duplicates)}

@app.post("/api/guests")
@limiter.limit("30/minute")
async def create_guest(request: Request, guest: GuestCreate, user=Depends(require_auth)):
    if not guest.force_create:
        duplicates = await find_duplicates(guest.id_number, guest.first_name, guest.last_name, guest.birth_date)
        if duplicates:
            return {"success": False, "duplicate_detected": True, "duplicates": duplicates, "message": "Mükerrer misafir tespit edildi."}
    
    guest_data = guest.model_dump(exclude_none=True)
    original_extracted = guest_data.pop("original_extracted_data", None)
    guest_data.pop("force_create", None)
    scan_id = guest_data.pop("scan_id", None)
    kvkk_consent = guest_data.pop("kvkk_consent", False)
    
    guest_doc = {
        **guest_data,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "check_in_at": None,
        "check_out_at": None,
        "scan_ids": [scan_id] if scan_id else [],
        "original_extracted_data": original_extracted,
        "kvkk_consent": kvkk_consent,
        "kvkk_consent_at": datetime.now(timezone.utc) if kvkk_consent else None,
        "created_by": user.get("email"),
    }
    
    result = await guests_col.insert_one(guest_doc)
    guest_doc["_id"] = result.inserted_id
    guest_id = str(result.inserted_id)
    
    audit_changes = compute_field_diffs(original_extracted or {}, guest_data) if original_extracted else {}
    await create_audit_log(guest_id, "created", audit_changes, original_extracted or {}, guest_data,
                           {"scan_id": scan_id, "had_manual_edits": bool(audit_changes), "kvkk_consent": kvkk_consent},
                           user.get("email"))
    
    return {"success": True, "guest": serialize_doc(guest_doc)}

@app.get("/api/guests")
async def get_guests(
    page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None, status: Optional[str] = None,
    nationality: Optional[str] = None, document_type: Optional[str] = None,
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    include_deleted: bool = Query(False, description="Silinen misafirleri de göster"),
    user=Depends(require_auth)
):
    query = {}
    # Soft-deleted olanları varsayılan olarak gizle
    if not include_deleted:
        query["status"] = {"$ne": "deleted"}
    if search:
        query["$or"] = [
            {"first_name": {"$regex": search, "$options": "i"}},
            {"last_name": {"$regex": search, "$options": "i"}},
            {"id_number": {"$regex": search, "$options": "i"}},
            {"document_number": {"$regex": search, "$options": "i"}}
        ]
    if status:
        query["status"] = status  # Explicit status overrides the $ne filter
    if nationality: query["nationality"] = {"$regex": nationality, "$options": "i"}
    if document_type: query["document_type"] = document_type
    if date_from:
        try: query.setdefault("created_at", {})["$gte"] = datetime.fromisoformat(date_from)
        except ValueError: pass
    if date_to:
        try: query.setdefault("created_at", {})["$lte"] = datetime.fromisoformat(date_to)
        except ValueError: pass
    
    skip = (page - 1) * limit
    total = await guests_col.count_documents(query)
    cursor = guests_col.find(query).sort("created_at", -1).skip(skip).limit(limit)
    guests = [serialize_doc(doc) async for doc in cursor]
    return {"guests": guests, "total": total, "page": page, "limit": limit}

@app.get("/api/guests/{guest_id}")
async def get_guest(guest_id: str, user=Depends(require_auth)):
    try: doc = await guests_col.find_one({"_id": ObjectId(guest_id)})
    except Exception: raise HTTPException(status_code=400, detail="Invalid guest ID")
    if not doc: raise HTTPException(status_code=404, detail="Guest not found")
    return {"guest": serialize_doc(doc)}

@app.patch("/api/guests/{guest_id}")
@limiter.limit("60/minute")
async def update_guest(request: Request, guest_id: str, update: GuestUpdate, user=Depends(require_auth)):
    try: oid = ObjectId(guest_id)
    except Exception: raise HTTPException(status_code=400)
    old_doc = await guests_col.find_one({"_id": oid})
    if not old_doc: raise HTTPException(status_code=404)
    old_data = serialize_doc(old_doc)
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc)
    await guests_col.update_one({"_id": oid}, {"$set": update_data})
    doc = await guests_col.find_one({"_id": oid})
    diffs = compute_field_diffs(old_data, update_data)
    if diffs:
        await create_audit_log(guest_id, "updated", diffs, {k: old_data.get(k) for k in diffs}, {k: update_data.get(k) for k in diffs}, user_email=user.get("email"))
    return {"success": True, "guest": serialize_doc(doc)}

@app.delete("/api/guests/{guest_id}")
@limiter.limit("30/minute")
async def delete_guest(request: Request, guest_id: str, permanent: bool = Query(False, description="Kalıcı silme (true = geri alınamaz)"), user=Depends(require_auth)):
    try: oid = ObjectId(guest_id)
    except Exception: raise HTTPException(status_code=400, detail="Geçersiz misafir ID")
    doc = await guests_col.find_one({"_id": oid})
    if not doc: raise HTTPException(status_code=404, detail="Misafir bulunamadı")

    if permanent:
        # Kalıcı silme - admin gerektirir.
        # v48 (Bug CI, architect Round-4): JWT-claim role'a güvenmek STALE olur
        # (admin demote edildikten sonra token expire olana kadar yetki devam eder).
        # DB'den canlı role + is_active kontrolü yap.
        sub = user.get("sub")
        db_user = None
        if sub:
            try:
                db_user = await users_col.find_one({"_id": ObjectId(sub)})
            except Exception:
                db_user = None
        if not db_user or not db_user.get("is_active", True) or db_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Kalıcı silme için admin yetkisi gerekiyor")
        await create_audit_log(guest_id, "permanently_deleted", old_data=serialize_doc(doc), user_email=user.get("email"))
        await guests_col.delete_one({"_id": oid})
        logger.info(f"Guest {guest_id} permanently deleted by {user.get('email')}")
        return {"success": True, "action": "permanently_deleted"}
    else:
        # Soft delete - geri alınabilir
        now = datetime.now(timezone.utc)
        await guests_col.update_one({"_id": oid}, {"$set": {
            "status": "deleted",
            "deleted_at": now,
            "deleted_by": user.get("email"),
            "updated_at": now,
        }})
        await create_audit_log(guest_id, "soft_deleted", old_data=serialize_doc(doc), user_email=user.get("email"))
        logger.info(f"Guest {guest_id} soft-deleted by {user.get('email')}")
        return {"success": True, "action": "soft_deleted", "message": "Misafir silindi. Geri almak için admin ile iletişime geçin."}

@app.post("/api/guests/{guest_id}/restore", tags=["Misafirler"], summary="Silinen misafiri geri getir")
async def restore_guest(guest_id: str, user=Depends(require_admin)):
    try: oid = ObjectId(guest_id)
    except Exception: raise HTTPException(status_code=400, detail="Geçersiz misafir ID")
    doc = await guests_col.find_one({"_id": oid})
    if not doc: raise HTTPException(status_code=404, detail="Misafir bulunamadı")
    if doc.get("status") != "deleted":
        raise HTTPException(status_code=400, detail="Bu misafir silinmiş durumda değil")

    now = datetime.now(timezone.utc)
    await guests_col.update_one({"_id": oid}, {
        "$set": {"status": "pending", "updated_at": now},
        "$unset": {"deleted_at": "", "deleted_by": ""},
    })
    await create_audit_log(guest_id, "restored", metadata={"restored_by": user.get("email")}, user_email=user.get("email"))
    doc = await guests_col.find_one({"_id": oid})
    logger.info(f"Guest {guest_id} restored by {user.get('email')}")
    return {"success": True, "guest": serialize_doc(doc)}

@app.post("/api/guests/{guest_id}/checkin")
async def checkin_guest(guest_id: str, user=Depends(require_auth)):
    try: oid = ObjectId(guest_id)
    except Exception: raise HTTPException(status_code=400)
    old_doc = await guests_col.find_one({"_id": oid})
    if not old_doc: raise HTTPException(status_code=404)
    now = datetime.now(timezone.utc)
    await guests_col.update_one({"_id": oid}, {"$set": {"status": "checked_in", "check_in_at": now, "updated_at": now}})
    await create_audit_log(guest_id, "checked_in", {"status": {"old": old_doc.get("status"), "new": "checked_in"}}, metadata={"check_in_at": now.isoformat()}, user_email=user.get("email"))
    logger.info(f"📥 Check-in: Guest {guest_id} by {user.get('email')}")
    doc = await guests_col.find_one({"_id": oid})
    # Email notification (async, non-blocking)
    try:
        guest_name = f"{doc.get('first_name', '')} {doc.get('last_name', '')}".strip()
        await notify_checkin(guest_name, doc.get('room_number', ''), user.get('email'))
    except Exception:
        pass
    return {"success": True, "guest": serialize_doc(doc)}

@app.post("/api/guests/{guest_id}/checkout")
async def checkout_guest(guest_id: str, user=Depends(require_auth)):
    try: oid = ObjectId(guest_id)
    except Exception: raise HTTPException(status_code=400)
    old_doc = await guests_col.find_one({"_id": oid})
    if not old_doc: raise HTTPException(status_code=404)
    now = datetime.now(timezone.utc)
    await guests_col.update_one({"_id": oid}, {"$set": {"status": "checked_out", "check_out_at": now, "updated_at": now}})
    await create_audit_log(guest_id, "checked_out", {"status": {"old": old_doc.get("status"), "new": "checked_out"}}, metadata={"check_out_at": now.isoformat()}, user_email=user.get("email"))
    logger.info(f"📤 Check-out: Guest {guest_id} by {user.get('email')}")
    doc = await guests_col.find_one({"_id": oid})
    # Email notification (async, non-blocking)
    try:
        guest_name = f"{doc.get('first_name', '')} {doc.get('last_name', '')}".strip()
        await notify_checkout(guest_name, doc.get('room_number', ''), user.get('email'))
    except Exception:
        pass
    return {"success": True, "guest": serialize_doc(doc)}


# ===== AUDIT =====
@app.get("/api/guests/{guest_id}/audit")
async def get_guest_audit(guest_id: str, user=Depends(require_auth)):
    cursor = audit_col.find({"guest_id": guest_id}).sort("created_at", -1)
    logs = [serialize_doc(doc) async for doc in cursor]
    return {"audit_logs": logs, "total": len(logs)}

@app.get("/api/audit/recent")
async def get_recent_audit(limit: int = Query(50, ge=1, le=200), user=Depends(require_auth)):
    # v49 Round-1: previously returned ALL categories to ANY authenticated user,
    # exposing admin auth rows (actor_email/target_email) to reception users.
    # v49 Round-2: cannot trust JWT 'role' field (stale on demote) — re-fetch
    # current role from DB before admin branch. Non-admins keep guest visibility.
    db_user = await users_col.find_one({"email": user.get("email")}, {"role": 1, "is_active": 1})
    is_admin_now = bool(db_user and db_user.get("role") == "admin" and db_user.get("is_active", True))
    q = {} if is_admin_now else {"category": {"$ne": "auth"}}
    cursor = audit_col.find(q).sort("created_at", -1).limit(limit)
    logs = [serialize_doc(doc) async for doc in cursor]
    return {"audit_logs": logs, "total": len(logs)}

# v49 (Bug CJ): admin-only auth audit query. Filterable by action / actor /
# target / outcome to investigate stolen-token probing patterns.
@app.get("/api/audit/auth")
async def get_auth_audit(
    limit: int = Query(100, ge=1, le=500),
    action: str = Query(None),
    actor_id: str = Query(None),
    target_id: str = Query(None),
    outcome: str = Query(None),
    user=Depends(require_admin),
):
    q = {"category": "auth"}
    if action: q["action"] = action
    if actor_id: q["actor_id"] = actor_id
    if target_id: q["target_id"] = target_id
    if outcome: q["outcome"] = outcome
    cursor = audit_col.find(q).sort("created_at", -1).limit(limit)
    logs = [serialize_doc(doc) async for doc in cursor]
    return {"audit_logs": logs, "total": len(logs), "filter": q}


# ===== DASHBOARD =====
@app.get("/api/dashboard/stats")
async def get_dashboard_stats(user=Depends(require_auth)):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total_guests = await guests_col.count_documents({})
    today_checkins = await guests_col.count_documents({"status": "checked_in", "check_in_at": {"$gte": today_start}})
    today_checkouts = await guests_col.count_documents({"status": "checked_out", "check_out_at": {"$gte": today_start}})
    pending_reviews = await guests_col.count_documents({"status": "pending"})
    currently_checked_in = await guests_col.count_documents({"status": "checked_in"})
    total_scans = await scans_col.count_documents({})
    today_scans = await scans_col.count_documents({"created_at": {"$gte": today_start}})
    recent_cursor = scans_col.find({}).sort("created_at", -1).limit(5)
    recent_scans = [serialize_doc(doc) async for doc in recent_cursor]
    recent_guests_cursor = guests_col.find({}).sort("created_at", -1).limit(5)
    recent_guests = [serialize_doc(doc) async for doc in recent_guests_cursor]
    weekly_stats = []
    for i in range(6, -1, -1):
        day_start = (datetime.now(timezone.utc) - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = await guests_col.count_documents({"created_at": {"$gte": day_start, "$lt": day_end}})
        weekly_stats.append({"date": day_start.strftime("%Y-%m-%d"), "day": day_start.strftime("%a"), "count": count})
    return {
        "total_guests": total_guests, "today_checkins": today_checkins, "today_checkouts": today_checkouts,
        "pending_reviews": pending_reviews, "currently_checked_in": currently_checked_in,
        "total_scans": total_scans, "today_scans": today_scans,
        "recent_scans": recent_scans, "recent_guests": recent_guests, "weekly_stats": weekly_stats
    }


# ===== EXPORT =====
@app.get("/api/exports/guests.json")
async def export_guests_json(status: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, user=Depends(require_auth)):
    query = {}
    if status: query["status"] = status
    if date_from:
        try: query.setdefault("created_at", {})["$gte"] = datetime.fromisoformat(date_from)
        except ValueError: pass
    if date_to:
        try: query.setdefault("created_at", {})["$lte"] = datetime.fromisoformat(date_to)
        except ValueError: pass
    cursor = guests_col.find(query).sort("created_at", -1)
    guests = [serialize_doc(doc) async for doc in cursor]
    return {"guests": guests, "total": len(guests), "exported_at": datetime.now(timezone.utc).isoformat()}

@app.get("/api/exports/guests.csv")
async def export_guests_csv(status: Optional[str] = None, user=Depends(require_auth)):
    from fastapi.responses import StreamingResponse
    import io
    import csv
    query = {}
    if status: query["status"] = status
    cursor = guests_col.find(query).sort("created_at", -1)
    guests = [serialize_doc(doc) async for doc in cursor]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Ad", "Soyad", "Kimlik No", "Dogum Tarihi", "Cinsiyet", "Uyruk", "Belge Turu", "Durum", "Check-in", "Check-out", "Olusturma"])
    for g in guests:
        writer.writerow([g.get("first_name",""), g.get("last_name",""), g.get("id_number",""), g.get("birth_date",""),
                         g.get("gender",""), g.get("nationality",""), g.get("document_type",""), g.get("status",""),
                         g.get("check_in_at",""), g.get("check_out_at",""), g.get("created_at","")])
    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=misafirler.csv"})


# ===== KVKK COMPLIANCE (Tam Uyumluluk) =====

@app.post("/api/kvkk/rights-request", tags=["KVKK Uyumluluk"], summary="KVKK hak talebi oluştur",
          description="Misafir veya ilgili kişi adına KVKK hak talebi oluşturur (erişim, düzeltme, silme, taşıma, itiraz)")
async def create_kvkk_request(req: RightsRequestCreate, user=Depends(require_auth)):
    try:
        result = await create_rights_request(
            db,
            request_type=req.request_type,
            guest_id=req.guest_id,
            requester_name=req.requester_name,
            requester_email=req.requester_email,
            requester_id_number=req.requester_id_number,
            description=req.description,
            created_by=user.get("email")
        )
        return {"success": True, "request": serialize_doc(result)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/kvkk/rights-requests", tags=["KVKK Uyumluluk"], summary="KVKK hak taleplerini listele")
async def get_kvkk_requests(
    status: Optional[str] = None,
    request_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user=Depends(require_admin)
):
    result = await list_rights_requests(db, status=status, request_type=request_type, page=page, limit=limit)
    return result

@app.patch("/api/kvkk/rights-requests/{request_id}", tags=["KVKK Uyumluluk"], summary="KVKK hak talebini işle")
async def process_kvkk_request(request_id: str, req: RightsRequestProcess, user=Depends(require_admin)):
    try:
        result = await process_rights_request(
            db,
            request_id=request_id,
            new_status=req.status,
            response_note=req.response_note,
            response_data=req.response_data,
            processed_by=user.get("email")
        )
        if not result:
            raise HTTPException(status_code=404, detail="Talep bulunamadı")
        return {"success": True, "request": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/kvkk/guest-data/{guest_id}", tags=["KVKK Uyumluluk"], summary="Misafir veri erişim raporu",
         description="KVKK erişim hakkı kapsamında misafirin tüm kişisel verilerini derler")
async def get_guest_kvkk_data(guest_id: str, user=Depends(require_admin)):
    data = await get_guest_data_for_access(db, guest_id)
    if not data:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")
    return data

@app.get("/api/kvkk/guest-data/{guest_id}/portable", tags=["KVKK Uyumluluk"], summary="Veri taşınabilirlik dışa aktarımı",
         description="KVKK veri taşıma hakkı kapsamında misafir verilerini taşınabilir formatta dışa aktarır")
async def export_guest_portable(guest_id: str, user=Depends(require_admin)):
    data = await export_guest_data_portable(db, guest_id)
    if not data:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")
    return data

@app.get("/api/kvkk/verbis-report", tags=["KVKK Uyumluluk"], summary="VERBİS uyumluluk raporu",
         description="KVKK Madde 16 kapsamında VERBİS uyumluluk raporu üretir")
async def get_verbis_report(user=Depends(require_admin)):
    report = await generate_verbis_report(db)
    return report

@app.get("/api/kvkk/data-inventory", tags=["KVKK Uyumluluk"], summary="Veri işleme envanteri",
         description="Sistemdeki tüm veri koleksiyonları ve işleme detaylarının envanterini sunar")
async def get_kvkk_data_inventory(user=Depends(require_admin)):
    inventory = await get_data_inventory(db)
    return inventory

@app.get("/api/kvkk/retention-warnings", tags=["KVKK Uyumluluk"], summary="Saklama süresi uyarıları",
         description="Saklama süresine yaklaşan veya aşan veriler için uyarılar üretir")
async def get_kvkk_retention_warnings(user=Depends(require_admin)):
    warnings = await get_retention_warnings(db)
    return warnings


# ===== API GUIDE =====
@app.get("/api/guide", tags=["API Rehberi"], summary="API Entegrasyon Rehberi",
         description="PMS entegrasyonu ve dış sistemler için kapsamlı API rehberi")
async def get_api_guide():
    return {
        "title": "Quick ID Reader - API Entegrasyon Rehberi",
        "version": "3.0.0",
        "base_url": "Deployment'a göre değişir",
        "authentication": {
            "type": "Bearer Token (JWT)",
            "login_endpoint": "POST /api/auth/login",
            "request_body": {"email": "string", "password": "string"},
            "response": {"token": "jwt_token_string", "user": {"id": "...", "email": "...", "role": "admin|reception"}},
            "header_format": "Authorization: Bearer <token>",
            "token_expiry": "24 saat (varsayılan)"
        },
        "endpoints": {
            "kimlik_tarama": {
                "scan": {
                    "method": "POST",
                    "path": "/api/scan",
                    "description": "AI ile kimlik belgesi tarama (GPT-4o Vision)",
                    "request": {"image_base64": "base64_encoded_image_string"},
                    "response_fields": ["success", "scan", "extracted_data", "documents", "confidence"],
                    "rate_limit": "15/dakika",
                    "fallback": "AI başarısız olursa kullanıcıya yeniden çekim rehberliği"
                },
                "scans_list": {"method": "GET", "path": "/api/scans", "params": {"page": "int", "limit": "int"}},
                "review_queue": {"method": "GET", "path": "/api/scans/review-queue", "description": "Düşük güvenilirlik puanlı taramalar"},
            },
            "misafir_yonetimi": {
                "list": {"method": "GET", "path": "/api/guests", "params": ["page", "limit", "search", "status", "nationality", "document_type", "date_from", "date_to"]},
                "create": {"method": "POST", "path": "/api/guests", "body_fields": ["first_name", "last_name", "id_number", "birth_date", "gender", "nationality", "document_type", "kvkk_consent"]},
                "get": {"method": "GET", "path": "/api/guests/{id}"},
                "update": {"method": "PATCH", "path": "/api/guests/{id}"},
                "delete": {"method": "DELETE", "path": "/api/guests/{id}"},
                "checkin": {"method": "POST", "path": "/api/guests/{id}/checkin"},
                "checkout": {"method": "POST", "path": "/api/guests/{id}/checkout"},
                "duplicate_check": {"method": "GET", "path": "/api/guests/check-duplicate"},
            },
            "biyometrik": {
                "face_compare": {"method": "POST", "path": "/api/biometric/face-compare", "description": "Belge fotoğrafı vs canlı yüz karşılaştırma"},
                "liveness_challenge": {"method": "GET", "path": "/api/biometric/liveness-challenge", "description": "Canlılık testi sorusu al"},
                "liveness_check": {"method": "POST", "path": "/api/biometric/liveness-check", "description": "Canlılık testi doğrulama"},
            },
            "tc_kimlik": {
                "validate": {"method": "POST", "path": "/api/tc-kimlik/validate", "description": "TC Kimlik No doğrulama"},
                "emniyet_bildirimi": {"method": "POST", "path": "/api/tc-kimlik/emniyet-bildirimi", "description": "Yabancı misafir Emniyet bildirimi"},
            },
            "on_checkin": {
                "create_token": {"method": "POST", "path": "/api/precheckin/create", "description": "QR ön check-in token oluştur"},
                "get_token_info": {"method": "GET", "path": "/api/precheckin/{token_id}", "description": "Token bilgisi (public)"},
                "scan_with_token": {"method": "POST", "path": "/api/precheckin/{token_id}/scan", "description": "QR ile kimlik tara (public)"},
                "qr_code": {"method": "GET", "path": "/api/precheckin/{token_id}/qr", "description": "QR kod görüntüsü"},
                "list_tokens": {"method": "GET", "path": "/api/precheckin/list", "description": "Token listesi"},
            },
            "multi_property": {
                "list": {"method": "GET", "path": "/api/properties"},
                "create": {"method": "POST", "path": "/api/properties"},
                "get": {"method": "GET", "path": "/api/properties/{property_id}"},
                "update": {"method": "PATCH", "path": "/api/properties/{property_id}"},
            },
            "kiosk": {
                "create_session": {"method": "POST", "path": "/api/kiosk/session"},
                "list_sessions": {"method": "GET", "path": "/api/kiosk/sessions"},
            },
            "offline_sync": {
                "upload": {"method": "POST", "path": "/api/sync/upload"},
                "pending": {"method": "GET", "path": "/api/sync/pending"},
                "process": {"method": "POST", "path": "/api/sync/{sync_id}/process"},
            },
            "kvkk_uyumluluk": {
                "consent_info": {"method": "GET", "path": "/api/kvkk/consent-info", "description": "KVKK bilgilendirme metni (public)"},
                "settings": {"method": "GET/PATCH", "path": "/api/settings/kvkk"},
                "rights_request": {"method": "POST", "path": "/api/kvkk/rights-request"},
                "rights_list": {"method": "GET", "path": "/api/kvkk/rights-requests"},
                "verbis_report": {"method": "GET", "path": "/api/kvkk/verbis-report"},
                "data_inventory": {"method": "GET", "path": "/api/kvkk/data-inventory"},
                "retention_warnings": {"method": "GET", "path": "/api/kvkk/retention-warnings"},
            },
            "denetim": {
                "guest_audit": {"method": "GET", "path": "/api/guests/{id}/audit"},
                "recent_audit": {"method": "GET", "path": "/api/audit/recent"},
            },
            "dashboard": {"stats": {"method": "GET", "path": "/api/dashboard/stats"}},
            "disa_aktarim": {
                "json": {"method": "GET", "path": "/api/exports/guests.json"},
                "csv": {"method": "GET", "path": "/api/exports/guests.csv"},
            },
        },
        "pms_integration_guide": {
            "title": "PMS Entegrasyon Rehberi",
            "steps": [
                "1. POST /api/auth/login ile token alın",
                "2. POST /api/scan ile kimlik tarayın (base64 görüntü gönderin)",
                "3. POST /api/tc-kimlik/validate ile TC Kimlik doğrulayın (Türkiye vatandaşları)",
                "4. POST /api/biometric/face-compare ile yüz doğrulama yapın (opsiyonel)",
                "5. Dönen extracted_data ile POST /api/guests ile misafir oluşturun",
                "6. POST /api/guests/{id}/checkin ile check-in yapın",
                "7. Yabancı misafirler için POST /api/tc-kimlik/emniyet-bildirimi ile bildirim oluşturun",
                "8. POST /api/guests/{id}/checkout ile check-out yapın",
            ],
            "webhook_support": "Henüz desteklenmiyor - gelecek sürümde planlanıyor",
            "batch_operations": "Toplu tarama için /api/scan endpoint'ini ardışık çağırın",
        },
        "error_codes": {
            "400": "Geçersiz istek (eksik/hatalı parametre)",
            "401": "Kimlik doğrulama gerekli (token eksik/geçersiz)",
            "403": "Yetki yetersiz (admin yetkisi gerekli)",
            "404": "Kaynak bulunamadı",
            "429": "İstek limiti aşıldı (retry-after header'ına bakın)",
            "500": "Sunucu hatası (AI tarama hatası durumunda fallback_guidance alanını kontrol edin)",
        }
    }


# ===== KVKK PUBLIC CONSENT INFO =====
@app.get("/api/kvkk/consent-info", tags=["KVKK Uyumluluk"], summary="KVKK bilgilendirme metni (public)",
         description="Misafirlerin görmesi gereken KVKK aydınlatma metni. Kimlik doğrulama gerektirmez.")
async def get_kvkk_consent_info():
    """KVKK bilgilendirme ve açık rıza metni - herkes erişebilir"""
    settings = await get_settings(db)
    return {
        "consent_required": settings.get("kvkk_consent_required", True),
        "consent_text": settings.get("kvkk_consent_text", """
KVKK AYDINLATMA METNİ

6698 Sayılı Kişisel Verilerin Korunması Kanunu kapsamında, otelimizde konaklama hizmeti alırken aşağıdaki kişisel verileriniz işlenmektedir:

İŞLENEN VERİLER:
• Kimlik Bilgileri: Ad, soyad, TC kimlik no/pasaport no, doğum tarihi, cinsiyet, uyruk
• Belge Bilgileri: Kimlik belgesi türü, belge numarası, geçerlilik tarihi
• Konaklama Bilgileri: Giriş-çıkış tarihleri
• Biyometrik Veri: Kimlik belgesi görüntüsü (sadece tarama amacıyla, saklanmaz*)

İŞLEME AMACI:
1. Konaklama hizmeti sunumu (Yasal zorunluluk - 1774 sayılı Kimlik Bildirme Kanunu)
2. Emniyet Müdürlüğü bildirimi (Yasal zorunluluk - 5682 sayılı Pasaport Kanunu)
3. Kimlik doğrulama (AI destekli belge okuma)

HUKUKİ DAYANAK:
• KVKK Madde 5/2-ç: Veri sorumlusunun hukuki yükümlülüğü
• KVKK Madde 5/2-c: Sözleşmenin ifası

VERİ AKTARIMI:
• Emniyet Müdürlüğü (yasal zorunluluk)
• OpenAI API (kimlik tarama işleme, veri saklanmaz)

SAKLAMA SÜRESİ:
• Kişisel veriler: Konaklama süresi + yasal saklama süresi
• Kimlik görüntüleri: Tarama sonrası saklanmaz*

HAKLARINIZ (KVKK Madde 11):
1. Kişisel verilerinizin işlenip işlenmediğini öğrenme
2. Kişisel verileriniz işlenmişse bilgi talep etme
3. İşlenme amacını öğrenme
4. Yurt içinde/dışında aktarıldığı kişileri bilme
5. Eksik/yanlış işlenmişse düzeltme talep etme
6. Silinme/yok edilme talep etme
7. Düzeltme/silinme işlemlerinin aktarıldığı kişilere bildirilmesini talep etme
8. İtiraz etme
9. Zarar halinde tazminat talep etme

Haklarınızı kullanmak için resepsiyon yetkilisine başvurabilirsiniz.
        """),
        "data_processing_purpose": settings.get("data_processing_purpose", "Konaklama hizmeti kapsamında yasal zorunluluk"),
        "data_controller": {
            "title": "Veri Sorumlusu",
            "note": "Otel İşletmesi"
        },
        "rights": [
            {"code": "access", "title": "Erişim Hakkı", "description": "Kişisel verilerinize erişim talep edebilirsiniz"},
            {"code": "rectification", "title": "Düzeltme Hakkı", "description": "Yanlış/eksik verilerin düzeltilmesini talep edebilirsiniz"},
            {"code": "erasure", "title": "Silme Hakkı", "description": "Verilerinizin silinmesini talep edebilirsiniz"},
            {"code": "portability", "title": "Taşıma Hakkı", "description": "Verilerinizi taşınabilir formatta alabilirsiniz"},
            {"code": "objection", "title": "İtiraz Hakkı", "description": "Veri işlemeye itiraz edebilirsiniz"},
        ],
    }


# ===== BIOMETRIC FACE MATCHING =====
# ===== TC KIMLIK VALIDATION =====
@app.post("/api/tc-kimlik/validate", tags=["TC Kimlik"], summary="TC Kimlik No doğrulama",
          description="TC Kimlik No'nun geçerliliğini matematiksel algoritma ile kontrol eder")
async def validate_tc(req: TcKimlikValidateRequest, user=Depends(require_auth)):
    result = validate_tc_kimlik(req.tc_no)
    return result


@app.post("/api/tc-kimlik/emniyet-bildirimi", tags=["TC Kimlik"], summary="Emniyet bildirimi oluştur",
          description="Yabancı uyruklu misafir için Emniyet Müdürlüğü bildirim formu otomatik doldurur")
async def create_emniyet_bildirimi(req: EmniyetBildirimiRequest, user=Depends(require_auth)):
    try:
        guest = await guests_col.find_one({"_id": ObjectId(req.guest_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz misafir ID")
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")
    
    guest_data = serialize_doc(guest)
    
    # Check if foreign guest
    if not is_foreign_guest(guest_data.get("nationality", "")):
        raise HTTPException(status_code=400, detail="Bu misafir yabancı uyruklu değil. Emniyet bildirimi sadece yabancı misafirler için gereklidir.")
    
    # Get property/hotel data if available
    hotel_data = None
    properties = await list_properties(db, is_active=True)
    if properties:
        hotel_data = {
            "hotel_name": properties[0].get("name", ""),
            "hotel_address": properties[0].get("address", ""),
            "hotel_phone": properties[0].get("phone", ""),
            "hotel_tax_no": properties[0].get("tax_no", ""),
        }
    
    form = generate_emniyet_bildirimi(guest_data, hotel_data)
    
    # Store the form
    form["guest_id"] = req.guest_id
    form["created_by"] = user.get("email")
    await db["emniyet_bildirimleri"].insert_one(form)
    
    # Create audit log
    await create_audit_log(req.guest_id, "emniyet_bildirimi_created", 
                           metadata={"form_id": form["form_id"]}, 
                           user_email=user.get("email"))
    
    return {"success": True, "form": form}


@app.get("/api/tc-kimlik/emniyet-bildirimleri", tags=["TC Kimlik"], summary="Emniyet bildirimleri listesi")
async def list_emniyet_bildirimleri(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user=Depends(require_auth)
):
    query = {}
    if status:
        query["status"] = status
    total = await db["emniyet_bildirimleri"].count_documents(query)
    skip = (page - 1) * limit
    cursor = db["emniyet_bildirimleri"].find(query).sort("created_at", -1).skip(skip).limit(limit)
    forms = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        forms.append(doc)
    return {"forms": forms, "total": total, "page": page, "limit": limit}




# ===== ROOM MANAGEMENT =====
@app.post("/api/rooms", tags=["Oda Yönetimi"], summary="Yeni oda oluştur")
async def create_new_room(req: RoomCreate, user=Depends(require_admin)):
    try:
        room = await create_room(
            db, room_number=req.room_number, room_type=req.room_type,
            floor=req.floor, capacity=req.capacity,
            property_id=req.property_id, features=req.features
        )
        return {"success": True, "room": room}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/rooms", tags=["Oda Yönetimi"], summary="Odaları listele")
async def get_rooms(
    property_id: Optional[str] = None,
    status: Optional[str] = None,
    room_type: Optional[str] = None,
    floor: Optional[int] = None,
    user=Depends(require_auth)
):
    rooms = await list_rooms(db, property_id=property_id, status=status,
                             room_type=room_type, floor=floor)
    return {"rooms": rooms, "total": len(rooms)}


@app.get("/api/rooms/types", tags=["Oda Yönetimi"], summary="Oda tipleri")
async def get_room_types():
    return {"room_types": ROOM_TYPES, "statuses": ROOM_STATUSES}


@app.get("/api/rooms/stats", tags=["Oda Yönetimi"], summary="Oda istatistikleri")
async def get_rooms_stats(property_id: Optional[str] = None, user=Depends(require_auth)):
    stats = await get_room_stats(db, property_id=property_id)
    return stats


@app.get("/api/rooms/{room_id}", tags=["Oda Yönetimi"], summary="Oda detayı")
async def get_room_detail(room_id: str, user=Depends(require_auth)):
    room = await get_room(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Oda bulunamadı")
    return {"room": room}


@app.patch("/api/rooms/{room_id}", tags=["Oda Yönetimi"], summary="Oda güncelle")
async def update_room_endpoint(room_id: str, req: RoomUpdate, user=Depends(require_admin)):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    room = await update_room(db, room_id, updates)
    if not room:
        raise HTTPException(status_code=404, detail="Oda bulunamadı")
    return {"success": True, "room": room}


@app.post("/api/rooms/assign", tags=["Oda Yönetimi"], summary="Oda ata",
          description="Belirtilen misafire oda atar")
async def assign_room_endpoint(req: RoomAssignRequest, user=Depends(require_auth)):
    try:
        result = await assign_room(db, room_id=req.room_id, guest_id=req.guest_id)
        room_data = result.get("room", {})
        assignment_data = result.get("assignment", {})
        await create_audit_log(req.guest_id, "room_assigned",
                               metadata={"room_id": req.room_id, "room_number": room_data.get("room_number", "")},
                               user_email=user.get("email"))
        return {"success": True, "room": room_data, "assignment": assignment_data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Oda atama hatası: {str(e)}")


@app.post("/api/rooms/auto-assign", tags=["Oda Yönetimi"], summary="Otomatik oda ata",
          description="Scan sonrası müsait odayı otomatik atar")
async def auto_assign_room_endpoint(req: AutoAssignRequest, user=Depends(require_auth)):
    try:
        result = await auto_assign_room(db, guest_id=req.guest_id,
                                         property_id=req.property_id,
                                         preferred_type=req.preferred_type)
        if not result:
            raise HTTPException(status_code=404, detail="Müsait oda bulunamadı")
        room_data = result.get("room", {})
        assignment_data = result.get("assignment", {})
        await create_audit_log(req.guest_id, "room_auto_assigned",
                               metadata={"room_id": room_data.get("room_id", ""), "room_number": room_data.get("room_number", "")},
                               user_email=user.get("email"))
        return {"success": True, "room": room_data, "assignment": assignment_data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Otomatik oda atama hatası: {str(e)}")


@app.post("/api/rooms/{room_id}/release", tags=["Oda Yönetimi"], summary="Odayı serbest bırak")
async def release_room_endpoint(room_id: str, guest_id: Optional[str] = None, user=Depends(require_auth)):
    try:
        room = await release_room(db, room_id=room_id, guest_id=guest_id)
        return {"success": True, "room": room}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===== GROUP CHECK-IN =====
@app.post("/api/guests/group-checkin", tags=["Grup Check-in"], summary="Grup check-in",
          description="Birden fazla misafiri tek işlemde kayıt eder ve opsiyonel oda atar")
async def group_checkin(req: GroupCheckinRequest, user=Depends(require_auth)):
    results = {"successful": [], "failed": [], "room_assignment": None}
    
    for guest_id in req.guest_ids:
        try:
            oid = ObjectId(guest_id)
            old_doc = await guests_col.find_one({"_id": oid})
            if not old_doc:
                results["failed"].append({"guest_id": guest_id, "error": "Misafir bulunamadı"})
                continue
            
            now = datetime.now(timezone.utc)
            await guests_col.update_one(
                {"_id": oid},
                {"$set": {"status": "checked_in", "check_in_at": now, "updated_at": now}}
            )
            await create_audit_log(guest_id, "group_checked_in",
                                   {"status": {"old": old_doc.get("status"), "new": "checked_in"}},
                                   metadata={"group_checkin": True, "group_size": len(req.guest_ids)},
                                   user_email=user.get("email"))
            
            doc = await guests_col.find_one({"_id": oid})
            results["successful"].append(serialize_doc(doc))
        except Exception as e:
            results["failed"].append({"guest_id": guest_id, "error": str(e)})
    
    # Auto-assign room if requested
    if req.room_id and results["successful"]:
        try:
            for guest in results["successful"]:
                await assign_room(db, room_id=req.room_id, guest_id=guest["id"])
            room = await get_room(db, req.room_id)
            results["room_assignment"] = {"success": True, "room": room}
        except Exception as e:
            results["room_assignment"] = {"success": False, "error": str(e)}
    
    return {
        "success": len(results["successful"]) > 0,
        "total_requested": len(req.guest_ids),
        "successful_count": len(results["successful"]),
        "failed_count": len(results["failed"]),
        "results": results,
    }


# ===== GUEST PHOTO =====
@app.post("/api/guests/{guest_id}/photo", tags=["Misafirler"], summary="Misafir fotoğrafı yükle",
          description="Check-in sırasında misafir fotoğrafı çeker ve kaydeder")
@limiter.limit("20/minute")
async def upload_guest_photo(request: Request, guest_id: str, req: GuestPhotoRequest, user=Depends(require_auth)):
    # Image size validation
    if len(req.image_base64) > MAX_IMAGE_BASE64_LENGTH:
        raise HTTPException(status_code=413, detail=f"Fotoğraf boyutu çok büyük. Maksimum {MAX_IMAGE_BASE64_LENGTH // (1024*1024)}MB izin verilir.")

    # v50 (Bug CK): magic-byte validation — reject empty / SVG / HTML / EXE /
    # arbitrary text. Previously any string was accepted and stored verbatim,
    # enabling DB bloat, audit-trail integrity loss and stored-XSS via downstream
    # data: URL rendering. Validator strips a single optional data:image/...
    # prefix and enforces JPEG/PNG/WEBP/GIF magic-byte allowlist.
    raw_bytes, mime = _validate_image_payload(req.image_base64)

    try:
        oid = ObjectId(guest_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz misafir ID")
    
    guest = await guests_col.find_one({"_id": oid})
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")
    
    # Image quality check
    quality = assess_image_quality(req.image_base64)

    # v51 (Bug CL): photo overwrite forensic trail. Pre-v51 herhangi bir
    # reception, başka bir reception'ın yüklediği fotoğrafı sessizce üzerine
    # yazabiliyordu — audit'te `old_data={}` `new_data={}` boş kalıyor, kimin
    # değiştirdiği/önceki fotoğrafın kime ait olduğu DURABLE şekilde bilinmiyordu.
    # Şimdi: overwrite tespit edilince action="photo_overwritten" + eski/yeni
    # captured_by + captured_at + sha256 + size diff'i audit_logs'a yazılır.
    # v51 Round-2 (architect concurrency fix): pre-image atomically read via
    # find_one_and_update(return_document=BEFORE) — eski kod find_one+update_one
    # arasında race window bırakıyordu (iki concurrent override aynı pre-image'ı
    # görüp aynı old_data'yı log ederek forensic chain'i kırardı).
    import hashlib
    from pymongo import ReturnDocument
    new_hash = hashlib.sha256(raw_bytes).hexdigest()
    new_size = len(raw_bytes)
    new_captured_at = datetime.now(timezone.utc)
    user_email = user.get("email")

    # Atomic compare-and-set: returns the document AS IT WAS before the update.
    # Two concurrent calls cannot observe identical pre-images.
    pre_doc = await guests_col.find_one_and_update(
        {"_id": oid},
        {"$set": {
            "has_photo": True,
            "photo_captured_at": new_captured_at,
            "photo_captured_by": user_email,
            "photo_sha256": new_hash,
            "photo_size_bytes": new_size,
            "photo_base64": req.image_base64,
            "updated_at": new_captured_at,
        }},
        return_document=ReturnDocument.BEFORE,
    )
    if not pre_doc:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")

    is_overwrite = bool(pre_doc.get("has_photo")) and bool(pre_doc.get("photo_base64"))
    old_data = {}
    if is_overwrite:
        old_data = {
            "captured_by": pre_doc.get("photo_captured_by"),
            "captured_at": (pre_doc.get("photo_captured_at").isoformat()
                            if isinstance(pre_doc.get("photo_captured_at"), datetime) else None),
            "sha256": pre_doc.get("photo_sha256"),
            "size_bytes": pre_doc.get("photo_size_bytes"),
        }

    # Store photo log entry (small audit doc, separate from main forensic audit_logs)
    photo_doc = {
        "photo_id": str(uuid.uuid4()),
        "guest_id": guest_id,
        "image_base64": req.image_base64[:100] + "...",  # truncate for log brevity
        "quality": quality,
        "captured_at": new_captured_at,
        "captured_by": user_email,
    }

    new_data = {
        "captured_by": user_email,
        "captured_at": new_captured_at.isoformat(),
        "sha256": new_hash,
        "size_bytes": new_size,
    }

    action = "photo_overwritten" if is_overwrite else "photo_captured"
    await create_audit_log(guest_id, action,
                           old_data=old_data, new_data=new_data,
                           metadata={"quality": quality.get("overall_quality", "unknown"),
                                     "mime": mime, "is_overwrite": is_overwrite},
                           user_email=user_email)
    
    return {
        "success": True,
        "photo_id": photo_doc["photo_id"],
        "quality": quality,
        "message": "Misafir fotoğrafı başarıyla kaydedildi",
    }


@app.get("/api/guests/{guest_id}/photo", tags=["Misafirler"], summary="Misafir fotoğrafı getir")
async def get_guest_photo(guest_id: str, user=Depends(require_auth)):
    try:
        oid = ObjectId(guest_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz misafir ID")
    
    guest = await guests_col.find_one({"_id": oid})
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")
    
    if not guest.get("photo_base64"):
        raise HTTPException(status_code=404, detail="Misafir fotoğrafı bulunamadı")
    
    return {
        "success": True,
        "guest_id": guest_id,
        "has_photo": True,
        "photo_base64": guest["photo_base64"],
        "photo_captured_at": guest.get("photo_captured_at", "").isoformat() if isinstance(guest.get("photo_captured_at"), datetime) else str(guest.get("photo_captured_at", "")),
    }


# ===== FORM-C (Emniyet Bildirim Formatı) =====
@app.get("/api/tc-kimlik/form-c/{guest_id}", tags=["TC Kimlik"], summary="Form-C oluştur",
         description="Emniyet Müdürlüğü Form-C (yabancı misafir bildirim formu) formatında rapor oluşturur")
async def generate_form_c(guest_id: str, user=Depends(require_auth)):
    try:
        guest = await guests_col.find_one({"_id": ObjectId(guest_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz misafir ID")
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")
    
    guest_data = serialize_doc(guest)
    
    # Get property info
    properties = await list_properties(db, is_active=True)
    hotel_data = None
    if properties:
        hotel_data = {
            "hotel_name": properties[0].get("name", ""),
            "hotel_address": properties[0].get("address", ""),
            "hotel_phone": properties[0].get("phone", ""),
            "hotel_tax_no": properties[0].get("tax_no", ""),
        }
    
    form_c = {
        "form_type": "FORM-C",
        "form_title": "YABANCI KONAKLAMA BİLDİRİM FORMU (FORM-C)",
        "yasal_dayanak": "5682 Sayılı Pasaport Kanunu Madde 18, 6458 Sayılı YÜKK",
        "bildirim_suresi": "Konaklama başlangıcından itibaren 24 saat",
        
        "tesis_bilgileri": {
            "tesis_adi": hotel_data.get("hotel_name", "") if hotel_data else "",
            "tesis_adresi": hotel_data.get("hotel_address", "") if hotel_data else "",
            "tesis_telefon": hotel_data.get("hotel_phone", "") if hotel_data else "",
            "vergi_no": hotel_data.get("hotel_tax_no", "") if hotel_data else "",
        },
        
        "misafir_bilgileri": {
            "sira_no": 1,
            "adi": guest_data.get("first_name", ""),
            "soyadi": guest_data.get("last_name", ""),
            "baba_adi": guest_data.get("father_name", ""),
            "ana_adi": guest_data.get("mother_name", ""),
            "dogum_tarihi": guest_data.get("birth_date", ""),
            "dogum_yeri": guest_data.get("birth_place", ""),
            "uyrugu": guest_data.get("nationality", ""),
            "cinsiyeti": "Erkek" if guest_data.get("gender") == "M" else "Kadın" if guest_data.get("gender") == "F" else "",
        },
        
        "belge_bilgileri": {
            "belge_turu": guest_data.get("document_type", ""),
            "belge_no": guest_data.get("document_number", "") or guest_data.get("id_number", ""),
            "belge_verilis_tarihi": guest_data.get("issue_date", ""),
            "belge_gecerlilik_tarihi": guest_data.get("expiry_date", ""),
            "vize_turu": "",
            "vize_no": "",
        },
        
        "konaklama_bilgileri": {
            "giris_tarihi": guest_data.get("check_in_at", ""),
            "tahmini_cikis_tarihi": guest_data.get("check_out_at", ""),
            "oda_no": guest_data.get("room_number", ""),
            "gelis_sebebi": "Turizm",
        },
        
        "duzenleme_bilgileri": {
            "duzenleme_tarihi": datetime.now(timezone.utc).isoformat(),
            "duzenleyen": user.get("email", ""),
            "imza": "",
        },
        
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "guest_id": guest_id,
        "status": "generated",
    }
    
    # Store Form-C
    await db["form_c_records"].insert_one({**form_c, "created_at": datetime.now(timezone.utc)})
    
    return {"success": True, "form_c": form_c}


# ===== YASAL UYUMLULUK RAPORLARI =====
@app.get("/api/compliance/reports", tags=["KVKK Uyumluluk"], summary="Yasal uyumluluk raporları",
         description="Emniyet bildirimi, KVKK ve konaklama yasal uyumluluk raporları")
async def get_compliance_reports(user=Depends(require_admin)):
    # Emniyet bildirimleri
    emniyet_col = db["emniyet_bildirimleri"]
    total_emniyet = await emniyet_col.count_documents({})
    draft_emniyet = await emniyet_col.count_documents({"status": "draft"})
    submitted_emniyet = await emniyet_col.count_documents({"status": "submitted"})
    
    # Form-C records
    form_c_col = db["form_c_records"]
    total_form_c = await form_c_col.count_documents({})
    
    # KVKK rights requests
    kvkk_col = db["kvkk_rights_requests"]
    total_kvkk = await kvkk_col.count_documents({})
    pending_kvkk = await kvkk_col.count_documents({"status": "pending"})
    completed_kvkk = await kvkk_col.count_documents({"status": "completed"})
    
    # Foreign guests without notification
    foreign_guests = await guests_col.count_documents({
        "nationality": {"$nin": ["TC", "TR", "Türkiye", "Turkey", "Türk", "Turkish", "T.C."], "$ne": None, "$exists": True},
    })
    
    return {
        "emniyet_bildirimleri": {
            "toplam": total_emniyet,
            "taslak": draft_emniyet,
            "gonderilmis": submitted_emniyet,
        },
        "form_c": {
            "toplam": total_form_c,
        },
        "kvkk": {
            "toplam_talep": total_kvkk,
            "bekleyen": pending_kvkk,
            "tamamlanan": completed_kvkk,
        },
        "yabanci_misafir": {
            "toplam": foreign_guests,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ===== MONITORING DASHBOARD =====
# ===== BACKUP & RESTORE =====
@app.post("/api/admin/backup", tags=["Yedekleme"], summary="Veritabanı yedeği oluştur")
async def create_db_backup(req: BackupCreateRequest, user=Depends(require_admin)):
    try:
        result = await create_backup(db, created_by=user.get("email"), description=req.description)
        return {"success": True, "backup": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Yedekleme hatası: {str(e)}")


@app.get("/api/admin/backups", tags=["Yedekleme"], summary="Yedek listesi")
async def get_backups(user=Depends(require_admin)):
    backups = await list_backups(db)
    return {"backups": backups, "total": len(backups)}


@app.post("/api/admin/restore", tags=["Yedekleme"], summary="Yedekten geri yükle",
          description="DİKKAT: Mevcut verilerin üzerine yazar!")
@limiter.limit("3/hour")
async def restore_db_backup(request: Request, req: BackupRestoreRequest, user=Depends(require_admin)):
    # v109 Bug DAJ round-3 (architect P1): backup restore can drop+rebuild
    # `audit_logs` (backup_restore.py:145-155) → compromised admin token can
    # rewind/erase forensic history. Defense layers:
    # 1. ENABLE_BACKUP_RESTORE env kill-switch (default disabled in production).
    # 2. Aggressive rate limit (3/hour) — operational ops far below this.
    # 3. Pre-restore audit log entry to current `audit_logs` (best-effort
    #    record of who attempted restore; lost after drop, BUT also written
    #    to server-side log file via logger.warning so on-disk evidence
    #    survives DB rewind).
    # 4. Post-restore audit log entry written AFTER restore completes (lives
    #    in new audit_logs collection; if attacker had inserted forged history
    #    via crafted backup, this row is the clear marker of the rewind moment).
    actor_id = user.get("sub"); actor_email = user.get("email")
    ip = request.client.host if request and request.client else None

    if os.environ.get("ENABLE_BACKUP_RESTORE", "0") != "1":
        await create_auth_audit_log("backup_restore_blocked",
            actor_id=actor_id, actor_email=actor_email,
            outcome="blocked", reason="ENABLE_BACKUP_RESTORE env not set",
            metadata={"backup_id": req.backup_id}, ip_address=ip)
        logger.warning(
            "BACKUP_RESTORE_BLOCKED actor=%s ip=%s backup_id=%s reason=env-disabled",
            actor_email, ip, req.backup_id,
        )
        raise HTTPException(
            status_code=403,
            detail="Geri yukleme bu ortamda devre disi. Aktiflestirme deploy zamani gerekir."
        )

    # Pre-restore: write to current audit_logs (best-effort) AND server-side log.
    # The server-side log line is on-disk forensic evidence that survives any
    # DB rewind via restore — attacker controls DB, not the file system log.
    await create_auth_audit_log("backup_restore_initiated",
        actor_id=actor_id, actor_email=actor_email,
        outcome="initiated", metadata={"backup_id": req.backup_id}, ip_address=ip)
    logger.warning(
        "BACKUP_RESTORE_INITIATED actor=%s ip=%s backup_id=%s — DB will be rewritten",
        actor_email, ip, req.backup_id,
    )

    try:
        result = await restore_backup(db, backup_id=req.backup_id, restore_by=actor_email)
    except ValueError as e:
        await create_auth_audit_log("backup_restore_failed",
            actor_id=actor_id, actor_email=actor_email,
            outcome="failed", reason=str(e),
            metadata={"backup_id": req.backup_id}, ip_address=ip)
        logger.warning(
            "BACKUP_RESTORE_FAILED actor=%s backup_id=%s err=%s",
            actor_email, req.backup_id, e,
        )
        raise HTTPException(status_code=404, detail=str(e))

    # Post-restore: write into the NEW audit_logs collection. If restore
    # rewound history, this row marks the rewind point so forensics can detect
    # the gap (compare with on-disk server log "BACKUP_RESTORE_INITIATED" line).
    await create_auth_audit_log("backup_restore_completed",
        actor_id=actor_id, actor_email=actor_email,
        outcome="success",
        metadata={"backup_id": req.backup_id, "stats": result.get("stats", {})},
        ip_address=ip)
    logger.warning(
        "BACKUP_RESTORE_COMPLETED actor=%s backup_id=%s stats=%s",
        actor_email, req.backup_id, result.get("stats", {}),
    )
    return result


@app.get("/api/admin/backup-schedule", tags=["Yedekleme"], summary="Yedekleme planı")
async def backup_schedule(user=Depends(require_admin)):
    return get_backup_schedule()


# ===== OCR FALLBACK =====
@app.post("/api/scan/ocr-fallback", tags=["OCR"], summary="Offline OCR tarama (Tesseract)",
          description="İnternet kesintisinde lokal Tesseract OCR ile kimlik belgesi tarama. Geliştirilmiş ön işleme ile.")
@limiter.limit("30/minute")
async def ocr_fallback_scan(request: Request, scan_req: ScanRequest, user=Depends(require_auth)):
    # v52 (Bug CM): shared validator reuse — pre-v52 bu uç payload'u doğrulamadan
    # Tesseract'a/quality-check'e veriyordu; HTML/SVG/junk DoS + integrity kayıpları.
    _validate_image_payload(scan_req.image_base64)
    if not is_tesseract_available():
        raise HTTPException(status_code=503, detail="Tesseract OCR sistemi mevcut değil")

    # Image quality check first
    quality = assess_image_quality(scan_req.image_base64)
    
    result = ocr_scan_document(scan_req.image_base64)
    
    if not result.get("success"):
        scan_doc = {
            "status": "failed",
            "error": result.get("error", "OCR hatası"),
            "source": "tesseract_ocr",
            "created_at": datetime.now(timezone.utc),
            "scanned_by": user.get("email"),
            "image_quality": quality,
        }
        await scans_col.insert_one(scan_doc)
        raise HTTPException(status_code=500, detail={
            "message": result.get("error", "OCR tarama başarısız"),
            "image_quality": quality,
            "can_retry": True,
        })
    
    # OCR güven puanı
    ocr_confidence = result.get("confidence", {})
    
    # Store scan
    scan_doc = {
        "extracted_data": {"documents": result.get("documents", []), "document_count": result.get("document_count", 0)},
        "document_count": result.get("document_count", 0),
        "is_valid": any(d.get("is_valid", False) for d in result.get("documents", [])),
        "created_at": datetime.now(timezone.utc),
        "status": "completed",
        "source": "tesseract_ocr",
        "scanned_by": user.get("email"),
        "confidence_level": ocr_confidence.get("confidence_level", "low"),
        "confidence_score": ocr_confidence.get("confidence_score", 40),
        "review_status": "needs_review",
        "image_quality": quality,
        "warnings": ["Offline OCR ile tarandı - sonuçları doğrulayın"],
        "provider": "tesseract",
        "preprocessing_applied": result.get("preprocessing_applied", False),
    }
    await scans_col.insert_one(scan_doc)
    
    return {
        "success": True,
        "source": "tesseract_ocr",
        "documents": result.get("documents", []),
        "raw_text": result.get("raw_text", ""),
        "image_quality": quality,
        "confidence": ocr_confidence,
        "confidence_note": result.get("confidence_note", ""),
        "preprocessing_applied": result.get("preprocessing_applied", False),
        "message": "Offline OCR tarama tamamlandı. Sonuçları doğrulayın.",
    }


@app.post("/api/scan/quality-check", tags=["OCR"], summary="Görüntü kalite kontrolü (geliştirilmiş)",
          description="Tarama öncesi geliştirilmiş görüntü kalite kontrolü: bulanıklık, karanlık, çözünürlük, parlama, kenar tespiti, eğiklik")
@limiter.limit("30/minute")
async def image_quality_check(request: Request, scan_req: ScanRequest, user=Depends(require_auth)):
    # v52 (Bug CM): pre-v52 bu uç (a) HİÇ rate-limit'siz, (b) HİÇ validator'sız idi —
    # sessizce {quality_checked:false} 200 dönerek HTML/empty/junk payload'ları
    # kabul ediyor, ayrıca 36MP decompression-bomb'ı OpenCV decode ediyordu.
    # Şimdi: shared validator + 30/minute rate limit.
    _validate_image_payload(scan_req.image_base64)
    quality = assess_image_quality(scan_req.image_base64)
    return quality


@app.get("/api/scan/ocr-status", tags=["OCR"], summary="OCR sistem durumu")
async def ocr_system_status():
    return {
        "tesseract_available": is_tesseract_available(),
        "supported_languages": ["tur", "eng"],
        "note": "Tesseract OCR internet kesintisinde yedek olarak kullanılabilir",
        "preprocessing": {
            "opencv_available": True,
            "features": ["deskew", "noise_reduction", "contrast_enhancement", "adaptive_threshold"],
        },
    }


@app.get("/api/scan/providers", tags=["OCR"], summary="Kullanılabilir AI sağlayıcıları",
         description="Kimlik tarama için kullanılabilir AI sağlayıcılarını listeler")
async def get_scan_providers():
    providers = list_providers()
    stats = get_provider_stats()
    return {
        "providers": providers,
        "stats": stats,
        "smart_routing": {
            "enabled": True,
            "description": "Görüntü kalitesine göre otomatik provider seçimi",
            "rules": {
                "high_quality": "Ucuz/hızlı provider (GPT-4o-mini veya Gemini Flash)",
                "medium_quality": "Orta seviye provider",
                "low_quality": "En yüksek doğruluklu provider (GPT-4o)",
            },
        },
        "tesseract": {
            "available": is_tesseract_available(),
            "role": "Offline fallback - internet kesintisinde otomatik devreye girer",
        },
    }


@app.get("/api/scan/cost-estimate/{provider_id}", tags=["OCR"], summary="Tarama maliyet tahmini")
async def scan_cost_estimate(provider_id: str):
    estimate = estimate_scan_cost(provider_id)
    if "error" in estimate:
        raise HTTPException(status_code=404, detail=estimate["error"])
    return estimate


# ===== PDF REPORTS =====
@app.get("/api/reports/form-c/{guest_id}/pdf", tags=["Raporlar"], summary="Form-C PDF indir")
async def download_form_c_pdf(guest_id: str, user=Depends(require_auth)):
    try:
        oid = ObjectId(guest_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Gecersiz misafir ID")
    guest = await guests_col.find_one({"_id": oid})
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")

    guest_data = serialize_doc(guest)
    guest_data["check_in_date"] = guest_data.get("check_in_at", "")[:10] if guest_data.get("check_in_at") else ""
    guest_data["check_out_date"] = guest_data.get("check_out_at", "")[:10] if guest_data.get("check_out_at") else ""
    guest_data["form_number"] = f"FC-{guest_id[:8].upper()}"

    pdf_bytes = generate_form_c_pdf(guest_data)
    filename = f"form_c_{guest_data.get('last_name', 'misafir')}_{datetime.now().strftime('%Y%m%d')}.pdf"
    logger.info(f"PDF Form-C olusturuldu: {guest_id} by {user.get('email')}")
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.get("/api/reports/guests/pdf", tags=["Raporlar"], summary="Misafir listesi PDF")
async def download_guest_list_pdf(
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user=Depends(require_auth)
):
    query = {"status": {"$ne": "deleted"}}
    if status:
        query["status"] = status
    if date_from:
        try:
            query.setdefault("created_at", {})["$gte"] = datetime.fromisoformat(date_from)
        except ValueError:
            pass
    if date_to:
        try:
            query.setdefault("created_at", {})["$lte"] = datetime.fromisoformat(date_to)
        except ValueError:
            pass

    cursor = guests_col.find(query).sort("created_at", -1).limit(500)
    guests = [serialize_doc(doc) async for doc in cursor]

    title = "Misafir Listesi"
    if status:
        status_labels = {"checked_in": "Giris Yapan", "checked_out": "Cikis Yapan", "pending": "Bekleyen"}
        title = f"{status_labels.get(status, status)} Misafirler"

    pdf_bytes = generate_guest_list_pdf(guests, title)
    filename = f"misafir_listesi_{datetime.now().strftime('%Y%m%d')}.pdf"
    logger.info(f"PDF Misafir listesi olusturuldu: {len(guests)} misafir by {user.get('email')}")
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


# ===== EMAIL STATUS =====
@app.get("/api/admin/email-status", tags=["E-posta"], summary="E-posta servis durumu")
async def email_status_endpoint(user=Depends(require_admin)):
    return get_email_status()


@app.get("/api/admin/email-log", tags=["E-posta"], summary="E-posta gonderim logu")
async def email_log_endpoint(limit: int = Query(50, ge=1, le=200), user=Depends(require_admin)):
    return {"emails": get_email_log(limit), "total": len(get_email_log(limit))}


@app.post("/api/admin/email-test", tags=["E-posta"], summary="Test e-postasi gonder")
async def send_test_email(user=Depends(require_admin)):
    result = await send_email(
        to=user.get("email", "admin@quickid.com"),
        subject="Quick ID - Test E-postasi",
        body_html="<h2>Test basarili!</h2><p>E-posta servisi calisiyor.</p>",
        template_name="test",
    )
    return {"success": True, "result": result}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("BACKEND_PORT", "8099"))
    uvicorn.run(app, host="0.0.0.0", port=port)
