"""Biometric endpoints: face-compare, liveness-challenge, liveness-check."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import require_auth
from biometric import check_liveness, compare_faces, get_liveness_challenge
from db import db
from helpers import _validate_image_payload
from rate_limit import limiter
from schemas import FaceCompareRequest, LivenessCheckRequest

router = APIRouter()


@router.post("/api/biometric/face-compare", tags=["Biyometrik"], summary="Yüz eşleştirme",
             description="Kimlik belgesindeki fotoğraf ile canlı selfie karşılaştırması. Güven skoru (0-100) döner.")
@limiter.limit("10/minute")
async def biometric_face_compare(request: Request, req: FaceCompareRequest, user=Depends(require_auth)):
    try:
        # v50 Round-3: validate both image payloads before downstream processing
        _validate_image_payload(req.document_image_base64)
        _validate_image_payload(req.selfie_image_base64)
        result = await compare_faces(req.document_image_base64, req.selfie_image_base64)
        match_doc = {
            "match_id": str(uuid.uuid4()),
            "result": result,
            "match": result.get("match", False),
            "confidence_score": result.get("confidence_score", 0),
            "created_at": datetime.now(timezone.utc),
            "created_by": user.get("email"),
        }
        await db["biometric_matches"].insert_one(match_doc)
        return {
            "success": True,
            "match": result.get("match", False),
            "confidence_score": result.get("confidence_score", 0),
            "confidence_level": result.get("confidence_level", "low"),
            "analysis": result.get("analysis", {}),
            "notes": result.get("notes", ""),
            "warnings": result.get("warnings", []),
            "image_quality": result.get("image_quality", {}),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Yüz eşleştirme hatası: {str(e)}")


@router.get("/api/biometric/liveness-challenge", tags=["Biyometrik"], summary="Canlılık testi sorusu",
            description="Spoofing önleme için rastgele canlılık testi sorusu döner")
async def get_liveness_challenge_endpoint():
    """Kimlik doğrulama gerektirmez - ön check-in'de de kullanılabilir"""
    return get_liveness_challenge()


@router.post("/api/biometric/liveness-check", tags=["Biyometrik"], summary="Canlılık testi doğrulama",
             description="Gönderilen fotoğrafın canlı kişiye ait olup olmadığını kontrol eder")
@limiter.limit("10/minute")
async def biometric_liveness_check(request: Request, req: LivenessCheckRequest, user=Depends(require_auth)):
    try:
        # v50 Round-3: validate image payload before downstream processing
        _validate_image_payload(req.image_base64)
        result = await check_liveness(req.image_base64, req.challenge_id)
        liveness_doc = {
            "session_id": req.session_id,
            "challenge_id": req.challenge_id,
            "result": result,
            "is_live": result.get("is_live", False),
            "confidence_score": result.get("confidence_score", 0),
            "created_at": datetime.now(timezone.utc),
            "created_by": user.get("email"),
        }
        await db["liveness_checks"].insert_one(liveness_doc)
        return {
            "success": True,
            "is_live": result.get("is_live", False),
            "challenge_completed": result.get("challenge_completed", False),
            "confidence_score": result.get("confidence_score", 0),
            "spoof_indicators": result.get("spoof_indicators", []),
            "notes": result.get("notes", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Canlılık testi hatası: {str(e)}")
