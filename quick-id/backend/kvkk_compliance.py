"""
KVKK (6698 Sayılı Kişisel Verilerin Korunması Kanunu) Tam Uyumluluk Modülü
- Misafir hakları yönetimi (erişim, düzeltme, silme, taşıma)
- VERBİS uyumluluk raporu
- Veri işleme envanteri
- Saklama süresi uyarıları ve periyodik temizlik
- Rıza yönetimi
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
import uuid
import json


# ============== KVKK Hak Talepleri ==============

VALID_REQUEST_TYPES = [
    "access",         # Erişim hakkı (Madde 11/1-a,b,c)
    "rectification",  # Düzeltme hakkı (Madde 11/1-d)
    "erasure",        # Silme/yok etme hakkı (Madde 11/1-e)
    "portability",    # Veri taşıma hakkı (Madde 11/1-ç)
    "objection",      # İtiraz hakkı (Madde 11/1-f,g)
]

VALID_REQUEST_STATUSES = [
    "pending",      # Beklemede
    "in_progress",  # İşleniyor
    "completed",    # Tamamlandı
    "rejected",     # Reddedildi
]


async def create_rights_request(
    db: AsyncIOMotorDatabase,
    request_type: str,
    guest_id: Optional[str],
    requester_name: str,
    requester_email: str,
    requester_id_number: Optional[str],
    description: str,
    created_by: Optional[str] = None
) -> dict:
    """Yeni KVKK hak talebi oluştur"""
    if request_type not in VALID_REQUEST_TYPES:
        raise ValueError(f"Geçersiz talep türü: {request_type}")

    request_doc = {
        "request_id": str(uuid.uuid4()),
        "request_type": request_type,
        "guest_id": guest_id,
        "requester_name": requester_name,
        "requester_email": requester_email,
        "requester_id_number": requester_id_number,
        "description": description,
        "status": "pending",
        "status_history": [
            {
                "status": "pending",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": "Talep oluşturuldu",
                "by": created_by
            }
        ],
        "response": None,
        "response_data": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "completed_at": None,
        "created_by": created_by,
        # KVKK 30 gün yanıt süresi
        "deadline": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    }

    col = db["kvkk_requests"]
    result = await col.insert_one(request_doc)
    request_doc["_id"] = result.inserted_id
    return request_doc


async def list_rights_requests(
    db: AsyncIOMotorDatabase,
    status: Optional[str] = None,
    request_type: Optional[str] = None,
    page: int = 1,
    limit: int = 20
) -> dict:
    """KVKK hak taleplerini listele"""
    col = db["kvkk_requests"]
    query = {}
    if status:
        query["status"] = status
    if request_type:
        query["request_type"] = request_type

    total = await col.count_documents(query)
    skip = (page - 1) * limit
    cursor = col.find(query).sort("created_at", -1).skip(skip).limit(limit)
    requests = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        requests.append(doc)
    return {"requests": requests, "total": total, "page": page, "limit": limit}


async def process_rights_request(
    db: AsyncIOMotorDatabase,
    request_id: str,
    new_status: str,
    response_note: str,
    response_data: Optional[dict] = None,
    processed_by: Optional[str] = None
) -> dict:
    """KVKK hak talebini işle"""
    if new_status not in VALID_REQUEST_STATUSES:
        raise ValueError(f"Geçersiz durum: {new_status}")

    col = db["kvkk_requests"]
    doc = await col.find_one({"request_id": request_id})
    if not doc:
        return None

    update = {
        "status": new_status,
        "response": response_note,
        "updated_at": datetime.now(timezone.utc),
    }
    if response_data:
        update["response_data"] = response_data
    if new_status in ("completed", "rejected"):
        update["completed_at"] = datetime.now(timezone.utc)

    # Append to status history
    history_entry = {
        "status": new_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": response_note,
        "by": processed_by
    }

    await col.update_one(
        {"request_id": request_id},
        {
            "$set": update,
            "$push": {"status_history": history_entry}
        }
    )

    updated = await col.find_one({"request_id": request_id})
    updated["id"] = str(updated.pop("_id"))
    return updated


async def get_guest_data_for_access(db: AsyncIOMotorDatabase, guest_id: str) -> dict:
    """Misafir erişim hakkı: tüm kişisel verileri derle"""
    guest = await db["guests"].find_one({"_id": ObjectId(guest_id)})
    if not guest:
        return None

    # İlişkili tarama kayıtları
    scans = []
    if guest.get("scan_ids"):
        for sid in guest["scan_ids"]:
            scan = await db["scans"].find_one({"_id": ObjectId(sid)}) if ObjectId.is_valid(sid) else None
            if scan:
                scan["id"] = str(scan.pop("_id"))
                scans.append(scan)

    # Denetim kayıtları
    audit_cursor = db["audit_logs"].find({"guest_id": guest_id}).sort("created_at", -1)
    audit_logs = []
    async for log in audit_cursor:
        log["id"] = str(log.pop("_id"))
        audit_logs.append(log)

    guest["id"] = str(guest.pop("_id"))

    return {
        "guest": guest,
        "scans": scans,
        "audit_logs": audit_logs,
        "data_categories": [
            {"category": "Kimlik Bilgileri", "fields": ["first_name", "last_name", "id_number", "birth_date", "gender", "nationality", "birth_place"]},
            {"category": "Belge Bilgileri", "fields": ["document_type", "document_number", "expiry_date", "issue_date"]},
            {"category": "Aile Bilgileri", "fields": ["mother_name", "father_name"]},
            {"category": "İletişim Bilgileri", "fields": ["address"]},
            {"category": "Konaklama Bilgileri", "fields": ["status", "check_in_at", "check_out_at"]},
            {"category": "Teknik Bilgiler", "fields": ["created_at", "updated_at", "scan_ids"]},
        ],
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


async def export_guest_data_portable(db: AsyncIOMotorDatabase, guest_id: str) -> dict:
    """Veri taşınabilirlik hakkı: JSON formatında dışa aktar"""
    data = await get_guest_data_for_access(db, guest_id)
    if not data:
        return None

    # Sanitize for portability - remove internal fields
    portable = {
        "format": "KVKK Veri Taşınabilirlik Formatı",
        "version": "1.0",
        "exported_at": data["exported_at"],
        "personal_data": {},
    }

    guest = data["guest"]
    portable_fields = [
        "first_name", "last_name", "id_number", "birth_date", "gender",
        "nationality", "birth_place", "document_type", "document_number",
        "expiry_date", "issue_date", "mother_name", "father_name", "address",
        "check_in_at", "check_out_at", "notes"
    ]
    for f in portable_fields:
        if guest.get(f):
            portable["personal_data"][f] = str(guest[f]) if not isinstance(guest[f], str) else guest[f]

    return portable


# ============== VERBİS Uyumluluk Raporu ==============

async def generate_verbis_report(db: AsyncIOMotorDatabase) -> dict:
    """KVKK Madde 16 - VERBİS (Veri Sorumluları Sicil Bilgi Sistemi) uyumluluk raporu"""
    from kvkk import get_settings

    settings = await get_settings(db)
    total_guests = await db["guests"].count_documents({"anonymized": {"$ne": True}})
    total_anonymized = await db["guests"].count_documents({"anonymized": True})
    total_scans = await db["scans"].count_documents({})
    total_audit = await db["audit_logs"].count_documents({})
    total_users = await db["users"].count_documents({})
    pending_requests = await db["kvkk_requests"].count_documents({"status": "pending"})
    total_requests = await db["kvkk_requests"].count_documents({})

    # Consent stats
    with_consent = await db["guests"].count_documents({"kvkk_consent": True, "anonymized": {"$ne": True}})
    without_consent = await db["guests"].count_documents({"kvkk_consent": {"$ne": True}, "anonymized": {"$ne": True}})

    return {
        "report_title": "VERBİS Uyumluluk Raporu",
        "report_date": datetime.now(timezone.utc).isoformat(),
        "veri_sorumlusu": {
            "unvan": "Otel İşletmesi",
            "sicil_no": "Henüz atanmadı",
            "note": "VERBİS kaydı yapılmalıdır"
        },
        "veri_kategorileri": [
            {
                "kategori": "Kimlik Bilgileri",
                "aciklama": "Ad, soyad, TCKN, doğum tarihi, cinsiyet, uyruk",
                "isleme_amaci": "Konaklama hizmetleri kapsamında yasal zorunluluk (5651 sayılı kanun, Pasaport Kanunu)",
                "hukuki_dayanak": "KVKK Madde 5/2-ç (Hukuki yükümlülük)",
                "saklama_suresi": f"{settings.get('retention_days_scans', 90)} gün (tarama kayıtları)",
                "aktarim": "Emniyet Müdürlüğü (yasal zorunluluk)",
                "kayit_sayisi": total_guests
            },
            {
                "kategori": "Belge Bilgileri",
                "aciklama": "Belge türü, belge numarası, geçerlilik tarihi",
                "isleme_amaci": "Kimlik doğrulama ve konaklama kaydı",
                "hukuki_dayanak": "KVKK Madde 5/2-ç (Hukuki yükümlülük)",
                "saklama_suresi": f"{settings.get('retention_days_scans', 90)} gün",
                "aktarim": "Yok",
                "kayit_sayisi": total_guests
            },
            {
                "kategori": "Konaklama Bilgileri",
                "aciklama": "Check-in/check-out tarihleri, oda bilgileri",
                "isleme_amaci": "Konaklama hizmeti sunumu",
                "hukuki_dayanak": "KVKK Madde 5/2-c (Sözleşmenin ifası)",
                "saklama_suresi": "Konaklama süresi + yasal saklama",
                "aktarim": "Yok",
                "kayit_sayisi": total_guests
            },
            {
                "kategori": "Biyometrik Veri (Kimlik Görüntüsü)",
                "aciklama": "Kimlik belgesi tarama görüntüleri",
                "isleme_amaci": "Kimlik doğrulama (AI OCR ile veri çıkarımı)",
                "hukuki_dayanak": "KVKK Madde 6 (Açık rıza)",
                "saklama_suresi": f"{'Saklanmıyor' if not settings.get('store_scan_images') else str(settings.get('retention_days_scans', 90)) + ' gün'}",
                "aktarim": "OpenAI API (işleme amaçlı, saklanmıyor)",
                "kayit_sayisi": total_scans
            },
            {
                "kategori": "Sistem/Denetim Kayıtları",
                "aciklama": "İşlem logları, değişiklik geçmişi",
                "isleme_amaci": "Denetim ve güvenlik",
                "hukuki_dayanak": "KVKK Madde 12 (Veri güvenliği)",
                "saklama_suresi": f"{settings.get('retention_days_audit', 365)} gün",
                "aktarim": "Yok",
                "kayit_sayisi": total_audit
            }
        ],
        "teknik_tedbirler": [
            "JWT tabanlı kimlik doğrulama",
            "Rol bazlı erişim kontrolü (RBAC)",
            "Şifre hash'leme (bcrypt)",
            "HTTPS iletişim şifrelemesi",
            "Rate limiting (istek sınırlama)",
            "Denetim izi (audit trail)",
            "Otomatik veri temizleme mekanizması",
            "Anonimleştirme (unutulma hakkı)"
        ],
        "idari_tedbirler": [
            "KVKK bilgilendirme ve aydınlatma metni",
            "Açık rıza mekanizması",
            "Veri saklama ve imha politikası",
            "Hak talebi yönetim süreci",
            "Periyodik veri temizliği"
        ],
        "istatistikler": {
            "toplam_misafir": total_guests,
            "anonimlestirilmis": total_anonymized,
            "toplam_tarama": total_scans,
            "toplam_denetim_kaydi": total_audit,
            "toplam_kullanici": total_users,
            "rizali_misafir": with_consent,
            "rizasiz_misafir": without_consent,
            "bekleyen_talepler": pending_requests,
            "toplam_talepler": total_requests,
        },
        "uyumluluk_durumu": {
            "aydinlatma_metni": bool(settings.get("kvkk_consent_text")),
            "riza_mekanizmasi": settings.get("kvkk_consent_required", False),
            "veri_saklama_politikasi": settings.get("auto_cleanup_enabled", False),
            "hak_talebi_sureci": True,
            "anonimlestime": True,
            "denetim_izi": True,
            "erisim_kontrolu": True,
            "verbis_kaydi": False,
        },
        "settings": settings
    }


# ============== Veri İşleme Envanteri ==============

async def get_data_inventory(db: AsyncIOMotorDatabase) -> dict:
    """Veri işleme envanteri / kayıt defteri"""
    from kvkk import get_settings
    settings = await get_settings(db)

    # Collection stats
    guests_count = await db["guests"].count_documents({})
    scans_count = await db["scans"].count_documents({})
    audit_count = await db["audit_logs"].count_documents({})
    users_count = await db["users"].count_documents({})
    requests_count = await db["kvkk_requests"].count_documents({})

    # Date ranges
    oldest_guest = await db["guests"].find_one(sort=[("created_at", 1)])
    newest_guest = await db["guests"].find_one(sort=[("created_at", -1)])
    oldest_scan = await db["scans"].find_one(sort=[("created_at", 1)])
    newest_scan = await db["scans"].find_one(sort=[("created_at", -1)])

    return {
        "envanter_tarihi": datetime.now(timezone.utc).isoformat(),
        "koleksiyonlar": [
            {
                "ad": "guests",
                "aciklama": "Misafir kişisel bilgileri",
                "kayit_sayisi": guests_count,
                "kisisel_veri_iceriyor": True,
                "hassas_veri": True,
                "saklama_politikasi": "Konaklama süresi + yasal saklama süresi",
                "en_eski_kayit": oldest_guest["created_at"].isoformat() if oldest_guest and "created_at" in oldest_guest else None,
                "en_yeni_kayit": newest_guest["created_at"].isoformat() if newest_guest and "created_at" in newest_guest else None,
                "alanlar": [
                    {"alan": "first_name", "tip": "Kimlik", "zorunlu": False},
                    {"alan": "last_name", "tip": "Kimlik", "zorunlu": False},
                    {"alan": "id_number", "tip": "Kimlik (TCKN/Pasaport)", "zorunlu": False},
                    {"alan": "birth_date", "tip": "Kimlik", "zorunlu": False},
                    {"alan": "gender", "tip": "Kimlik", "zorunlu": False},
                    {"alan": "nationality", "tip": "Kimlik", "zorunlu": False},
                    {"alan": "birth_place", "tip": "Kimlik", "zorunlu": False},
                    {"alan": "mother_name", "tip": "Aile", "zorunlu": False},
                    {"alan": "father_name", "tip": "Aile", "zorunlu": False},
                    {"alan": "address", "tip": "İletişim", "zorunlu": False},
                    {"alan": "document_type", "tip": "Belge", "zorunlu": False},
                    {"alan": "document_number", "tip": "Belge", "zorunlu": False},
                ]
            },
            {
                "ad": "scans",
                "aciklama": "Kimlik tarama kayıtları ve AI çıkarım sonuçları",
                "kayit_sayisi": scans_count,
                "kisisel_veri_iceriyor": True,
                "hassas_veri": True,
                "saklama_politikasi": f"{settings.get('retention_days_scans', 90)} gün",
                "en_eski_kayit": oldest_scan["created_at"].isoformat() if oldest_scan and "created_at" in oldest_scan else None,
                "en_yeni_kayit": newest_scan["created_at"].isoformat() if newest_scan and "created_at" in newest_scan else None,
            },
            {
                "ad": "audit_logs",
                "aciklama": "Denetim kayıtları ve değişiklik geçmişi",
                "kayit_sayisi": audit_count,
                "kisisel_veri_iceriyor": True,
                "hassas_veri": False,
                "saklama_politikasi": f"{settings.get('retention_days_audit', 365)} gün",
            },
            {
                "ad": "users",
                "aciklama": "Sistem kullanıcıları",
                "kayit_sayisi": users_count,
                "kisisel_veri_iceriyor": True,
                "hassas_veri": False,
                "saklama_politikasi": "Hesap aktif olduğu sürece",
            },
            {
                "ad": "kvkk_requests",
                "aciklama": "KVKK hak talepleri",
                "kayit_sayisi": requests_count,
                "kisisel_veri_iceriyor": True,
                "hassas_veri": False,
                "saklama_politikasi": "5 yıl (yasal zorunluluk)",
            },
        ],
        "veri_akisi": [
            {
                "kaynak": "Kimlik belgesi (kamera/yükleme)",
                "hedef": "OpenAI GPT-4o Vision API",
                "amac": "Kimlik bilgisi çıkarımı (OCR)",
                "yontem": "Base64 görüntü gönderimi",
                "not": "Görüntü OpenAI tarafında saklanmaz (API policy)"
            },
            {
                "kaynak": "AI çıkarım sonuçları",
                "hedef": "MongoDB (scans koleksiyonu)",
                "amac": "Tarama kaydı saklama",
                "yontem": "JSON yapılandırılmış veri"
            },
            {
                "kaynak": "Operatör girişi/düzenlemesi",
                "hedef": "MongoDB (guests koleksiyonu)",
                "amac": "Misafir kaydı oluşturma/güncelleme",
                "yontem": "REST API"
            }
        ]
    }


# ============== Saklama Süresi Uyarıları ==============

async def get_retention_warnings(db: AsyncIOMotorDatabase) -> dict:
    """Saklama süresine yaklaşan veya aşan verilerin uyarıları"""
    from kvkk import get_settings
    settings = await get_settings(db)

    now = datetime.now(timezone.utc)
    warnings = []

    # Scans approaching retention
    scan_retention = settings.get("retention_days_scans", 90)
    warn_threshold = scan_retention - 7  # 7 gün öncesinden uyar
    if warn_threshold > 0:
        warn_cutoff = now - timedelta(days=warn_threshold)
        expire_cutoff = now - timedelta(days=scan_retention)

        expiring_scans = await db["scans"].count_documents({
            "created_at": {"$lt": warn_cutoff, "$gte": expire_cutoff}
        })
        expired_scans = await db["scans"].count_documents({
            "created_at": {"$lt": expire_cutoff}
        })

        if expiring_scans > 0:
            warnings.append({
                "type": "warning",
                "category": "scans",
                "message": f"{expiring_scans} tarama kaydı {scan_retention} günlük saklama süresine yaklaşıyor",
                "count": expiring_scans,
                "action": "Otomatik temizlik çalıştırın veya saklama süresini güncelleyin"
            })
        if expired_scans > 0:
            warnings.append({
                "type": "critical",
                "category": "scans",
                "message": f"{expired_scans} tarama kaydı saklama süresini aştı ve silinmeli",
                "count": expired_scans,
                "action": "Hemen temizlik çalıştırın"
            })

    # Audit logs approaching retention
    audit_retention = settings.get("retention_days_audit", 365)
    audit_warn = audit_retention - 30  # 30 gün öncesinden uyar
    if audit_warn > 0:
        audit_warn_cutoff = now - timedelta(days=audit_warn)
        audit_expire_cutoff = now - timedelta(days=audit_retention)

        expiring_audits = await db["audit_logs"].count_documents({
            "created_at": {"$lt": audit_warn_cutoff, "$gte": audit_expire_cutoff}
        })
        expired_audits = await db["audit_logs"].count_documents({
            "created_at": {"$lt": audit_expire_cutoff}
        })

        if expiring_audits > 0:
            warnings.append({
                "type": "warning",
                "category": "audit_logs",
                "message": f"{expiring_audits} denetim kaydı saklama süresine yaklaşıyor",
                "count": expiring_audits,
                "action": "Otomatik temizliği kontrol edin"
            })
        if expired_audits > 0:
            warnings.append({
                "type": "critical",
                "category": "audit_logs",
                "message": f"{expired_audits} denetim kaydı saklama süresini aştı",
                "count": expired_audits,
                "action": "Hemen temizlik çalıştırın"
            })

    # Pending KVKK requests approaching deadline
    overdue_requests = await db["kvkk_requests"].count_documents({
        "status": "pending",
        "deadline": {"$lt": now.isoformat()}
    })
    if overdue_requests > 0:
        warnings.append({
            "type": "critical",
            "category": "kvkk_requests",
            "message": f"{overdue_requests} KVKK hak talebi 30 günlük yanıt süresini aştı!",
            "count": overdue_requests,
            "action": "Acil olarak talepleri yanıtlayın"
        })

    approaching_deadline = await db["kvkk_requests"].count_documents({
        "status": "pending",
        "deadline": {
            "$gte": now.isoformat(),
            "$lt": (now + timedelta(days=7)).isoformat()
        }
    })
    if approaching_deadline > 0:
        warnings.append({
            "type": "warning",
            "category": "kvkk_requests",
            "message": f"{approaching_deadline} KVKK hak talebinin son yanıt tarihine 7 günden az kaldı",
            "count": approaching_deadline,
            "action": "Talepleri inceleyin"
        })

    # Guests without consent
    no_consent = await db["guests"].count_documents({
        "kvkk_consent": {"$ne": True},
        "anonymized": {"$ne": True}
    })
    if no_consent > 0:
        warnings.append({
            "type": "info",
            "category": "consent",
            "message": f"{no_consent} misafirin KVKK açık rızası alınmamış",
            "count": no_consent,
            "action": "Rıza durumlarını kontrol edin"
        })

    return {
        "warnings": warnings,
        "total_warnings": len(warnings),
        "critical_count": sum(1 for w in warnings if w["type"] == "critical"),
        "warning_count": sum(1 for w in warnings if w["type"] == "warning"),
        "info_count": sum(1 for w in warnings if w["type"] == "info"),
        "checked_at": now.isoformat(),
        "settings": {
            "scan_retention_days": settings.get("retention_days_scans", 90),
            "audit_retention_days": settings.get("retention_days_audit", 365),
            "auto_cleanup_enabled": settings.get("auto_cleanup_enabled", False),
        }
    }


# ============== Confidence Scoring ==============

def calculate_confidence_score(extracted_data: dict) -> dict:
    """AI tarama sonucuna güvenilirlik puanı hesapla"""
    documents = extracted_data.get("documents", [])
    if not documents:
        return {"overall_score": 0, "review_needed": True, "details": []}

    doc_scores = []
    for doc in documents:
        score = 0
        max_score = 100
        details = {}

        # is_valid check (20 points)
        if doc.get("is_valid"):
            score += 20
            details["is_valid"] = {"score": 20, "max": 20}
        else:
            details["is_valid"] = {"score": 0, "max": 20, "note": "Belge geçersiz"}

        # Key fields completeness (50 points)
        key_fields = {
            "first_name": 10,
            "last_name": 10,
            "id_number": 10,
            "birth_date": 8,
            "document_type": 7,
            "nationality": 5,
        }
        for field, points in key_fields.items():
            val = doc.get(field)
            if val and str(val).strip() and val != "null":
                score += points
                details[field] = {"score": points, "max": points}
            else:
                details[field] = {"score": 0, "max": points, "note": "Eksik alan"}

        # Secondary fields (15 points)
        secondary_fields = ["gender", "expiry_date", "document_number", "birth_place"]
        secondary_per = 15 / len(secondary_fields)
        for field in secondary_fields:
            val = doc.get(field)
            if val and str(val).strip() and val != "null":
                score += secondary_per
                details[field] = {"score": round(secondary_per, 1), "max": round(secondary_per, 1)}

        # Warnings penalty (15 points)
        warnings = doc.get("warnings", [])
        if len(warnings) == 0:
            score += 15
            details["warnings"] = {"score": 15, "max": 15}
        elif len(warnings) <= 2:
            score += 8
            details["warnings"] = {"score": 8, "max": 15, "note": f"{len(warnings)} uyarı"}
        else:
            details["warnings"] = {"score": 0, "max": 15, "note": f"{len(warnings)} uyarı"}

        doc_scores.append({
            "score": round(min(score, 100), 1),
            "details": details,
            "document_type": doc.get("document_type", "unknown")
        })

    overall = round(sum(d["score"] for d in doc_scores) / len(doc_scores), 1) if doc_scores else 0

    return {
        "overall_score": overall,
        "document_scores": doc_scores,
        "review_needed": overall < 70,
        "confidence_level": "high" if overall >= 85 else "medium" if overall >= 70 else "low"
    }
