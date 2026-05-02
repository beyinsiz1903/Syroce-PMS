"""
Quick-ID Microservice Proxy
===========================
PMS backend, Quick-ID mikroservisine (port 8099) kimlik tarama isteklerini iletir.
PMS kullanıcısı JWT'si ile korunur; Quick-ID'ye servis anahtarı (QUICKID_SERVICE_KEY) ile erişir.

Ayrıca admin kullanıcılar OpenAI/Gemini API anahtarlarını uygulama içinden
yönetebilir (şifreli olarak `quick_id_settings` koleksiyonunda saklanır).
"""
import base64
import hashlib
import logging
import os
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel

from core.database import _raw_db as raw_db
from core.security import JWT_SECRET, _is_super_admin, get_current_user

logger = logging.getLogger("quick_id_proxy")

router = APIRouter(prefix="/api/quick-id", tags=["Quick-ID"])

QUICKID_URL = os.environ.get("QUICKID_URL", "http://localhost:8099").rstrip("/")
QUICKID_SERVICE_KEY = os.environ.get("QUICKID_SERVICE_KEY", "")
# Demo mod yalnızca açıkça etkinleştirilmişse çalışır (fail-closed)
QUICKID_DEMO_ENABLED = os.environ.get("ENABLE_QUICKID_DEMO", "").lower() in ("1", "true", "yes", "on")

# Şifreleme anahtarları (öncelik: dedicated env > JWT_SECRET-türetilmiş).
# Anahtar rotasyonu için OLD anahtar(lar) geçici olarak okumak için kullanılabilir.
QUICKID_ENC_KEY = os.environ.get("QUICKID_SETTINGS_ENC_KEY", "").strip()
QUICKID_ENC_KEY_OLD = os.environ.get("QUICKID_SETTINGS_ENC_KEY_OLD", "").strip()

SETTINGS_COLL = "quick_id_settings"
SETTINGS_DOC_ID = "global"

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _is_safe_quickid_transport(url: str) -> bool:
    """Header üzerinden API anahtarı geçirmek için yalnızca loopback ya da HTTPS güvenli."""
    try:
        parsed = urlparse(url)
        if parsed.scheme == "https":
            return True
        if parsed.scheme == "http" and (parsed.hostname or "").lower() in LOOPBACK_HOSTS:
            return True
    except Exception:
        pass
    return False


def _normalize_fernet_key(raw: str) -> bytes | None:
    """Verilen string'i Fernet anahtarına dönüştürür.
    - 44 byte urlsafe base64 ise olduğu gibi kullanılır.
    - Aksi halde SHA256 türevi alınıp base64 encode edilir.
    """
    if not raw:
        return None
    try:
        # Geçerli bir Fernet anahtarı mı?
        Fernet(raw.encode("utf-8"))
        return raw.encode("utf-8")
    except Exception:
        digest = hashlib.sha256(raw.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)


def _build_fernet() -> MultiFernet | None:
    """MultiFernet: birincil anahtarla şifreler; OLD ile de okuyabilir."""
    primary_raw = QUICKID_ENC_KEY or JWT_SECRET
    if not primary_raw:
        return None
    primary = _normalize_fernet_key(primary_raw)
    if not primary:
        return None
    fernets = [Fernet(primary)]
    if QUICKID_ENC_KEY_OLD:
        old_key = _normalize_fernet_key(QUICKID_ENC_KEY_OLD)
        if old_key and old_key != primary:
            fernets.append(Fernet(old_key))
    return MultiFernet(fernets)


def _fernet() -> MultiFernet:
    f = _build_fernet()
    if f is None:
        raise HTTPException(
            status_code=503,
            detail="Şifreleme anahtarı yapılandırılmamış (QUICKID_SETTINGS_ENC_KEY veya JWT_SECRET gerekli)",
        )
    return f


def _enc(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def _dec(value: str | None) -> tuple | None:
    """(plaintext, ok) — ok=False decryption hata anlamına gelir (anahtar uyumsuz/bozuk)."""
    if not value:
        return None
    try:
        f = _build_fernet()
        if f is None:
            return None
        return f.decrypt(value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as e:
        logger.error(
            "Quick-ID API key çözülemedi — anahtar rotasyonu yapıldıysa "
            "QUICKID_SETTINGS_ENC_KEY_OLD ayarlayın ve kayıtları tekrar girin: %s",
            e,
        )
        return "__DECRYPT_FAILED__"


def _mask(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}{'•' * 8}{value[-4:]}"


async def _load_settings() -> dict:
    doc = await raw_db[SETTINGS_COLL].find_one({"_id": SETTINGS_DOC_ID})
    return doc or {}


async def _save_settings(update: dict, user) -> None:
    update["updated_at"] = datetime.now(UTC)
    update["updated_by"] = getattr(user, "email", None) or getattr(user, "username", "admin")
    await raw_db[SETTINGS_COLL].update_one(
        {"_id": SETTINGS_DOC_ID},
        {"$set": update},
        upsert=True,
    )


def _safe_dec(value: str | None) -> str | None:
    """`__DECRYPT_FAILED__` durumunu None'a çevirerek ham metni döner."""
    res = _dec(value)
    if res == "__DECRYPT_FAILED__":
        return None
    return res


async def _resolve_api_keys() -> dict:
    """DB'den çözülmüş anahtarlar; yoksa env fallback."""
    s = await _load_settings()
    openai_key = _safe_dec(s.get("openai_api_key_enc")) or os.environ.get("OPENAI_API_KEY", "")
    gemini_key = _safe_dec(s.get("gemini_api_key_enc")) or os.environ.get("GEMINI_API_KEY", "")
    return {
        "openai": openai_key.strip() if openai_key else "",
        "gemini": gemini_key.strip() if gemini_key else "",
        "preferred_provider": s.get("preferred_provider"),
    }


def _service_headers(user, api_keys: dict | None = None) -> dict:
    acting = getattr(user, "email", None) or getattr(user, "username", None) or "pms-user"
    headers = {
        "X-Service-Key": QUICKID_SERVICE_KEY,
        "X-Acting-User": str(acting),
        "Content-Type": "application/json",
    }
    # API anahtarlarını yalnızca güvenli transport (loopback ya da HTTPS) ise ilet
    if api_keys and _is_safe_quickid_transport(QUICKID_URL):
        if api_keys.get("openai"):
            headers["X-OpenAI-Key"] = api_keys["openai"]
        if api_keys.get("gemini"):
            headers["X-Gemini-Key"] = api_keys["gemini"]
    elif api_keys and (api_keys.get("openai") or api_keys.get("gemini")):
        logger.error(
            "QUICKID_URL güvensiz (HTTP+remote): API anahtarları header üzerinden "
            "iletilmeyecek. Loopback ya da HTTPS kullanın. URL=%s", QUICKID_URL,
        )
    return headers


def _require_admin(user):
    if not _is_super_admin(user):
        raise HTTPException(status_code=403, detail="Bu ayarı sadece süper yönetici değiştirebilir")


def _demo_scan_result() -> dict:
    """API anahtarı yokken kullanıcıya UI akışını göstermek için sahte veri."""
    return {
        "success": True,
        "demo_mode": True,
        "extracted_data": {
            "documents": [{
                "first_name": "AYŞE",
                "last_name": "DEMO",
                "id_number": "12345678901",
                "document_type": "tc_kimlik",
                "document_number": "A12345678",
                "birth_date": "1990-05-15",
                "gender": "female",
                "nationality": "TR",
                "issue_date": "2020-01-01",
                "expiry_date": "2030-01-01",
                "mother_name": "FATMA",
                "father_name": "MEHMET",
                "birth_place": "İSTANBUL",
                "is_valid": True,
                "warnings": ["Demo verisi - OCR sağlayıcı yapılandırılmamış"],
            }],
            "document_count": 1,
        },
        "scan": {
            "confidence_score": 85,
            "confidence_level": "medium",
            "provider": "demo",
            "provider_info": {"name": "Demo Mode", "cost": 0},
        },
    }


@router.get("/health")
async def health(current_user=Depends(get_current_user)):
    """Quick-ID servisinin sağlığını kontrol eder."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{QUICKID_URL}/api/health")
            if r.status_code == 200:
                return {"available": True, "quickid": r.json(), "service_key_configured": bool(QUICKID_SERVICE_KEY)}
    except Exception as e:
        logger.warning(f"Quick-ID erişilemiyor: {e}")
    return {"available": False, "service_key_configured": bool(QUICKID_SERVICE_KEY)}


@router.post("/scan")
async def scan_id(
    payload: dict = Body(...),
    current_user=Depends(get_current_user),
):
    """
    Kimlik belgesi tarama.
    Body: { image_base64: str, provider?: str, smart_mode?: bool }
    """
    image_b64 = payload.get("image_base64")
    if not image_b64:
        raise HTTPException(status_code=400, detail="image_base64 gerekli")

    if not QUICKID_SERVICE_KEY:
        if QUICKID_DEMO_ENABLED:
            logger.warning("QUICKID_SERVICE_KEY ayarlı değil — demo mod (ENABLE_QUICKID_DEMO açık)")
            return _demo_scan_result()
        raise HTTPException(status_code=503, detail="Kimlik tarama servisi yapılandırılmamış (QUICKID_SERVICE_KEY eksik)")

    api_keys = await _resolve_api_keys()
    chosen_provider = payload.get("provider") or api_keys.get("preferred_provider")
    body = {
        "image_base64": image_b64,
        "provider": chosen_provider,
        "smart_mode": payload.get("smart_mode", True),
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{QUICKID_URL}/api/scan",
                json=body,
                headers=_service_headers(current_user, api_keys=api_keys),
            )
        if r.status_code >= 400:
            # OCR sağlayıcı yoksa veya tarama başarısızsa demo moda düş
            detail_raw = ""
            try:
                payload_resp = r.json()
                detail_raw = payload_resp.get("detail", "")
                if isinstance(detail_raw, dict):
                    detail_raw = str(detail_raw.get("message", "")) + " " + " ".join(detail_raw.get("fallback_guidance", []))
            except Exception:
                detail_raw = r.text
            detail_lower = str(detail_raw).lower()
            ocr_unavailable_signals = [
                "api anahtarı", "api key",
                "tüm sağlayıcılar", "tum saglayicilar", "all providers",
                "tesseract", "ocr",
                "openai", "gemini",
            ]
            if r.status_code in (500, 502, 503) or any(s in detail_lower for s in ocr_unavailable_signals):
                if QUICKID_DEMO_ENABLED:
                    logger.warning(f"Quick-ID OCR kullanılamıyor, demo moda geçiliyor: {detail_raw[:200]}")
                    return _demo_scan_result()
                # Production: gerçek hatayı yansıt
                raise HTTPException(
                    status_code=503,
                    detail=f"Kimlik tarama servisi şu anda kullanılamıyor: {str(detail_raw)[:200]}",
                )
            raise HTTPException(status_code=r.status_code, detail=str(detail_raw) or "Tarama hatası")
        return r.json()
    except httpx.RequestError as e:
        if QUICKID_DEMO_ENABLED:
            logger.warning(f"Quick-ID bağlantı hatası, demo mod: {e}")
            return _demo_scan_result()
        raise HTTPException(status_code=503, detail=f"Kimlik tarama servisine ulaşılamıyor: {e}")


@router.get("/providers")
async def providers(current_user=Depends(get_current_user)):
    """Mevcut OCR sağlayıcı listesi."""
    if not QUICKID_SERVICE_KEY:
        return {"providers": [{"id": "demo", "name": "Demo Mode", "available": True, "cost": 0}], "demo_mode": True}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{QUICKID_URL}/api/scan/providers",
                headers=_service_headers(current_user),
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.warning(f"Quick-ID providers hatası: {e}")
    return {"providers": [], "demo_mode": True}


# ===================== AYARLAR (admin) =====================

class QuickIdSettingsUpdate(BaseModel):
    openai_api_key: str | None = None  # None: değiştirme; "": temizle
    gemini_api_key: str | None = None
    preferred_provider: str | None = None  # gpt-4o | gpt-4o-mini | gemini-flash | tesseract | None


@router.get("/settings")
async def get_quick_id_settings(current_user=Depends(get_current_user)):
    """Quick-ID API anahtar ayarlarını maskeli olarak döndürür."""
    _require_admin(current_user)
    s = await _load_settings()
    openai_raw = _dec(s.get("openai_api_key_enc"))
    gemini_raw = _dec(s.get("gemini_api_key_enc"))
    openai_dec = openai_raw if openai_raw and openai_raw != "__DECRYPT_FAILED__" else None
    gemini_dec = gemini_raw if gemini_raw and gemini_raw != "__DECRYPT_FAILED__" else None
    openai_failed = openai_raw == "__DECRYPT_FAILED__"
    gemini_failed = gemini_raw == "__DECRYPT_FAILED__"
    env_openai = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    env_gemini = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    return {
        "openai": {
            "configured": bool(openai_dec),
            "masked": _mask(openai_dec),
            "env_fallback": env_openai,
            "decrypt_failed": openai_failed,
        },
        "gemini": {
            "configured": bool(gemini_dec),
            "masked": _mask(gemini_dec),
            "env_fallback": env_gemini,
            "decrypt_failed": gemini_failed,
        },
        "preferred_provider": s.get("preferred_provider"),
        "updated_at": s.get("updated_at"),
        "updated_by": s.get("updated_by"),
        "demo_mode": QUICKID_DEMO_ENABLED and not (openai_dec or gemini_dec or env_openai or env_gemini),
        "service_key_configured": bool(QUICKID_SERVICE_KEY),
        "transport_safe": _is_safe_quickid_transport(QUICKID_URL),
        "encryption_key_source": "dedicated" if QUICKID_ENC_KEY else ("jwt_secret" if JWT_SECRET else "missing"),
    }


@router.put("/settings")
async def update_quick_id_settings(
    payload: QuickIdSettingsUpdate,
    current_user=Depends(get_current_user),
):
    """Quick-ID API anahtarlarını şifreli olarak kaydet."""
    _require_admin(current_user)
    update: dict = {}
    # None gelirse dokunma; "" gelirse temizle; dolu gelirse şifrele
    if payload.openai_api_key is not None:
        if payload.openai_api_key.strip() == "":
            update["openai_api_key_enc"] = None
        else:
            update["openai_api_key_enc"] = _enc(payload.openai_api_key.strip())
    if payload.gemini_api_key is not None:
        if payload.gemini_api_key.strip() == "":
            update["gemini_api_key_enc"] = None
        else:
            update["gemini_api_key_enc"] = _enc(payload.gemini_api_key.strip())
    if payload.preferred_provider is not None:
        valid = {"gpt-4o", "gpt-4o-mini", "gemini-flash", "tesseract", ""}
        if payload.preferred_provider not in valid:
            raise HTTPException(status_code=400, detail=f"Geçersiz sağlayıcı: {payload.preferred_provider}")
        update["preferred_provider"] = payload.preferred_provider or None

    if not update:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")

    await _save_settings(update, current_user)
    return await get_quick_id_settings(current_user)


@router.post("/settings/test")
async def test_quick_id_keys(current_user=Depends(get_current_user)):
    """Mevcut kayıtlı (veya env) anahtarlarla küçük bir bağlanabilirlik testi yapar."""
    _require_admin(current_user)
    keys = await _resolve_api_keys()
    results = {}

    if keys.get("openai"):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {keys['openai']}"},
                )
            results["openai"] = {
                "ok": r.status_code == 200,
                "status_code": r.status_code,
                "detail": "Bağlantı başarılı" if r.status_code == 200 else r.text[:200],
            }
        except Exception as e:
            results["openai"] = {"ok": False, "detail": str(e)[:200]}
    else:
        results["openai"] = {"ok": False, "detail": "Anahtar tanımlı değil"}

    if keys.get("gemini"):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={keys['gemini']}",
                )
            results["gemini"] = {
                "ok": r.status_code == 200,
                "status_code": r.status_code,
                "detail": "Bağlantı başarılı" if r.status_code == 200 else r.text[:200],
            }
        except Exception as e:
            results["gemini"] = {"ok": False, "detail": str(e)[:200]}
    else:
        results["gemini"] = {"ok": False, "detail": "Anahtar tanımlı değil"}

    return {"results": results}


# ===================== BIYOMETRIK (face-compare + liveness) =====================

@router.post("/biometric/face-compare")
async def biometric_face_compare(
    payload: dict = Body(...),
    current_user=Depends(get_current_user),
):
    """Kimlik üzerindeki fotoğraf ile selfie karşılaştır.
    Body: { document_image_base64, selfie_image_base64 }
    """
    doc_b64 = payload.get("document_image_base64")
    selfie_b64 = payload.get("selfie_image_base64")
    if not doc_b64 or not selfie_b64:
        raise HTTPException(status_code=400, detail="document_image_base64 ve selfie_image_base64 gerekli")

    if not QUICKID_SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Biyometrik servis yapılandırılmamış")

    api_keys = await _resolve_api_keys()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{QUICKID_URL}/api/biometric/face-compare",
                json={"document_image_base64": doc_b64, "selfie_image_base64": selfie_b64},
                headers=_service_headers(current_user, api_keys=api_keys),
            )
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", "")
            except Exception:
                detail = r.text
            raise HTTPException(status_code=r.status_code, detail=str(detail) or "Yüz eşleştirme hatası")
        return r.json()
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Biyometrik servise ulaşılamıyor: {e}")


@router.get("/biometric/liveness-challenge")
async def biometric_liveness_challenge(current_user=Depends(get_current_user)):
    """Rastgele canlılık testi sorusu döner."""
    if not QUICKID_SERVICE_KEY:
        # Demo challenge
        return {
            "challenge_id": "demo",
            "instruction": "Lütfen başınızı hafifçe sağa çevirin",
            "type": "head_turn",
        }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{QUICKID_URL}/api/biometric/liveness-challenge",
                headers=_service_headers(current_user),
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.warning(f"Liveness challenge hatası: {e}")
    return {"challenge_id": "fallback", "instruction": "Kameraya bakın", "type": "look"}


@router.post("/biometric/liveness-check")
async def biometric_liveness_check(
    payload: dict = Body(...),
    current_user=Depends(get_current_user),
):
    """Selfie'nin canlı kişi olup olmadığını kontrol et."""
    image_b64 = payload.get("image_base64")
    if not image_b64:
        raise HTTPException(status_code=400, detail="image_base64 gerekli")

    if not QUICKID_SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Biyometrik servis yapılandırılmamış")

    api_keys = await _resolve_api_keys()
    body = {
        "image_base64": image_b64,
        "challenge_id": payload.get("challenge_id", ""),
        "session_id": payload.get("session_id", ""),
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{QUICKID_URL}/api/biometric/liveness-check",
                json=body,
                headers=_service_headers(current_user, api_keys=api_keys),
            )
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", "")
            except Exception:
                detail = r.text
            raise HTTPException(status_code=r.status_code, detail=str(detail) or "Canlılık testi hatası")
        return r.json()
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Biyometrik servise ulaşılamıyor: {e}")


# ===================== ÖN CHECK-IN (QR) =====================

@router.post("/precheckin/create")
async def precheckin_create(
    payload: dict = Body(...),
    current_user=Depends(get_current_user),
):
    """QR ön check-in tokenı oluştur.
    Body: { property_id, reservation_ref?, guest_name? }
    """
    if not QUICKID_SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Quick-ID servis anahtarı tanımlı değil")
    body = {
        "property_id": payload.get("property_id") or "default",
        "reservation_ref": payload.get("reservation_ref", ""),
        "guest_name": payload.get("guest_name", ""),
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{QUICKID_URL}/api/precheckin/create",
                json=body,
                headers=_service_headers(current_user),
            )
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", "")
            except Exception:
                detail = r.text
            raise HTTPException(status_code=r.status_code, detail=str(detail) or "Token oluşturulamadı")
        return r.json()
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Servise ulaşılamıyor: {e}")


# Aşağıdaki iki endpoint **public** — JWT zorunlu DEĞİL.
# Misafir kendi telefonundan QR linkiyle açtığında çalışır.
public_router = APIRouter(prefix="/api/quick-id/precheckin", tags=["Quick-ID Public"])

# In-memory rate limiter (IP+token bazlı). Multi-instance için Redis'e taşınabilir.
import time
from collections import defaultdict, deque
from threading import Lock

_RL_BUCKETS: dict = defaultdict(deque)
_RL_ATTEMPTS: dict = defaultdict(int)
_RL_LOCKED_UNTIL: dict = defaultdict(float)
_RL_LOCK = Lock()
_RL_INFO_LIMIT = 30      # token başına 60 sn'de en fazla 30 info isteği
_RL_INFO_WINDOW = 60
_RL_SCAN_LIMIT = 5       # token başına 60 sn'de en fazla 5 scan
_RL_SCAN_WINDOW = 60
_RL_MAX_ATTEMPTS = 10    # token başına toplam 10 başarısız sonrası 30 dk kilit
_RL_LOCKOUT_SEC = 1800


def _rl_check(bucket_key: str, limit: int, window: int):
    """Sliding-window rate-limit + lockout kontrolü."""
    now = time.time()
    with _RL_LOCK:
        if _RL_LOCKED_UNTIL.get(bucket_key, 0) > now:
            remain = int(_RL_LOCKED_UNTIL[bucket_key] - now)
            raise HTTPException(status_code=429, detail=f"Çok fazla deneme. {remain}s sonra tekrar deneyin.")
        dq = _RL_BUCKETS[bucket_key]
        cutoff = now - window
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            raise HTTPException(status_code=429, detail="İstek limiti aşıldı, biraz bekleyin.")
        dq.append(now)


def _rl_record_attempt(bucket_key: str, success: bool):
    """Başarısız deneme sayar; eşik aşılırsa lockout uygular."""
    with _RL_LOCK:
        if success:
            _RL_ATTEMPTS[bucket_key] = 0
            return
        _RL_ATTEMPTS[bucket_key] += 1
        if _RL_ATTEMPTS[bucket_key] >= _RL_MAX_ATTEMPTS:
            _RL_LOCKED_UNTIL[bucket_key] = time.time() + _RL_LOCKOUT_SEC
            _RL_ATTEMPTS[bucket_key] = 0


def _client_ip(request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@public_router.get("/{token_id}/info")
async def precheckin_info_public(token_id: str, request: Request):
    """QR ile ulaşılan token bilgisi (public)."""
    if not QUICKID_SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Servis yapılandırılmamış")
    bucket = f"info:{_client_ip(request)}:{token_id}"
    _rl_check(bucket, _RL_INFO_LIMIT, _RL_INFO_WINDOW)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{QUICKID_URL}/api/precheckin/{token_id}",
                headers={"X-Service-Key": QUICKID_SERVICE_KEY, "X-Acting-User": "guest-public"},
            )
        if r.status_code >= 400:
            _rl_record_attempt(bucket, success=False)
            try:
                detail = r.json().get("detail", "QR geçersiz")
            except Exception:
                detail = "QR geçersiz"
            raise HTTPException(status_code=r.status_code, detail=str(detail))
        _rl_record_attempt(bucket, success=True)
        return r.json()
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Servise ulaşılamıyor: {e}")


@public_router.post("/{token_id}/scan")
async def precheckin_scan_public(token_id: str, request: Request, payload: dict = Body(...)):
    """Misafir kendi telefonundan kimlik tarar (public)."""
    # KVKK consent backend'de zorunlu — frontend kontrolüne ek katman
    if not payload.get("kvkk_consent"):
        raise HTTPException(status_code=400, detail="KVKK onayı zorunludur")
    image_b64 = payload.get("image_base64")
    if not image_b64:
        raise HTTPException(status_code=400, detail="image_base64 gerekli")
    if not QUICKID_SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Servis yapılandırılmamış")
    # Tarama maliyetli — sıkı limit
    bucket = f"scan:{_client_ip(request)}:{token_id}"
    _rl_check(bucket, _RL_SCAN_LIMIT, _RL_SCAN_WINDOW)

    api_keys = await _resolve_api_keys()
    headers = {
        "X-Service-Key": QUICKID_SERVICE_KEY,
        "X-Acting-User": "guest-public",
        "Content-Type": "application/json",
    }
    if _is_safe_quickid_transport(QUICKID_URL):
        if api_keys.get("openai"):
            headers["X-OpenAI-Key"] = api_keys["openai"]
        if api_keys.get("gemini"):
            headers["X-Gemini-Key"] = api_keys["gemini"]

    body = {"image_base64": image_b64, "kvkk_consent": True}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{QUICKID_URL}/api/precheckin/{token_id}/scan",
                json=body,
                headers=headers,
            )
        if r.status_code >= 400:
            _rl_record_attempt(bucket, success=False)
            try:
                detail = r.json().get("detail", "")
            except Exception:
                detail = r.text
            raise HTTPException(status_code=r.status_code, detail=str(detail) or "Tarama hatası")
        _rl_record_attempt(bucket, success=True)
        return r.json()
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Servise ulaşılamıyor: {e}")
