"""
TC Kimlik No Doğrulama ve Emniyet Bildirimi Modülü
- TC Kimlik No algoritması ile doğrulama
- Emniyet bildirimi form verisi oluşturma (yabancı misafirler)
- Otomatik form doldurma
"""
from datetime import datetime, timezone
from typing import Optional
import uuid


def validate_tc_kimlik(tc_no: str) -> dict:
    """
    TC Kimlik No doğrulama algoritması.
    
    Kurallar:
    1. 11 haneli olmalı
    2. İlk hane 0 olamaz
    3. İlk 9 hanenin tek pozisyonların toplamı * 7 - çift pozisyonların toplamı mod 10 = 10. hane
    4. İlk 10 hanenin toplamı mod 10 = 11. hane
    """
    result = {
        "is_valid": False,
        "tc_no": tc_no,
        "errors": [],
        "checks": {
            "length": False,
            "numeric": False,
            "first_digit": False,
            "check_digit_10": False,
            "check_digit_11": False,
        }
    }
    
    if not tc_no:
        result["errors"].append("TC Kimlik No boş olamaz")
        return result
    
    # Strip whitespace
    tc_no = tc_no.strip()
    result["tc_no"] = tc_no
    
    # Length check
    if len(tc_no) != 11:
        result["errors"].append(f"TC Kimlik No 11 haneli olmalı (mevcut: {len(tc_no)} hane)")
        return result
    result["checks"]["length"] = True
    
    # Numeric check
    if not tc_no.isdigit():
        result["errors"].append("TC Kimlik No sadece rakamlardan oluşmalı")
        return result
    result["checks"]["numeric"] = True
    
    # First digit check
    if tc_no[0] == '0':
        result["errors"].append("TC Kimlik No'nun ilk hanesi 0 olamaz")
        return result
    result["checks"]["first_digit"] = True
    
    digits = [int(d) for d in tc_no]
    
    # 10th digit check
    # Odd positions (1,3,5,7,9) sum * 7 - Even positions (2,4,6,8) sum mod 10 = 10th digit
    odd_sum = sum(digits[i] for i in range(0, 9, 2))  # 1st, 3rd, 5th, 7th, 9th
    even_sum = sum(digits[i] for i in range(1, 8, 2))  # 2nd, 4th, 6th, 8th
    check_10 = (odd_sum * 7 - even_sum) % 10
    
    if check_10 != digits[9]:
        result["errors"].append(f"10. hane doğrulaması başarısız (beklenen: {check_10}, mevcut: {digits[9]})")
        return result
    result["checks"]["check_digit_10"] = True
    
    # 11th digit check
    # Sum of first 10 digits mod 10 = 11th digit
    check_11 = sum(digits[:10]) % 10
    if check_11 != digits[10]:
        result["errors"].append(f"11. hane doğrulaması başarısız (beklenen: {check_11}, mevcut: {digits[10]})")
        return result
    result["checks"]["check_digit_11"] = True
    
    result["is_valid"] = True
    return result


def generate_emniyet_bildirimi(guest_data: dict, hotel_data: dict = None) -> dict:
    """
    Emniyet Müdürlüğü yabancı misafir bildirim formu oluştur.
    
    Yasal zorunluluk: 5682 sayılı Pasaport Kanunu ve 
    6458 sayılı Yabancılar ve Uluslararası Koruma Kanunu gereği
    yabancı uyruklu misafirlerin 24 saat içinde bildirilmesi zorunludur.
    """
    if not hotel_data:
        hotel_data = {
            "hotel_name": "Otel İşletmesi",
            "hotel_address": "",
            "hotel_phone": "",
            "hotel_tax_no": "",
        }
    
    form_data = {
        "form_id": str(uuid.uuid4()),
        "form_type": "emniyet_yabanci_bildirimi",
        "form_title": "Yabancı Uyruklu Misafir Giriş Bildirim Formu",
        "yasal_dayanak": "5682 Sayılı Pasaport Kanunu, 6458 Sayılı YUKK",
        "bildirim_suresi": "24 saat içinde",
        "created_at": datetime.now(timezone.utc).isoformat(),
        
        # Tesis bilgileri
        "tesis_bilgileri": {
            "tesis_adi": hotel_data.get("hotel_name", ""),
            "tesis_adresi": hotel_data.get("hotel_address", ""),
            "tesis_telefon": hotel_data.get("hotel_phone", ""),
            "vergi_no": hotel_data.get("hotel_tax_no", ""),
        },
        
        # Misafir bilgileri
        "misafir_bilgileri": {
            "ad": guest_data.get("first_name", ""),
            "soyad": guest_data.get("last_name", ""),
            "uyruk": guest_data.get("nationality", ""),
            "dogum_tarihi": guest_data.get("birth_date", ""),
            "dogum_yeri": guest_data.get("birth_place", ""),
            "cinsiyet": guest_data.get("gender", ""),
            "anne_adi": guest_data.get("mother_name", ""),
            "baba_adi": guest_data.get("father_name", ""),
        },
        
        # Belge bilgileri
        "belge_bilgileri": {
            "belge_turu": guest_data.get("document_type", ""),
            "belge_no": guest_data.get("document_number", "") or guest_data.get("id_number", ""),
            "belge_gecerlilik": guest_data.get("expiry_date", ""),
            "veren_makam": "",
        },
        
        # Konaklama bilgileri
        "konaklama_bilgileri": {
            "giris_tarihi": guest_data.get("check_in_at", datetime.now(timezone.utc).isoformat()),
            "cikis_tarihi": guest_data.get("check_out_at", ""),
            "oda_no": guest_data.get("room_number", ""),
        },
        
        "status": "draft",
        "submitted_at": None,
        "notes": "Bu form otomatik olarak oluşturulmuştur. Emniyet Müdürlüğüne gönderilmeden önce kontrol ediniz.",
    }
    
    return form_data


def is_foreign_guest(nationality: str) -> bool:
    """Misafirin yabancı uyruklu olup olmadığını kontrol et"""
    if not nationality:
        return False
    turkey_codes = ["TC", "TR", "Türkiye", "Turkey", "Türk", "Turkish", "T.C."]
    return nationality.strip().upper() not in [c.upper() for c in turkey_codes]
