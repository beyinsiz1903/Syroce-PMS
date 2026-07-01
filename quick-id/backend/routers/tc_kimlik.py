"""TC Kimlik validation, Emniyet bildirimi (foreign-guest notice), and Form-C generation."""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from auth import require_auth
from db import db, guests_col
from helpers import create_audit_log, serialize_doc
from multi_property import list_properties
from schemas import EmniyetBildirimiRequest, TcKimlikValidateRequest
from tc_kimlik import generate_emniyet_bildirimi, is_foreign_guest, validate_tc_kimlik

router = APIRouter()


@router.post("/api/tc-kimlik/validate", tags=["TC Kimlik"], summary="TC Kimlik No doğrulama",
             description="TC Kimlik No'nun geçerliliğini matematiksel algoritma ile kontrol eder")
async def validate_tc(req: TcKimlikValidateRequest, user=Depends(require_auth)):
    return validate_tc_kimlik(req.tc_no)


@router.post("/api/tc-kimlik/emniyet-bildirimi", tags=["TC Kimlik"], summary="Emniyet bildirimi oluştur",
             description="Yabancı uyruklu misafir için Emniyet Müdürlüğü bildirim formu otomatik doldurur")
async def create_emniyet_bildirimi(req: EmniyetBildirimiRequest, user=Depends(require_auth)):
    try:
        guest = await guests_col.find_one({"_id": ObjectId(req.guest_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz misafir ID")
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")

    guest_data = serialize_doc(guest)
    if not is_foreign_guest(guest_data.get("nationality", "")):
        raise HTTPException(status_code=400, detail="Bu misafir yabancı uyruklu değil. Emniyet bildirimi sadece yabancı misafirler için gereklidir.")

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
    form["guest_id"] = req.guest_id
    form["created_by"] = user.get("email")
    await db["emniyet_bildirimleri"].insert_one(form)

    await create_audit_log(req.guest_id, "emniyet_bildirimi_created",
                           metadata={"form_id": form["form_id"]},
                           user_email=user.get("email"))
    return {"success": True, "form": form}


@router.get("/api/tc-kimlik/emniyet-bildirimleri", tags=["TC Kimlik"], summary="Emniyet bildirimleri listesi")
async def list_emniyet_bildirimleri(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user=Depends(require_auth),
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


@router.get("/api/tc-kimlik/form-c/{guest_id}", tags=["TC Kimlik"], summary="Form-C oluştur",
            description="Emniyet Müdürlüğü Form-C (yabancı misafir bildirim formu) formatında rapor oluşturur")
async def generate_form_c(guest_id: str, user=Depends(require_auth)):
    try:
        guest = await guests_col.find_one({"_id": ObjectId(guest_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz misafir ID")
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")

    guest_data = serialize_doc(guest)
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
    await db["form_c_records"].insert_one({**form_c, "created_at": datetime.now(timezone.utc)})
    return {"success": True, "form_c": form_c}
