"""
Geliştirilmiş MRZ (Machine Readable Zone) Parser
- TD1 (ID Card - 3x30), TD2 (Visa/ID - 2x36), TD3 (Passport - 2x44)
- OCR hata düzeltme (O/0, I/1, B/8 gibi yaygın karışıklıklar)
- Fuzzy MRZ satır tespiti
- Check digit doğrulama
- ICAO 9303 uyumluluk kontrolü
"""
import re
from datetime import datetime
from typing import Optional


# MRZ character to number mapping
MRZ_CHAR_MAP = {
    '<': 0, '0': 0, '1': 1, '2': 2, '3': 3, '4': 4,
    '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
    'A': 10, 'B': 11, 'C': 12, 'D': 13, 'E': 14, 'F': 15,
    'G': 16, 'H': 17, 'I': 18, 'J': 19, 'K': 20, 'L': 21,
    'M': 22, 'N': 23, 'O': 24, 'P': 25, 'Q': 26, 'R': 27,
    'S': 28, 'T': 29, 'U': 30, 'V': 31, 'W': 32, 'X': 33,
    'Y': 34, 'Z': 35,
}

WEIGHTS = [7, 3, 1]

# Yaygın OCR hata düzeltme tablosu
OCR_CORRECTIONS = {
    # Sayı/harf karışıklıkları
    'O': '0',  # O harfi -> 0 rakamı (sayısal alanlarda)
    'o': '0',
    'I': '1',  # I harfi -> 1 rakamı (sayısal alanlarda)
    'l': '1',  # küçük L -> 1
    'B': '8',  # B harfi -> 8 (sayısal alanlarda)
    'S': '5',  # S -> 5 (sayısal alanlarda)
    'Z': '2',  # Z -> 2 (sayısal alanlarda)
    'G': '6',  # G -> 6 (sayısal alanlarda)
    'D': '0',  # D -> 0 (sayısal alanlarda)
    'Q': '0',  # Q -> 0 (sayısal alanlarda)
    # Harf/sayı karışıklıkları (harfsel alanlarda)
    '0': 'O',  # 0 rakamı -> O harfi (harfsel alanlarda)
    '1': 'I',  # 1 -> I (harfsel alanlarda)
    '8': 'B',  # 8 -> B (harfsel alanlarda)
    '5': 'S',  # 5 -> S (harfsel alanlarda)
    '2': 'Z',  # 2 -> Z (harfsel alanlarda)
}

# ICAO ülke kodları (yaygın olanlar)
ICAO_COUNTRY_CODES = {
    'TUR': 'Türkiye', 'DEU': 'Almanya', 'GBR': 'İngiltere', 'USA': 'ABD',
    'FRA': 'Fransa', 'ITA': 'İtalya', 'ESP': 'İspanya', 'NLD': 'Hollanda',
    'BEL': 'Belçika', 'AUT': 'Avusturya', 'CHE': 'İsviçre', 'SWE': 'İsveç',
    'NOR': 'Norveç', 'DNK': 'Danimarka', 'FIN': 'Finlandiya', 'GRC': 'Yunanistan',
    'PRT': 'Portekiz', 'POL': 'Polonya', 'CZE': 'Çekya', 'HUN': 'Macaristan',
    'ROU': 'Romanya', 'BGR': 'Bulgaristan', 'HRV': 'Hırvatistan', 'SVK': 'Slovakya',
    'SVN': 'Slovenya', 'LTU': 'Litvanya', 'LVA': 'Letonya', 'EST': 'Estonya',
    'IRL': 'İrlanda', 'ISR': 'İsrail', 'JPN': 'Japonya', 'KOR': 'G.Kore',
    'CHN': 'Çin', 'IND': 'Hindistan', 'BRA': 'Brezilya', 'CAN': 'Kanada',
    'AUS': 'Avustralya', 'RUS': 'Rusya', 'UKR': 'Ukrayna', 'SAU': 'S.Arabistan',
    'ARE': 'BAE', 'EGY': 'Mısır', 'IRN': 'İran', 'IRQ': 'Irak', 'SYR': 'Suriye',
    'GEO': 'Gürcistan', 'AZE': 'Azerbaycan', 'KAZ': 'Kazakistan',
    'UZB': 'Özbekistan', 'TKM': 'Türkmenistan',
    'D': 'Almanya',  # Bazı eski belgelerde tek karakter kullanılır
}


def compute_check_digit(data: str) -> int:
    """MRZ check digit hesapla"""
    total = 0
    for i, char in enumerate(data):
        val = MRZ_CHAR_MAP.get(char.upper(), 0)
        total += val * WEIGHTS[i % 3]
    return total % 10


def validate_check_digit(data: str, check_digit: str) -> bool:
    """Check digit doğrula"""
    try:
        expected = compute_check_digit(data)
        return expected == int(check_digit)
    except (ValueError, IndexError):
        return False


def parse_mrz_date(date_str: str) -> Optional[str]:
    """MRZ tarih formatını (YYMMDD) ISO formatına çevir"""
    try:
        if len(date_str) != 6:
            return None

        # OCR hata düzeltme (tarih alanı sadece sayı olmalı)
        corrected = correct_numeric_field(date_str)

        year = int(corrected[:2])
        month = int(corrected[2:4])
        day = int(corrected[4:6])

        # Geçerlilik kontrolü
        if month < 1 or month > 12:
            return None
        if day < 1 or day > 31:
            return None

        # Y2K handling
        current_year = datetime.now().year % 100
        if year <= current_year + 10:
            year += 2000
        else:
            year += 1900

        return f"{year:04d}-{month:02d}-{day:02d}"
    except (ValueError, IndexError):
        return None


def clean_mrz_field(field: str) -> str:
    """MRZ alanından '<' karakterlerini temizle"""
    return field.replace('<', ' ').strip()


def correct_numeric_field(field: str) -> str:
    """Sayısal alanlardaki OCR hatalarını düzelt"""
    corrected = ""
    for char in field:
        if char.isdigit():
            corrected += char
        elif char in ('<', ' '):
            corrected += char
        elif char.upper() in OCR_CORRECTIONS:
            replacement = OCR_CORRECTIONS[char.upper()]
            if replacement.isdigit():
                corrected += replacement
            else:
                corrected += char
        else:
            corrected += char
    return corrected


def correct_alpha_field(field: str) -> str:
    """Harfsel alanlardaki OCR hatalarını düzelt"""
    corrected = ""
    for char in field:
        if char.isalpha() or char in ('<', ' '):
            corrected += char
        elif char in OCR_CORRECTIONS:
            replacement = OCR_CORRECTIONS[char]
            if replacement.isalpha():
                corrected += replacement
            else:
                corrected += char
        else:
            corrected += char
    return corrected


def correct_mrz_line(line: str) -> str:
    """MRZ satırındaki yaygın OCR hatalarını düzelt"""
    # Genel düzeltmeler
    corrected = line.upper().strip()
    corrected = corrected.replace(' ', '')

    # Yaygın OCR hataları
    corrected = corrected.replace('«', '<')
    corrected = corrected.replace('‹', '<')
    corrected = corrected.replace('>', '<')
    corrected = corrected.replace('{', '<')
    corrected = corrected.replace('}', '<')
    corrected = corrected.replace('[', '<')
    corrected = corrected.replace(']', '<')
    corrected = corrected.replace('(', '<')
    corrected = corrected.replace(')', '<')
    corrected = corrected.replace('|', 'I')
    corrected = corrected.replace('\\', '<')
    corrected = corrected.replace('/', '<')

    return corrected


def extract_names(name_field: str) -> dict:
    """MRZ isim alanından ad ve soyad çıkar"""
    parts = name_field.split('<<')
    last_name = clean_mrz_field(parts[0]) if len(parts) > 0 else ""
    first_name = clean_mrz_field(parts[1]) if len(parts) > 1 else ""
    first_name = first_name.replace('<', ' ').strip()

    # OCR düzeltme - isimlerde sayı olmamalı
    first_name = correct_alpha_field(first_name)
    last_name = correct_alpha_field(last_name)

    return {"first_name": first_name, "last_name": last_name}


def parse_td3_passport(lines: list) -> Optional[dict]:
    """TD3 format pasaport MRZ parse (2 satır x 44 karakter)"""
    if len(lines) != 2:
        return None

    line1 = correct_mrz_line(lines[0])
    line2 = correct_mrz_line(lines[1])

    if len(line1) != 44 or len(line2) != 44:
        return None

    if line1[0] != 'P':
        return None

    # Line 1
    doc_type = line1[0:2].replace('<', '')
    issuing_country = line1[2:5].replace('<', '')
    names_field = line1[5:44]
    names = extract_names(names_field)

    # Line 2
    passport_number = line2[0:9].replace('<', '')
    passport_check = line2[9]
    nationality = line2[10:13].replace('<', '')
    birth_date_raw = line2[13:19]
    birth_check = line2[19]
    gender = line2[20]
    expiry_date_raw = line2[21:27]
    expiry_check = line2[27]
    personal_number = line2[28:42].replace('<', '')
    personal_check = line2[42]
    final_check = line2[43]

    # Check digit düzeltme - sayısal alan
    birth_date_corrected = correct_numeric_field(birth_date_raw)
    expiry_date_corrected = correct_numeric_field(expiry_date_raw)

    # Validate check digits
    checks = {
        "passport_number": validate_check_digit(line2[0:9], passport_check),
        "birth_date": validate_check_digit(birth_date_corrected, birth_check),
        "expiry_date": validate_check_digit(expiry_date_corrected, expiry_check),
    }

    # Parse dates
    birth_date = parse_mrz_date(birth_date_corrected)
    expiry_date = parse_mrz_date(expiry_date_corrected)

    # Gender mapping
    gender_map = {'M': 'M', 'F': 'F', '<': None}

    # ICAO uyumluluk
    icao_compliance = check_icao_compliance({
        "issuing_country": issuing_country,
        "nationality": nationality,
        "checks": checks,
        "mrz_type": "TD3",
        "line_lengths": [len(line1), len(line2)],
    })

    return {
        "mrz_type": "TD3",
        "document_type": "passport",
        "doc_subtype": doc_type,
        "issuing_country": issuing_country,
        "issuing_country_name": ICAO_COUNTRY_CODES.get(issuing_country, issuing_country),
        "first_name": names["first_name"],
        "last_name": names["last_name"],
        "passport_number": passport_number,
        "nationality": nationality,
        "nationality_name": ICAO_COUNTRY_CODES.get(nationality, nationality),
        "birth_date": birth_date,
        "gender": gender_map.get(gender, gender),
        "expiry_date": expiry_date,
        "personal_number": personal_number if personal_number else None,
        "check_digits_valid": checks,
        "all_checks_passed": all(checks.values()),
        "icao_compliance": icao_compliance,
        "ocr_corrections_applied": birth_date_raw != birth_date_corrected or expiry_date_raw != expiry_date_corrected,
        "raw_mrz": lines,
    }


def parse_td2_document(lines: list) -> Optional[dict]:
    """TD2 format belge MRZ parse (2 satır x 36 karakter) - Vize, kimlik kartı"""
    if len(lines) != 2:
        return None

    line1 = correct_mrz_line(lines[0])
    line2 = correct_mrz_line(lines[1])

    if len(line1) != 36 or len(line2) != 36:
        return None

    # Line 1
    doc_type = line1[0:2].replace('<', '')
    issuing_country = line1[2:5].replace('<', '')
    names_field = line1[5:36]
    names = extract_names(names_field)

    # Line 2
    doc_number = line2[0:9].replace('<', '')
    doc_check = line2[9]
    nationality = line2[10:13].replace('<', '')
    birth_date_raw = line2[13:19]
    birth_check = line2[19]
    gender = line2[20]
    expiry_date_raw = line2[21:27]
    expiry_check = line2[27]
    optional_data = line2[28:35].replace('<', '')
    final_check = line2[35]

    # OCR düzeltme
    birth_date_corrected = correct_numeric_field(birth_date_raw)
    expiry_date_corrected = correct_numeric_field(expiry_date_raw)

    checks = {
        "document_number": validate_check_digit(line2[0:9], doc_check),
        "birth_date": validate_check_digit(birth_date_corrected, birth_check),
        "expiry_date": validate_check_digit(expiry_date_corrected, expiry_check),
    }

    birth_date = parse_mrz_date(birth_date_corrected)
    expiry_date = parse_mrz_date(expiry_date_corrected)
    gender_map = {'M': 'M', 'F': 'F', '<': None}

    # Belge tipi belirleme
    if doc_type.startswith('V'):
        document_type = "visa"
    elif doc_type.startswith('I'):
        document_type = "id_card"
    elif doc_type.startswith('A') or doc_type.startswith('C'):
        document_type = "travel_document"
    else:
        document_type = "other"

    icao_compliance = check_icao_compliance({
        "issuing_country": issuing_country,
        "nationality": nationality,
        "checks": checks,
        "mrz_type": "TD2",
        "line_lengths": [len(line1), len(line2)],
    })

    return {
        "mrz_type": "TD2",
        "document_type": document_type,
        "doc_subtype": doc_type,
        "issuing_country": issuing_country,
        "issuing_country_name": ICAO_COUNTRY_CODES.get(issuing_country, issuing_country),
        "first_name": names["first_name"],
        "last_name": names["last_name"],
        "document_number": doc_number,
        "nationality": nationality,
        "nationality_name": ICAO_COUNTRY_CODES.get(nationality, nationality),
        "birth_date": birth_date,
        "gender": gender_map.get(gender, gender),
        "expiry_date": expiry_date,
        "optional_data": optional_data if optional_data else None,
        "check_digits_valid": checks,
        "all_checks_passed": all(checks.values()),
        "icao_compliance": icao_compliance,
        "ocr_corrections_applied": birth_date_raw != birth_date_corrected or expiry_date_raw != expiry_date_corrected,
        "raw_mrz": lines,
    }


def parse_td1_id_card(lines: list) -> Optional[dict]:
    """TD1 format kimlik kartı MRZ parse (3 satır x 30 karakter)"""
    if len(lines) != 3:
        return None

    line1 = correct_mrz_line(lines[0])
    line2 = correct_mrz_line(lines[1])
    line3 = correct_mrz_line(lines[2])

    if len(line1) != 30 or len(line2) != 30 or len(line3) != 30:
        return None

    # Line 1
    doc_type = line1[0:2].replace('<', '')
    issuing_country = line1[2:5].replace('<', '')
    doc_number = line1[5:14].replace('<', '')
    doc_check = line1[14]
    optional1 = line1[15:30].replace('<', '')

    # Line 2
    birth_date_raw = line2[0:6]
    birth_check = line2[6]
    gender = line2[7]
    expiry_date_raw = line2[8:14]
    expiry_check = line2[14]
    nationality = line2[15:18].replace('<', '')
    optional2 = line2[18:29].replace('<', '')
    final_check = line2[29]

    # Line 3 - Names
    names = extract_names(line3)

    # OCR düzeltme
    birth_date_corrected = correct_numeric_field(birth_date_raw)
    expiry_date_corrected = correct_numeric_field(expiry_date_raw)

    checks = {
        "document_number": validate_check_digit(line1[5:14], doc_check),
        "birth_date": validate_check_digit(birth_date_corrected, birth_check),
        "expiry_date": validate_check_digit(expiry_date_corrected, expiry_check),
    }

    birth_date = parse_mrz_date(birth_date_corrected)
    expiry_date = parse_mrz_date(expiry_date_corrected)
    gender_map = {'M': 'M', 'F': 'F', '<': None}

    icao_compliance = check_icao_compliance({
        "issuing_country": issuing_country,
        "nationality": nationality,
        "checks": checks,
        "mrz_type": "TD1",
        "line_lengths": [len(line1), len(line2), len(line3)],
    })

    return {
        "mrz_type": "TD1",
        "document_type": "id_card",
        "doc_subtype": doc_type,
        "issuing_country": issuing_country,
        "issuing_country_name": ICAO_COUNTRY_CODES.get(issuing_country, issuing_country),
        "first_name": names["first_name"],
        "last_name": names["last_name"],
        "document_number": doc_number,
        "nationality": nationality,
        "nationality_name": ICAO_COUNTRY_CODES.get(nationality, nationality),
        "birth_date": birth_date,
        "gender": gender_map.get(gender, gender),
        "expiry_date": expiry_date,
        "personal_number": optional1 if optional1 else None,
        "check_digits_valid": checks,
        "all_checks_passed": all(checks.values()),
        "icao_compliance": icao_compliance,
        "ocr_corrections_applied": birth_date_raw != birth_date_corrected or expiry_date_raw != expiry_date_corrected,
        "raw_mrz": lines,
    }


def check_icao_compliance(data: dict) -> dict:
    """ICAO 9303 uyumluluk kontrolü"""
    issues = []
    is_compliant = True

    # Ülke kodu kontrolü
    if data.get("issuing_country") and len(data["issuing_country"]) != 3:
        # Bazı eski belgeler 1-2 karakter kullanabilir
        if data["issuing_country"] not in ICAO_COUNTRY_CODES:
            issues.append(f"Veren ülke kodu geçersiz: {data['issuing_country']}")
            is_compliant = False

    if data.get("nationality") and len(data["nationality"]) != 3:
        if data["nationality"] not in ICAO_COUNTRY_CODES:
            issues.append(f"Uyruk kodu geçersiz: {data['nationality']}")
            is_compliant = False

    # Check digit kontrolü
    checks = data.get("checks", {})
    failed_checks = [k for k, v in checks.items() if not v]
    if failed_checks:
        issues.append(f"Check digit doğrulama başarısız: {', '.join(failed_checks)}")
        is_compliant = False

    # Satır uzunluğu kontrolü
    mrz_type = data.get("mrz_type", "")
    expected_lengths = {"TD1": [30, 30, 30], "TD2": [36, 36], "TD3": [44, 44]}
    if mrz_type in expected_lengths:
        actual = data.get("line_lengths", [])
        expected = expected_lengths[mrz_type]
        if actual != expected:
            issues.append(f"Satır uzunlukları uyumsuz: beklenen {expected}, bulunan {actual}")
            is_compliant = False

    return {
        "is_compliant": is_compliant,
        "standard": "ICAO 9303",
        "issues": issues,
        "mrz_type": mrz_type,
    }


def fuzzy_mrz_line_match(line: str) -> Optional[str]:
    """Bulanık MRZ satır eşleştirme - OCR hatalarını tolere et"""
    cleaned = correct_mrz_line(line)

    # MRZ karakterleri: A-Z, 0-9, <
    valid_chars = sum(1 for c in cleaned if c.isalnum() or c == '<')
    total_chars = len(cleaned)

    if total_chars == 0:
        return None

    validity_ratio = valid_chars / total_chars

    # %85'ten fazla geçerli karakter varsa MRZ satırı sayılabilir
    if validity_ratio >= 0.85 and total_chars >= 28:
        return cleaned

    return None


def detect_and_parse_mrz(text: str) -> Optional[dict]:
    """Metin içinden MRZ bölgesini tespit et ve parse et (geliştirilmiş)"""
    if not text:
        return None

    # Clean and split lines
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]

    # Strict matching - tam MRZ satırları
    mrz_pattern = re.compile(r'^[A-Z0-9<]{28,44}$')
    strict_mrz_lines = []
    for line in lines:
        cleaned = line.replace(' ', '').upper()
        if mrz_pattern.match(cleaned):
            strict_mrz_lines.append(cleaned)

    # Fuzzy matching - OCR hatalarını tolere et
    fuzzy_mrz_lines = []
    for line in lines:
        fuzzy_result = fuzzy_mrz_line_match(line)
        if fuzzy_result:
            fuzzy_mrz_lines.append(fuzzy_result)

    # Önce strict, sonra fuzzy dene
    for mrz_lines in [strict_mrz_lines, fuzzy_mrz_lines]:
        if not mrz_lines:
            continue

        # Try TD3 (passport - 2 lines x 44 chars)
        if len(mrz_lines) >= 2:
            td3_lines = [ln for ln in mrz_lines if len(ln) == 44]
            if len(td3_lines) >= 2:
                result = parse_td3_passport(td3_lines[:2])
                if result:
                    return result

        # Try TD2 (visa/ID - 2 lines x 36 chars)
        if len(mrz_lines) >= 2:
            td2_lines = [ln for ln in mrz_lines if len(ln) == 36]
            if len(td2_lines) >= 2:
                result = parse_td2_document(td2_lines[:2])
                if result:
                    return result

        # Try TD1 (ID card - 3 lines x 30 chars)
        if len(mrz_lines) >= 3:
            td1_lines = [ln for ln in mrz_lines if len(ln) == 30]
            if len(td1_lines) >= 3:
                result = parse_td1_id_card(td1_lines[:3])
                if result:
                    return result

    # Son çare: yakın uzunlukları da dene (OCR bazen karakter ekler/siler)
    for mrz_lines in [strict_mrz_lines, fuzzy_mrz_lines]:
        if not mrz_lines:
            continue

        # TD3 yakın eşleşme (42-46 karakter)
        td3_close = [ln for ln in mrz_lines if 42 <= len(ln) <= 46]
        if len(td3_close) >= 2:
            # Tam 44 karaktere kes/doldur
            adjusted = []
            for ln in td3_close[:2]:
                if len(ln) > 44:
                    ln = ln[:44]
                elif len(ln) < 44:
                    ln = ln + '<' * (44 - len(ln))
                adjusted.append(ln)
            result = parse_td3_passport(adjusted)
            if result:
                result["fuzzy_matched"] = True
                return result

        # TD2 yakın eşleşme (34-38 karakter)
        td2_close = [ln for ln in mrz_lines if 34 <= len(ln) <= 38]
        if len(td2_close) >= 2:
            adjusted = []
            for ln in td2_close[:2]:
                if len(ln) > 36:
                    ln = ln[:36]
                elif len(ln) < 36:
                    ln = ln + '<' * (36 - len(ln))
                adjusted.append(ln)
            result = parse_td2_document(adjusted)
            if result:
                result["fuzzy_matched"] = True
                return result

    return None


def parse_mrz_from_text(raw_text: str) -> dict:
    """Ham metinden MRZ parse et ve sonuç döndür"""
    result = detect_and_parse_mrz(raw_text)

    if result:
        mrz_type = result.get('mrz_type', 'unknown')
        fuzzy = result.get('fuzzy_matched', False)
        ocr_corrected = result.get('ocr_corrections_applied', False)

        notes = []
        if fuzzy:
            notes.append("fuzzy eşleşme ile bulundu")
        if ocr_corrected:
            notes.append("OCR hata düzeltmesi uygulandı")

        icao = result.get('icao_compliance', {})

        message = f"MRZ başarıyla okundu ({mrz_type} format)"
        if notes:
            message += f" [{', '.join(notes)}]"

        return {
            "mrz_detected": True,
            "mrz_data": result,
            "mrz_type": mrz_type,
            "message": message,
            "icao_compliant": icao.get("is_compliant", False),
            "ocr_corrected": ocr_corrected,
            "fuzzy_matched": fuzzy,
        }

    return {
        "mrz_detected": False,
        "mrz_data": None,
        "mrz_type": None,
        "message": "MRZ bölgesi tespit edilemedi",
        "icao_compliant": False,
        "ocr_corrected": False,
        "fuzzy_matched": False,
    }
