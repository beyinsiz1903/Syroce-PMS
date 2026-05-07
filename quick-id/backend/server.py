"""Quick ID Reader API — FastAPI app entry.

Refactor R3a: split monolithic server.py into:
  - db.py          : Mongo client + collections
  - schemas.py     : Pydantic request models + constants (MAX_IMAGE_BASE64_LENGTH, ID_EXTRACTION_PROMPT)
  - middleware.py  : SecurityHeaders / CSRF / RequestSizeLimit + exception handlers
  - helpers.py     : serialize_doc, image-validate, audit, throttle, find_duplicates, extract_id_data
This file keeps only app construction + lifespan + route handlers.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import logging
from datetime import datetime, timezone, timedelta
from slowapi.errors import RateLimitExceeded

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
from middleware import (  # noqa: E402
    SecurityHeadersMiddleware, CSRFProtectionMiddleware, RequestSizeLimitMiddleware,
    rate_limit_handler, generic_exception_handler,
)

# --- External feature modules (unchanged) ---
from auth import hash_password, verify_password  # noqa: E402
from backup_restore import create_backup  # noqa: E402
from kvkk import get_settings, run_data_cleanup  # noqa: E402

# --- Rate limiter ---
from rate_limit import limiter  # noqa: E402  shared singleton (also used by routers/*)

# --- FastAPI app ---
@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Forward reference: _run_startup_tasks is defined further down in this
    # module. Lookup happens at call time (during ASGI startup), so the
    # forward reference is safe.
    await _run_startup_tasks()
    yield


app = FastAPI(
    lifespan=_lifespan,
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
async def _run_startup_tasks():
    """Startup: create indexes + default users (called from lifespan)."""
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

# R3d: extracted endpoint groups
from routers.guests import router as guests_router  # noqa: E402
from routers.audit import router as audit_router  # noqa: E402
from routers.dashboard import router as dashboard_router  # noqa: E402
from routers.kvkk import router as kvkk_router  # noqa: E402
from routers.tc_kimlik import router as tc_kimlik_router  # noqa: E402
from routers.rooms import router as rooms_router  # noqa: E402
from routers.admin import router as admin_router  # noqa: E402
from routers.reports import router as reports_router  # noqa: E402
from routers.ocr import router as ocr_router  # noqa: E402
from routers.guide import router as guide_router  # noqa: E402
from routers.scan import router as scan_router  # noqa: E402

app.include_router(guests_router)
app.include_router(audit_router)
app.include_router(dashboard_router)
app.include_router(kvkk_router)
app.include_router(tc_kimlik_router)
app.include_router(rooms_router)
app.include_router(admin_router)
app.include_router(reports_router)
app.include_router(ocr_router)
app.include_router(guide_router)
app.include_router(scan_router)





if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("BACKEND_PORT", "8099"))
    uvicorn.run(app, host="0.0.0.0", port=port)
