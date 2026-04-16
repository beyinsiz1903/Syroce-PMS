"""
Geliştirilmiş Offline OCR Fallback (Tesseract)
- Görüntü ön işleme (eğrilik düzeltme, kontrast artırma, gürültü azaltma)
- İnternet kesintisinde lokal OCR
- Tesseract ile metin çıkarımı
- Gelişmiş veri yapılandırma
- MRZ okuma desteği
- Güven puanı hesaplama
- Otomatik fallback (AI başarısız olunca)
"""
import base64
import io
import re
from typing import Optional
from datetime import datetime, timezone

try:
    import pytesseract
    from PIL import Image, ImageFilter, ImageEnhance
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from mrz_parser import detect_and_parse_mrz


def is_tesseract_available() -> bool:
    """Tesseract'ın kurulu olup olmadığını kontrol et"""
    if not TESSERACT_AVAILABLE:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def preprocess_image_pil(img: Image.Image) -> Image.Image:
    """PIL ile görüntü ön işleme"""
    # Griye çevir
    if img.mode != 'L':
        img = img.convert('L')

    # Kontrast artırma
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)

    # Keskinlik artırma
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(2.0)

    # Parlaklık normalizasyonu
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(1.1)

    return img


def preprocess_image_cv2(img_bytes: bytes) -> Optional[bytes]:
    """OpenCV ile gelişmiş görüntü ön işleme"""
    if not CV2_AVAILABLE:
        return None

    try:
        # Bytes'ı numpy array'e çevir
        img_array = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if img is None:
            return None

        # Griye çevir
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Gürültü azaltma
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

        # CLAHE ile kontrast artırma
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        # Eğrilik düzeltme (deskew)
        enhanced = deskew_image(enhanced)

        # Adaptive thresholding - belge metinleri için
        thresh = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

        # Morfolojik temizlik (küçük gürültüyü kaldır)
        kernel = np.ones((1, 1), np.uint8)
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

        # PNG olarak encode et
        _, buffer = cv2.imencode('.png', cleaned)
        return buffer.tobytes()

    except Exception:
        return None


def deskew_image(img: object) -> object:
    """Görüntü eğrilik düzeltme (deskew)"""
    if not CV2_AVAILABLE:
        return img

    try:
        # Kenarları bul
        coords = np.column_stack(np.where(img > 0))
        if coords.shape[0] < 10:
            return img

        # Minimum bounding box ile açı bul
        angle = cv2.minAreaRect(coords)[-1]

        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        # Çok küçük açıları atla
        if abs(angle) < 0.5:
            return img

        # Büyük açıları atla (muhtemelen hata)
        if abs(angle) > 30:
            return img

        # Döndür
        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        return rotated

    except Exception:
        return img


def ocr_extract_text(image_base64: str, lang: str = "tur+eng", preprocess: bool = True) -> str:
    """Base64 görüntüden metin çıkar (geliştirilmiş ön işleme ile)"""
    if not TESSERACT_AVAILABLE:
        raise RuntimeError("Tesseract OCR kurulu değil")

    if "," in image_base64:
        image_base64 = image_base64.split(",")[1]

    img_bytes = base64.b64decode(image_base64)

    if preprocess and CV2_AVAILABLE:
        # Gelişmiş ön işleme
        processed_bytes = preprocess_image_cv2(img_bytes)
        if processed_bytes:
            img = Image.open(io.BytesIO(processed_bytes))
        else:
            img = Image.open(io.BytesIO(img_bytes))
            img = preprocess_image_pil(img)
    else:
        img = Image.open(io.BytesIO(img_bytes))
        if preprocess:
            img = preprocess_image_pil(img)

    # Birden fazla PSM modu ile dene
    results = []

    # PSM 6: Tek bir metin bloğu
    try:
        text6 = pytesseract.image_to_string(img, lang=lang, config='--psm 6')
        results.append(("psm6", text6.strip()))
    except Exception:
        pass

    # PSM 3: Tam otomatik sayfa segmentasyonu
    try:
        text3 = pytesseract.image_to_string(img, lang=lang, config='--psm 3')
        results.append(("psm3", text3.strip()))
    except Exception:
        pass

    # PSM 4: Farklı boyutlarda tek sütun metin
    try:
        text4 = pytesseract.image_to_string(img, lang=lang, config='--psm 4')
        results.append(("psm4", text4.strip()))
    except Exception:
        pass

    # En uzun sonucu tercih et (genellikle en çok veri)
    if results:
        best = max(results, key=lambda x: len(x[1]))
        return best[1]

    return ""


def extract_structured_data(raw_text: str) -> dict:
    """Ham OCR metninden yapılandırılmış veri çıkar (geliştirilmiş)"""
    data = {
        "first_name": None,
        "last_name": None,
        "id_number": None,
        "birth_date": None,
        "gender": None,
        "nationality": None,
        "document_type": None,
        "document_number": None,
        "expiry_date": None,
        "issue_date": None,
        "birth_place": None,
        "mother_name": None,
        "father_name": None,
        "raw_text": raw_text,
        "extraction_confidence": 0,
    }

    lines = raw_text.split('\n')
    text_upper = raw_text.upper()

    fields_found = 0

    # TC Kimlik No detection (11 digit number)
    tc_pattern = re.compile(r'\b[1-9]\d{10}\b')
    tc_matches = tc_pattern.findall(raw_text)
    if tc_matches:
        data["id_number"] = tc_matches[0]
        data["document_type"] = "tc_kimlik"
        fields_found += 2

    # Passport number detection (1-2 uppercase letters followed by 6-8 digits)
    passport_pattern = re.compile(r'\b[A-Z]{1,2}\d{6,8}\b')
    passport_matches = passport_pattern.findall(raw_text.upper())
    if passport_matches and not data["id_number"]:
        data["document_number"] = passport_matches[0]
        data["document_type"] = "passport"
        fields_found += 2

    # Date detection (DD.MM.YYYY or DD/MM/YYYY)
    date_pattern = re.compile(r'\b(\d{2})[./](\d{2})[./](\d{4})\b')
    date_matches = date_pattern.findall(raw_text)
    dates_found = []
    for day, month, year in date_matches:
        try:
            d, m, y = int(day), int(month), int(year)
            if 1 <= d <= 31 and 1 <= m <= 12 and 1900 <= y <= 2100:
                dates_found.append(f"{y:04d}-{m:02d}-{d:02d}")
        except ValueError:
            continue

    if dates_found:
        data["birth_date"] = dates_found[0]
        fields_found += 1
        if len(dates_found) > 1:
            data["expiry_date"] = dates_found[-1]
            fields_found += 1
        if len(dates_found) > 2:
            data["issue_date"] = dates_found[1]
            fields_found += 1

    # ISO date format (YYYY-MM-DD)
    if not data["birth_date"]:
        iso_date_pattern = re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b')
        iso_matches = iso_date_pattern.findall(raw_text)
        for year, month, day in iso_matches:
            try:
                y, m, d = int(year), int(month), int(day)
                if 1 <= d <= 31 and 1 <= m <= 12 and 1900 <= y <= 2100:
                    if not data["birth_date"]:
                        data["birth_date"] = f"{y:04d}-{m:02d}-{d:02d}"
                        fields_found += 1
            except ValueError:
                continue

    # Gender detection (geliştirilmiş)
    gender_male_patterns = ['ERKEK', '/M/', ' M ', 'MALE', 'MASCULIN', 'MANNLICH']
    gender_female_patterns = ['KADIN', '/F/', ' F ', 'FEMALE', 'FEMININ', 'WEIBLICH']

    for pattern in gender_male_patterns:
        if pattern in text_upper:
            data["gender"] = "M"
            fields_found += 1
            break

    if not data["gender"]:
        for pattern in gender_female_patterns:
            if pattern in text_upper:
                data["gender"] = "F"
                fields_found += 1
                break

    # Nationality detection (geliştirilmiş)
    nationality_patterns = {
        'TR': ['T.C.', 'TÜRKİYE', 'TURKEY', 'TURKISH', 'TURKIYE', 'TURK', 'TC'],
        'DE': ['DEUTSCHLAND', 'GERMAN', 'ALLEMAGNE', 'BUNDESREPUBLIK'],
        'GB': ['UNITED KINGDOM', 'BRITISH', 'GREAT BRITAIN'],
        'US': ['UNITED STATES', 'AMERICAN', 'USA'],
        'FR': ['FRANCE', 'FRENCH', 'FRANCAISE'],
        'IT': ['ITALIA', 'ITALIAN', 'ITALIANO'],
        'ES': ['ESPANA', 'SPANISH', 'ESPANOL'],
        'NL': ['NEDERLAND', 'DUTCH', 'NETHERLANDS'],
        'RU': ['RUSSIA', 'RUSSIAN', 'ROSSIYA'],
        'UA': ['UKRAINE', 'UKRAINIAN'],
    }

    for code, patterns in nationality_patterns.items():
        for pattern in patterns:
            if pattern in text_upper:
                data["nationality"] = code
                fields_found += 1
                break
        if data["nationality"]:
            break

    # İsim alanı çıkarma (geliştirilmiş)
    name_patterns = [
        # Türkçe
        (r'(?:ADI?|AD)\s*[:/]?\s*(.+)', 'first_name'),
        (r'(?:SOYADI?|SOYAD)\s*[:/]?\s*(.+)', 'last_name'),
        # İngilizce
        (r'(?:GIVEN\s*NAME|FIRST\s*NAME|NAME|PRENOM)\s*[:/]?\s*(.+)', 'first_name'),
        (r'(?:SURNAME|FAMILY\s*NAME|LAST\s*NAME|NOM)\s*[:/]?\s*(.+)', 'last_name'),
        # Doğum yeri
        (r'(?:DOĞUM\s*YERİ|DOGUM\s*YERI|BIRTH\s*PLACE|LIEU\s*DE\s*NAISSANCE)\s*[:/]?\s*(.+)', 'birth_place'),
        # Anne/baba adı
        (r'(?:ANNE\s*ADI?|MOTHER)\s*[:/]?\s*(.+)', 'mother_name'),
        (r'(?:BABA\s*ADI?|FATHER)\s*[:/]?\s*(.+)', 'father_name'),
    ]

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        for pattern, field in name_patterns:
            match = re.match(pattern, line_clean, re.IGNORECASE)
            if match and not data.get(field):
                value = match.group(1).strip()
                if len(value) > 1:  # En az 2 karakter
                    data[field] = value
                    fields_found += 1

    # MRZ parsing dene
    mrz_result = detect_and_parse_mrz(raw_text)
    if mrz_result:
        mrz_data = mrz_result
        # MRZ verilerini mevcut verilerle birleştir (MRZ öncelikli)
        mrz_fields = {
            "first_name": mrz_data.get("first_name"),
            "last_name": mrz_data.get("last_name"),
            "birth_date": mrz_data.get("birth_date"),
            "gender": mrz_data.get("gender"),
            "nationality": mrz_data.get("nationality"),
            "expiry_date": mrz_data.get("expiry_date"),
        }

        for field, value in mrz_fields.items():
            if value:
                if not data.get(field):
                    data[field] = value
                    fields_found += 1

        if mrz_data.get("passport_number"):
            data["document_number"] = data.get("document_number") or mrz_data["passport_number"]
            fields_found += 1
        if mrz_data.get("document_number"):
            data["document_number"] = data.get("document_number") or mrz_data["document_number"]
            fields_found += 1

        data["mrz_data"] = mrz_data
        fields_found += 2  # MRZ bulunması bonus

    # Güven puanı hesapla
    max_fields = 12
    data["extraction_confidence"] = min(round(fields_found / max_fields * 100), 100)

    return data


def calculate_ocr_confidence(structured_data: dict) -> dict:
    """OCR sonuçları için güven puanı hesapla"""
    confidence = structured_data.get("extraction_confidence", 0)

    has_name = bool(structured_data.get("first_name") or structured_data.get("last_name"))
    has_id = bool(structured_data.get("id_number") or structured_data.get("document_number"))
    has_date = bool(structured_data.get("birth_date"))
    has_mrz = bool(structured_data.get("mrz_data"))

    if has_mrz:
        confidence = min(confidence + 20, 100)

    if confidence >= 70:
        level = "medium"
        message = "Offline OCR sonuçları makul güvenilirlikte. Doğrulama önerilir."
    elif confidence >= 40:
        level = "low"
        message = "Offline OCR sonuçları düşük güvenilirlikte. Manuel kontrol gerekli."
    else:
        level = "very_low"
        message = "Offline OCR sonuçları çok düşük güvenilirlikte. Çoğu alan boş olabilir."

    return {
        "confidence_score": confidence,
        "confidence_level": level,
        "message": message,
        "has_name": has_name,
        "has_id": has_id,
        "has_date": has_date,
        "has_mrz": has_mrz,
    }


def ocr_scan_document(image_base64: str) -> dict:
    """Tam OCR tarama: geliştirilmiş ön işleme + metin çıkarım + yapılandırma"""
    if not is_tesseract_available():
        return {
            "success": False,
            "error": "Tesseract OCR sistemi kurulu değil",
            "documents": [],
        }

    try:
        raw_text = ocr_extract_text(image_base64, preprocess=True)

        if not raw_text or len(raw_text.strip()) < 5:
            # Ön işleme olmadan tekrar dene
            raw_text_no_preprocess = ocr_extract_text(image_base64, preprocess=False)
            if raw_text_no_preprocess and len(raw_text_no_preprocess.strip()) > len(raw_text.strip()):
                raw_text = raw_text_no_preprocess

        if not raw_text or len(raw_text.strip()) < 5:
            return {
                "success": False,
                "error": "Görüntüden yeterli metin çıkarılamadı. Daha net bir fotoğraf deneyin.",
                "raw_text": raw_text,
                "documents": [],
            }

        structured = extract_structured_data(raw_text)
        confidence = calculate_ocr_confidence(structured)

        # Determine validity
        has_name = bool(structured.get("first_name") or structured.get("last_name"))
        has_id = bool(structured.get("id_number") or structured.get("document_number"))
        is_valid = has_name or has_id

        document = {
            "is_valid": is_valid,
            "document_type": structured.get("document_type", "other"),
            "first_name": structured.get("first_name"),
            "last_name": structured.get("last_name"),
            "id_number": structured.get("id_number"),
            "birth_date": structured.get("birth_date"),
            "gender": structured.get("gender"),
            "nationality": structured.get("nationality"),
            "document_number": structured.get("document_number"),
            "expiry_date": structured.get("expiry_date"),
            "issue_date": structured.get("issue_date"),
            "birth_place": structured.get("birth_place"),
            "mother_name": structured.get("mother_name"),
            "father_name": structured.get("father_name"),
            "raw_extracted_text": raw_text,
            "warnings": [
                "Offline OCR (Tesseract) ile tarandı - sonuçları mutlaka kontrol edin",
            ],
            "mrz_data": structured.get("mrz_data"),
            "confidence": confidence,
        }

        return {
            "success": True,
            "source": "tesseract_ocr",
            "document_count": 1,
            "documents": [document],
            "raw_text": raw_text,
            "confidence": confidence,
            "confidence_note": f"Offline OCR güven puanı: %{confidence['confidence_score']}",
            "preprocessing_applied": True,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"OCR hatası: {str(e)}",
            "documents": [],
        }
