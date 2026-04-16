"""
Quick-ID Microservice Proxy
===========================
PMS backend, Quick-ID mikroservisine (port 8099) kimlik tarama isteklerini iletir.
PMS kullanıcısı JWT'si ile korunur; Quick-ID'ye servis anahtarı (QUICKID_SERVICE_KEY) ile erişir.
"""
import os
import logging
from typing import Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException, Body
from core.security import get_current_user

logger = logging.getLogger("quick_id_proxy")

router = APIRouter(prefix="/api/quick-id", tags=["Quick-ID"])

QUICKID_URL = os.environ.get("QUICKID_URL", "http://localhost:8099").rstrip("/")
QUICKID_SERVICE_KEY = os.environ.get("QUICKID_SERVICE_KEY", "")
# Demo mod yalnızca açıkça etkinleştirilmişse çalışır (fail-closed)
QUICKID_DEMO_ENABLED = os.environ.get("ENABLE_QUICKID_DEMO", "").lower() in ("1", "true", "yes", "on")


def _service_headers(user) -> dict:
    acting = getattr(user, "email", None) or getattr(user, "username", None) or "pms-user"
    return {
        "X-Service-Key": QUICKID_SERVICE_KEY,
        "X-Acting-User": str(acting),
        "Content-Type": "application/json",
    }


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

    body = {
        "image_base64": image_b64,
        "provider": payload.get("provider"),
        "smart_mode": payload.get("smart_mode", True),
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{QUICKID_URL}/api/scan",
                json=body,
                headers=_service_headers(current_user),
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
