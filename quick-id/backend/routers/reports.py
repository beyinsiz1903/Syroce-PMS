"""PDF reports: Form-C and guest list."""
import logging
from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from auth import require_auth
from db import guests_col
from helpers import serialize_doc
from pdf_reports import generate_form_c_pdf, generate_guest_list_pdf

router = APIRouter()
logger = logging.getLogger("quickid")


@router.get("/api/reports/form-c/{guest_id}/pdf", tags=["Raporlar"], summary="Form-C PDF indir")
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


@router.get("/api/reports/guests/pdf", tags=["Raporlar"], summary="Misafir listesi PDF")
async def download_guest_list_pdf(
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user=Depends(require_auth),
):
    query = {"status": {"$ne": "deleted"}}
    if status:
        query["status"] = status
    if date_from:
        try: query.setdefault("created_at", {})["$gte"] = datetime.fromisoformat(date_from)
        except ValueError: pass
    if date_to:
        try: query.setdefault("created_at", {})["$lte"] = datetime.fromisoformat(date_to)
        except ValueError: pass

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
