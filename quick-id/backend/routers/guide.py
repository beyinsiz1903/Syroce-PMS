"""API integration guide (public, no auth)."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/guide", tags=["API Rehberi"], summary="API Entegrasyon Rehberi",
            description="PMS entegrasyonu ve dış sistemler için kapsamlı API rehberi")
async def get_api_guide():
    return {
        "title": "Quick ID Reader - API Entegrasyon Rehberi",
        "version": "3.0.0",
        "base_url": "Deployment'a göre değişir",
        "authentication": {
            "type": "Bearer Token (JWT)",
            "login_endpoint": "POST /api/auth/login",
            "request_body": {"email": "string", "password": "string"},
            "response": {"token": "jwt_token_string", "user": {"id": "...", "email": "...", "role": "admin|reception"}},
            "header_format": "Authorization: Bearer <token>",
            "token_expiry": "24 saat (varsayılan)",
        },
        "endpoints": {
            "kimlik_tarama": {
                "scan": {
                    "method": "POST", "path": "/api/scan",
                    "description": "AI ile kimlik belgesi tarama (GPT-4o Vision)",
                    "request": {"image_base64": "base64_encoded_image_string"},
                    "response_fields": ["success", "scan", "extracted_data", "documents", "confidence"],
                    "rate_limit": "15/dakika",
                    "fallback": "AI başarısız olursa kullanıcıya yeniden çekim rehberliği",
                },
                "scans_list": {"method": "GET", "path": "/api/scans", "params": {"page": "int", "limit": "int"}},
                "review_queue": {"method": "GET", "path": "/api/scans/review-queue", "description": "Düşük güvenilirlik puanlı taramalar"},
            },
            "misafir_yonetimi": {
                "list": {"method": "GET", "path": "/api/guests", "params": ["page", "limit", "search", "status", "nationality", "document_type", "date_from", "date_to"]},
                "create": {"method": "POST", "path": "/api/guests", "body_fields": ["first_name", "last_name", "id_number", "birth_date", "gender", "nationality", "document_type", "kvkk_consent"]},
                "get": {"method": "GET", "path": "/api/guests/{id}"},
                "update": {"method": "PATCH", "path": "/api/guests/{id}"},
                "delete": {"method": "DELETE", "path": "/api/guests/{id}"},
                "checkin": {"method": "POST", "path": "/api/guests/{id}/checkin"},
                "checkout": {"method": "POST", "path": "/api/guests/{id}/checkout"},
                "duplicate_check": {"method": "GET", "path": "/api/guests/check-duplicate"},
            },
            "biyometrik": {
                "face_compare": {"method": "POST", "path": "/api/biometric/face-compare", "description": "Belge fotoğrafı vs canlı yüz karşılaştırma"},
                "liveness_challenge": {"method": "GET", "path": "/api/biometric/liveness-challenge", "description": "Canlılık testi sorusu al"},
                "liveness_check": {"method": "POST", "path": "/api/biometric/liveness-check", "description": "Canlılık testi doğrulama"},
            },
            "tc_kimlik": {
                "validate": {"method": "POST", "path": "/api/tc-kimlik/validate", "description": "TC Kimlik No doğrulama"},
                "emniyet_bildirimi": {"method": "POST", "path": "/api/tc-kimlik/emniyet-bildirimi", "description": "Yabancı misafir Emniyet bildirimi"},
            },
            "on_checkin": {
                "create_token": {"method": "POST", "path": "/api/precheckin/create", "description": "QR ön check-in token oluştur"},
                "get_token_info": {"method": "GET", "path": "/api/precheckin/{token_id}", "description": "Token bilgisi (public)"},
                "scan_with_token": {"method": "POST", "path": "/api/precheckin/{token_id}/scan", "description": "QR ile kimlik tara (public)"},
                "qr_code": {"method": "GET", "path": "/api/precheckin/{token_id}/qr", "description": "QR kod görüntüsü"},
                "list_tokens": {"method": "GET", "path": "/api/precheckin/list", "description": "Token listesi"},
            },
            "multi_property": {
                "list": {"method": "GET", "path": "/api/properties"},
                "create": {"method": "POST", "path": "/api/properties"},
                "get": {"method": "GET", "path": "/api/properties/{property_id}"},
                "update": {"method": "PATCH", "path": "/api/properties/{property_id}"},
            },
            "kiosk": {
                "create_session": {"method": "POST", "path": "/api/kiosk/session"},
                "list_sessions": {"method": "GET", "path": "/api/kiosk/sessions"},
            },
            "offline_sync": {
                "upload": {"method": "POST", "path": "/api/sync/upload"},
                "pending": {"method": "GET", "path": "/api/sync/pending"},
                "process": {"method": "POST", "path": "/api/sync/{sync_id}/process"},
            },
            "kvkk_uyumluluk": {
                "consent_info": {"method": "GET", "path": "/api/kvkk/consent-info", "description": "KVKK bilgilendirme metni (public)"},
                "settings": {"method": "GET/PATCH", "path": "/api/settings/kvkk"},
                "rights_request": {"method": "POST", "path": "/api/kvkk/rights-request"},
                "rights_list": {"method": "GET", "path": "/api/kvkk/rights-requests"},
                "verbis_report": {"method": "GET", "path": "/api/kvkk/verbis-report"},
                "data_inventory": {"method": "GET", "path": "/api/kvkk/data-inventory"},
                "retention_warnings": {"method": "GET", "path": "/api/kvkk/retention-warnings"},
            },
            "denetim": {
                "guest_audit": {"method": "GET", "path": "/api/guests/{id}/audit"},
                "recent_audit": {"method": "GET", "path": "/api/audit/recent"},
            },
            "dashboard": {"stats": {"method": "GET", "path": "/api/dashboard/stats"}},
            "disa_aktarim": {
                "json": {"method": "GET", "path": "/api/exports/guests.json"},
                "csv": {"method": "GET", "path": "/api/exports/guests.csv"},
            },
        },
        "pms_integration_guide": {
            "title": "PMS Entegrasyon Rehberi",
            "steps": [
                "1. POST /api/auth/login ile token alın",
                "2. POST /api/scan ile kimlik tarayın (base64 görüntü gönderin)",
                "3. POST /api/tc-kimlik/validate ile TC Kimlik doğrulayın (Türkiye vatandaşları)",
                "4. POST /api/biometric/face-compare ile yüz doğrulama yapın (opsiyonel)",
                "5. Dönen extracted_data ile POST /api/guests ile misafir oluşturun",
                "6. POST /api/guests/{id}/checkin ile check-in yapın",
                "7. Yabancı misafirler için POST /api/tc-kimlik/emniyet-bildirimi ile bildirim oluşturun",
                "8. POST /api/guests/{id}/checkout ile check-out yapın",
            ],
            "webhook_support": "Henüz desteklenmiyor - gelecek sürümde planlanıyor",
            "batch_operations": "Toplu tarama için /api/scan endpoint'ini ardışık çağırın",
        },
        "error_codes": {
            "400": "Geçersiz istek (eksik/hatalı parametre)",
            "401": "Kimlik doğrulama gerekli (token eksik/geçersiz)",
            "403": "Yetki yetersiz (admin yetkisi gerekli)",
            "404": "Kaynak bulunamadı",
            "429": "İstek limiti aşıldı (retry-after header'ına bakın)",
            "500": "Sunucu hatası (AI tarama hatası durumunda fallback_guidance alanını kontrol edin)",
        },
    }
