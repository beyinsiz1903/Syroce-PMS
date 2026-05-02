"""Pre-checkin (QR) endpoints."""
import io
import os
from datetime import datetime, timezone

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from typing import Optional

from auth import require_auth
from db import db, scans_col
from helpers import _validate_image_payload, extract_id_data, serialize_doc
from kvkk_compliance import calculate_confidence_score
from multi_property import (
    create_precheckin_token, get_precheckin_token, get_property,
    list_precheckin_tokens, use_precheckin_token,
)
from rate_limit import limiter
from schemas import PreCheckinCreate, PreCheckinScanRequest

router = APIRouter()


@router.post("/api/precheckin/create", tags=["Ön Check-in"], summary="QR ön check-in token oluştur",
             description="Misafirin varıştan önce telefonundan kimlik taraması yapabilmesi için QR token oluşturur")
async def create_precheckin(req: PreCheckinCreate, user=Depends(require_auth)):
    token = await create_precheckin_token(
        db, property_id=req.property_id,
        reservation_ref=req.reservation_ref,
        guest_name=req.guest_name,
        created_by=user.get("email"),
    )
    return {"success": True, "token": serialize_doc(token)}


@router.get("/api/precheckin/list", tags=["Ön Check-in"], summary="Ön check-in tokenlarını listele")
async def list_precheckin(
    property_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user=Depends(require_auth),
):
    return await list_precheckin_tokens(db, property_id=property_id, status=status, page=page, limit=limit)


@router.get("/api/precheckin/{token_id}", tags=["Ön Check-in"], summary="Token bilgisi (public)",
            description="QR kod ile erişilen token bilgisi. Kimlik doğrulama gerektirmez.")
async def get_precheckin_info(token_id: str):
    """Public endpoint - QR ile erişim"""
    token = await get_precheckin_token(db, token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Geçersiz veya süresi dolmuş QR kod")
    if token.get("status") != "active":
        raise HTTPException(status_code=400, detail="Bu QR kod zaten kullanılmış")
    prop = await get_property(db, token.get("property_id", ""))
    return {
        "token_id": token["token_id"],
        "status": token["status"],
        "property_name": prop.get("name", "Otel") if prop else "Otel",
        "reservation_ref": token.get("reservation_ref", ""),
        "guest_name": token.get("guest_name", ""),
    }


@router.post("/api/precheckin/{token_id}/scan", tags=["Ön Check-in"], summary="QR ile kimlik tara (public)",
             description="Misafirin kendi telefonundan kimlik belgesi taraması. Kimlik doğrulama gerektirmez.")
@limiter.limit("5/minute")
async def precheckin_scan(request: Request, token_id: str, req: PreCheckinScanRequest):
    """Public endpoint - Misafir kendi telefonundan tarar"""
    token = await get_precheckin_token(db, token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Geçersiz QR kod")
    if token.get("status") != "active":
        raise HTTPException(status_code=400, detail="Bu QR kod zaten kullanılmış")
    try:
        # v50 Round-3: validate image payload before AI scan (public endpoint)
        _validate_image_payload(req.image_base64)
        extracted = await extract_id_data(req.image_base64)
        documents = extracted.get("documents", [])
        confidence = calculate_confidence_score(extracted)
        scan_doc = {
            "extracted_data": extracted,
            "document_count": extracted.get("document_count", len(documents)),
            "is_valid": any(d.get("is_valid", False) for d in documents),
            "created_at": datetime.now(timezone.utc),
            "status": "completed",
            "source": "precheckin",
            "token_id": token_id,
            "confidence_score": confidence.get("overall_score", 0),
            "confidence_level": confidence.get("confidence_level", "low"),
            "kvkk_consent": req.kvkk_consent,
        }
        await scans_col.insert_one(scan_doc)
        await use_precheckin_token(db, token_id, extracted)
        return {
            "success": True,
            "extracted_data": extracted,
            "documents": documents,
            "confidence": confidence,
            "message": "Kimlik taramanız başarılı! Otele vardığınızda hızlı check-in yapabilirsiniz.",
        }
    except HTTPException:
        raise
    except Exception as e:
        fallback = [
            "Kimlik belgesi okunamadı. Lütfen şunları deneyin:",
            "1. Belgeyi düz bir yüzeye yerleştirin",
            "2. Flaş kullanarak fotoğraf çekin",
            "3. İyi aydınlatma altında tekrar deneyin",
        ]
        raise HTTPException(status_code=500, detail={
            "message": f"Tarama başarısız: {str(e)}",
            "fallback_guidance": fallback,
            "can_retry": True,
        })


@router.get("/api/precheckin/{token_id}/qr", tags=["Ön Check-in"], summary="QR kod görüntüsü",
            description="Ön check-in QR kodunu PNG olarak döndürür")
async def get_precheckin_qr(token_id: str, user=Depends(require_auth)):
    """QR kod oluştur ve döndür"""
    token = await get_precheckin_token(db, token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token bulunamadı")
    frontend_url = os.environ.get("FRONTEND_URL", "")
    qr_url = f"{frontend_url}/precheckin/{token_id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png",
                             headers={"Content-Disposition": f"inline; filename=precheckin-{token_id}.png"})
