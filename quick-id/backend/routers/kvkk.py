"""KVKK compliance: rights requests, data access, VERBİS, retention, public consent, compliance reports."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import require_admin, require_auth
from db import db, guests_col
from helpers import serialize_doc
from kvkk import get_settings
from kvkk_compliance import (
    create_rights_request, list_rights_requests, process_rights_request,
    get_guest_data_for_access, export_guest_data_portable,
    generate_verbis_report, get_data_inventory, get_retention_warnings,
)
from schemas import RightsRequestCreate, RightsRequestProcess

router = APIRouter()


@router.post("/api/kvkk/rights-request", tags=["KVKK Uyumluluk"], summary="KVKK hak talebi oluştur",
             description="Misafir veya ilgili kişi adına KVKK hak talebi oluşturur (erişim, düzeltme, silme, taşıma, itiraz)")
async def create_kvkk_request(req: RightsRequestCreate, user=Depends(require_auth)):
    try:
        result = await create_rights_request(
            db, request_type=req.request_type, guest_id=req.guest_id,
            requester_name=req.requester_name, requester_email=req.requester_email,
            requester_id_number=req.requester_id_number, description=req.description,
            created_by=user.get("email"),
        )
        return {"success": True, "request": serialize_doc(result)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/kvkk/rights-requests", tags=["KVKK Uyumluluk"], summary="KVKK hak taleplerini listele")
async def get_kvkk_requests(
    status: Optional[str] = None, request_type: Optional[str] = None,
    page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
    user=Depends(require_admin),
):
    return await list_rights_requests(db, status=status, request_type=request_type, page=page, limit=limit)


@router.patch("/api/kvkk/rights-requests/{request_id}", tags=["KVKK Uyumluluk"], summary="KVKK hak talebini işle")
async def process_kvkk_request(request_id: str, req: RightsRequestProcess, user=Depends(require_admin)):
    try:
        result = await process_rights_request(
            db, request_id=request_id, new_status=req.status,
            response_note=req.response_note, response_data=req.response_data,
            processed_by=user.get("email"),
        )
        if not result:
            raise HTTPException(status_code=404, detail="Talep bulunamadı")
        return {"success": True, "request": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/kvkk/guest-data/{guest_id}", tags=["KVKK Uyumluluk"], summary="Misafir veri erişim raporu",
            description="KVKK erişim hakkı kapsamında misafirin tüm kişisel verilerini derler")
async def get_guest_kvkk_data(guest_id: str, user=Depends(require_admin)):
    data = await get_guest_data_for_access(db, guest_id)
    if not data:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")
    return data


@router.get("/api/kvkk/guest-data/{guest_id}/portable", tags=["KVKK Uyumluluk"], summary="Veri taşınabilirlik dışa aktarımı",
            description="KVKK veri taşıma hakkı kapsamında misafir verilerini taşınabilir formatta dışa aktarır")
async def export_guest_portable(guest_id: str, user=Depends(require_admin)):
    data = await export_guest_data_portable(db, guest_id)
    if not data:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")
    return data


@router.get("/api/kvkk/verbis-report", tags=["KVKK Uyumluluk"], summary="VERBİS uyumluluk raporu",
            description="KVKK Madde 16 kapsamında VERBİS uyumluluk raporu üretir")
async def get_verbis_report(user=Depends(require_admin)):
    return await generate_verbis_report(db)


@router.get("/api/kvkk/data-inventory", tags=["KVKK Uyumluluk"], summary="Veri işleme envanteri",
            description="Sistemdeki tüm veri koleksiyonları ve işleme detaylarının envanterini sunar")
async def get_kvkk_data_inventory(user=Depends(require_admin)):
    return await get_data_inventory(db)


@router.get("/api/kvkk/retention-warnings", tags=["KVKK Uyumluluk"], summary="Saklama süresi uyarıları",
            description="Saklama süresine yaklaşan veya aşan veriler için uyarılar üretir")
async def get_kvkk_retention_warnings(user=Depends(require_admin)):
    return await get_retention_warnings(db)


@router.get("/api/kvkk/consent-info", tags=["KVKK Uyumluluk"], summary="KVKK bilgilendirme metni (public)",
            description="Misafirlerin görmesi gereken KVKK aydınlatma metni. Kimlik doğrulama gerektirmez.")
async def get_kvkk_consent_info():
    settings = await get_settings(db)
    return {
        "consent_required": settings.get("kvkk_consent_required", True),
        "consent_text": settings.get("kvkk_consent_text", """
KVKK AYDINLATMA METNİ

6698 Sayılı Kişisel Verilerin Korunması Kanunu kapsamında, otelimizde konaklama hizmeti alırken aşağıdaki kişisel verileriniz işlenmektedir:

İŞLENEN VERİLER:
• Kimlik Bilgileri: Ad, soyad, TC kimlik no/pasaport no, doğum tarihi, cinsiyet, uyruk
• Belge Bilgileri: Kimlik belgesi türü, belge numarası, geçerlilik tarihi
• Konaklama Bilgileri: Giriş-çıkış tarihleri
• Biyometrik Veri: Kimlik belgesi görüntüsü (sadece tarama amacıyla, saklanmaz*)

İŞLEME AMACI:
1. Konaklama hizmeti sunumu (Yasal zorunluluk - 1774 sayılı Kimlik Bildirme Kanunu)
2. Emniyet Müdürlüğü bildirimi (Yasal zorunluluk - 5682 sayılı Pasaport Kanunu)
3. Kimlik doğrulama (AI destekli belge okuma)

HUKUKİ DAYANAK:
• KVKK Madde 5/2-ç: Veri sorumlusunun hukuki yükümlülüğü
• KVKK Madde 5/2-c: Sözleşmenin ifası

VERİ AKTARIMI:
• Emniyet Müdürlüğü (yasal zorunluluk)
• OpenAI API (kimlik tarama işleme, veri saklanmaz)

SAKLAMA SÜRESİ:
• Kişisel veriler: Konaklama süresi + yasal saklama süresi
• Kimlik görüntüleri: Tarama sonrası saklanmaz*

HAKLARINIZ (KVKK Madde 11):
1. Kişisel verilerinizin işlenip işlenmediğini öğrenme
2. Kişisel verileriniz işlenmişse bilgi talep etme
3. İşlenme amacını öğrenme
4. Yurt içinde/dışında aktarıldığı kişileri bilme
5. Eksik/yanlış işlenmişse düzeltme talep etme
6. Silinme/yok edilme talep etme
7. Düzeltme/silinme işlemlerinin aktarıldığı kişilere bildirilmesini talep etme
8. İtiraz etme
9. Zarar halinde tazminat talep etme

Haklarınızı kullanmak için resepsiyon yetkilisine başvurabilirsiniz.
        """),
        "data_processing_purpose": settings.get("data_processing_purpose", "Konaklama hizmeti kapsamında yasal zorunluluk"),
        "data_controller": {"title": "Veri Sorumlusu", "note": "Otel İşletmesi"},
        "rights": [
            {"code": "access", "title": "Erişim Hakkı", "description": "Kişisel verilerinize erişim talep edebilirsiniz"},
            {"code": "rectification", "title": "Düzeltme Hakkı", "description": "Yanlış/eksik verilerin düzeltilmesini talep edebilirsiniz"},
            {"code": "erasure", "title": "Silme Hakkı", "description": "Verilerinizin silinmesini talep edebilirsiniz"},
            {"code": "portability", "title": "Taşıma Hakkı", "description": "Verilerinizi taşınabilir formatta alabilirsiniz"},
            {"code": "objection", "title": "İtiraz Hakkı", "description": "Veri işlemeye itiraz edebilirsiniz"},
        ],
    }


@router.get("/api/compliance/reports", tags=["KVKK Uyumluluk"], summary="Yasal uyumluluk raporları",
            description="Emniyet bildirimi, KVKK ve konaklama yasal uyumluluk raporları")
async def get_compliance_reports(user=Depends(require_admin)):
    emniyet_col = db["emniyet_bildirimleri"]
    total_emniyet = await emniyet_col.count_documents({})
    draft_emniyet = await emniyet_col.count_documents({"status": "draft"})
    submitted_emniyet = await emniyet_col.count_documents({"status": "submitted"})
    form_c_col = db["form_c_records"]
    total_form_c = await form_c_col.count_documents({})
    kvkk_col = db["kvkk_rights_requests"]
    total_kvkk = await kvkk_col.count_documents({})
    pending_kvkk = await kvkk_col.count_documents({"status": "pending"})
    completed_kvkk = await kvkk_col.count_documents({"status": "completed"})
    foreign_guests = await guests_col.count_documents({
        "nationality": {"$nin": ["TC", "TR", "Türkiye", "Turkey", "Türk", "Turkish", "T.C."], "$ne": None, "$exists": True},
    })
    return {
        "emniyet_bildirimleri": {"toplam": total_emniyet, "taslak": draft_emniyet, "gonderilmis": submitted_emniyet},
        "form_c": {"toplam": total_form_c},
        "kvkk": {"toplam_talep": total_kvkk, "bekleyen": pending_kvkk, "tamamlanan": completed_kvkk},
        "yabanci_misafir": {"toplam": foreign_guests},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
