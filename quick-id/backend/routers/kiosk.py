"""Kiosk mode endpoints."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import require_admin, require_auth
from db import db, scans_col
from helpers import _validate_image_payload, extract_id_data, serialize_doc
from kvkk_compliance import calculate_confidence_score
from multi_property import create_kiosk_session, get_kiosk_sessions, update_kiosk_activity
from rate_limit import limiter
from schemas import KioskSessionCreate, ScanRequest

router = APIRouter()


@router.post("/api/kiosk/session", tags=["Kiosk"], summary="Kiosk oturumu başlat")
async def start_kiosk_session(req: KioskSessionCreate, user=Depends(require_admin)):
    session = await create_kiosk_session(db, property_id=req.property_id, kiosk_name=req.kiosk_name)
    return {"success": True, "session": serialize_doc(session)}


@router.get("/api/kiosk/sessions", tags=["Kiosk"], summary="Kiosk oturumları listele")
async def list_kiosk_sessions(
    property_id: Optional[str] = None,
    status: Optional[str] = None,
    user=Depends(require_auth),
):
    sessions = await get_kiosk_sessions(db, property_id=property_id, status=status)
    return {"sessions": sessions, "total": len(sessions)}


@router.post("/api/kiosk/scan", tags=["Kiosk"], summary="Kiosk kimlik tarama",
             description="Kiosk modunda kimlik tarama - session_id ile çalışır")
@limiter.limit("20/minute")
async def kiosk_scan(request: Request, scan_req: ScanRequest,
                     session_id: str = Query(..., description="Kiosk session ID")):
    """Kiosk taraması - basic auth yeterli, session bazlı"""
    try:
        # v50 Round-3: validate image payload before AI scan
        _validate_image_payload(scan_req.image_base64)
        extracted = await extract_id_data(scan_req.image_base64)
        documents = extracted.get("documents", [])
        confidence = calculate_confidence_score(extracted)
        scan_doc = {
            "extracted_data": extracted,
            "document_count": extracted.get("document_count", len(documents)),
            "is_valid": any(d.get("is_valid", False) for d in documents),
            "created_at": datetime.now(timezone.utc),
            "status": "completed",
            "source": "kiosk",
            "session_id": session_id,
            "confidence_score": confidence.get("overall_score", 0),
            "confidence_level": confidence.get("confidence_level", "low"),
        }
        await scans_col.insert_one(scan_doc)
        await update_kiosk_activity(db, session_id, scan_increment=1)
        return {
            "success": True,
            "scan": serialize_doc(scan_doc),
            "extracted_data": extracted,
            "documents": documents,
            "confidence": confidence,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "message": f"Kiosk tarama hatası: {str(e)}",
            "fallback_guidance": [
                "Belgeyi düz yerleştirin", "Flaş kullanın", "Tekrar deneyin",
            ],
        })
