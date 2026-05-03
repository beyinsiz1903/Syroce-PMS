"""Scan endpoints: POST /api/scan (multi-provider AI), GET /api/scans (history),
review queue + review status patch. server.py'den R3e turunda ayrıştırıldı."""
import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import require_auth
from db import db, scans_col
from helpers import _validate_image_payload, extract_id_data, serialize_doc
from image_quality import assess_image_quality
from kvkk_compliance import calculate_confidence_score
from monitoring import track_ai_cost
from mrz_parser import parse_mrz_from_text
from ocr_fallback import is_tesseract_available, ocr_scan_document
from ocr_providers import PROVIDERS, extract_with_provider, smart_scan
from rate_limit import limiter
from schemas import MAX_IMAGE_BASE64_LENGTH, ScanRequest

router = APIRouter()
logger = logging.getLogger("quickid")


@router.post("/api/scan", tags=["Tarama"], summary="Kimlik belgesi tara (çoklu provider)",
             description="AI ile kimlik belgesini tarayıp bilgi çıkarır. Provider seçimi: gpt-4o, gpt-4o-mini, gemini-flash, tesseract, auto. Görüntü kalite kontrolü + MRZ parsing + Confidence score.")
@limiter.limit("15/minute")
async def scan_id(request: Request, scan_req: ScanRequest, user=Depends(require_auth)):
    try:
        _validate_image_payload(scan_req.image_base64)
        if len(scan_req.image_base64) > MAX_IMAGE_BASE64_LENGTH:
            raise HTTPException(
                status_code=413,
                detail=f"Görüntü boyutu çok büyük. Maksimum {MAX_IMAGE_BASE64_LENGTH // (1024*1024)}MB izin verilir."
            )

        per_req_keys = {
            "openai": request.headers.get("X-OpenAI-Key"),
            "gemini": request.headers.get("X-Gemini-Key"),
        }
        per_req_keys = {k: v for k, v in per_req_keys.items() if v}

        quality = assess_image_quality(scan_req.image_base64)
        quality_score = quality.get("overall_score", 70)

        if quality.get("quality_checked") and not quality.get("pass", True):
            pass

        requested_provider = scan_req.provider
        use_smart = scan_req.smart_mode if scan_req.smart_mode is not None else True

        if requested_provider == "tesseract":
            ocr_result = ocr_scan_document(scan_req.image_base64)
            if not ocr_result.get("success"):
                raise Exception(ocr_result.get("error", "OCR hatası"))

            documents = ocr_result.get("documents", [])
            extracted = {"documents": documents, "document_count": len(documents)}
            used_provider = "tesseract"
            provider_info = {"name": "Tesseract OCR", "cost": 0, "speed": "fast"}
        elif use_smart and not requested_provider:
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
        elif requested_provider and requested_provider in PROVIDERS:
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
        else:
            extracted = await extract_id_data(scan_req.image_base64)
            documents = extracted.get("documents", [])
            used_provider = "gpt-4o"
            provider_info = {"name": "GPT-4o", "cost": 0.015}

        document_count = extracted.get("document_count", len(documents))

        confidence = calculate_confidence_score(extracted)

        mrz_results = []
        for doc in documents:
            raw_text = doc.get("raw_extracted_text", "")
            if raw_text:
                mrz = parse_mrz_from_text(raw_text)
                if mrz.get("mrz_detected"):
                    mrz_results.append(mrz)
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


@router.get("/api/scans", tags=["Tarama"], summary="Tarama geçmişi")
async def get_scans(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), user=Depends(require_auth)):
    skip = (page - 1) * limit
    total = await scans_col.count_documents({})
    cursor = scans_col.find({}).sort("created_at", -1).skip(skip).limit(limit)
    scans = [serialize_doc(doc) async for doc in cursor]
    return {"scans": scans, "total": total, "page": page, "limit": limit}


@router.get("/api/scans/review-queue", tags=["Tarama"], summary="İnceleme kuyruğu",
            description="Düşük güvenilirlik puanlı taramaları listeler")
async def get_review_queue(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    review_status: Optional[str] = Query(None, description="needs_review, auto_approved, reviewed"),
    user=Depends(require_auth),
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


@router.patch("/api/scans/{scan_id}/review", tags=["Tarama"], summary="Tarama inceleme durumu güncelle")
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
