"""OCR endpoints: Tesseract fallback, image quality check, system status, AI provider list/cost."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import require_auth
from db import scans_col
from helpers import _validate_image_payload
from image_quality import assess_image_quality
from ocr_fallback import is_tesseract_available, ocr_scan_document
from ocr_providers import estimate_scan_cost, get_provider_stats, list_providers
from rate_limit import limiter
from schemas import ScanRequest

router = APIRouter()
logger = logging.getLogger("quickid")


@router.post("/api/scan/ocr-fallback", tags=["OCR"], summary="Offline OCR tarama (Tesseract)",
             description="İnternet kesintisinde lokal Tesseract OCR ile kimlik belgesi tarama.")
@limiter.limit("30/minute")
async def ocr_fallback_scan(request: Request, scan_req: ScanRequest, user=Depends(require_auth)):
    # v52 (Bug CM): shared validator reuse — pre-v52 payload validate edilmiyordu.
    _validate_image_payload(scan_req.image_base64)
    if not is_tesseract_available():
        raise HTTPException(status_code=503, detail="Tesseract OCR sistemi mevcut değil")

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

    ocr_confidence = result.get("confidence", {})
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


@router.post("/api/scan/quality-check", tags=["OCR"], summary="Görüntü kalite kontrolü (geliştirilmiş)",
             description="Tarama öncesi geliştirilmiş görüntü kalite kontrolü.")
@limiter.limit("30/minute")
async def image_quality_check(request: Request, scan_req: ScanRequest, user=Depends(require_auth)):
    # v52 (Bug CM): shared validator + 30/minute rate limit (önceden hiçbiri yoktu).
    _validate_image_payload(scan_req.image_base64)
    return assess_image_quality(scan_req.image_base64)


@router.get("/api/scan/ocr-status", tags=["OCR"], summary="OCR sistem durumu")
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


@router.get("/api/scan/providers", tags=["OCR"], summary="Kullanılabilir AI sağlayıcıları",
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


@router.get("/api/scan/cost-estimate/{provider_id}", tags=["OCR"], summary="Tarama maliyet tahmini")
async def scan_cost_estimate(provider_id: str):
    estimate = estimate_scan_cost(provider_id)
    if "error" in estimate:
        raise HTTPException(status_code=404, detail=estimate["error"])
    return estimate
