"""In-process identity document scanning for the PMS API.

The scanner intentionally does not persist document images or extracted raw
text.  It supports hosted vision providers and a local Tesseract fallback so
the PMS can use Quick-ID without running a second public service.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import io
import json
import os
import re
from datetime import datetime
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter

MAX_IMAGE_BYTES = int(os.environ.get("QUICKID_MAX_IMAGE_BYTES", str(8 * 1024 * 1024)))
SCAN_TIMEOUT_SECONDS = float(os.environ.get("QUICKID_SCAN_TIMEOUT_SECONDS", "60"))
MAX_CONCURRENT_SCANS = max(1, int(os.environ.get("QUICKID_MAX_CONCURRENT_SCANS", "2")))

_scan_slots = asyncio.Semaphore(MAX_CONCURRENT_SCANS)

ID_EXTRACTION_PROMPT = """You read identity documents for a hotel PMS.
Extract every visible identity document. Return JSON only, with this shape:
{"document_count":1,"documents":[{"is_valid":true,"document_type":"tc_kimlik|passport|drivers_license|old_nufus_cuzdani|other","first_name":null,"last_name":null,"id_number":null,"birth_date":null,"gender":"M|F|null","nationality":null,"expiry_date":null,"document_number":null,"birth_place":null,"issue_date":null,"mother_name":null,"father_name":null,"address":null,"warnings":[]}]}
Use YYYY-MM-DD dates. Use null for unreadable fields. Do not invent values."""


def _decode_image(value: str) -> tuple[bytes, str]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Görüntü verisi gerekli")
    encoded = value.strip()
    mime_type = "image/jpeg"
    if encoded.startswith("data:"):
        if "," not in encoded:
            raise ValueError("Geçersiz data URL")
        header, encoded = encoded.split(",", 1)
        mime_type = header[5:].split(";", 1)[0].lower()
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError("Yalnızca JPEG, PNG veya WebP görüntü desteklenir")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Geçersiz base64 görüntü") from exc
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"Görüntü en fazla {MAX_IMAGE_BYTES // (1024 * 1024)} MB olabilir")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
    except Exception as exc:
        raise ValueError("Geçersiz veya bozuk görüntü") from exc
    return data, mime_type


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("OCR sağlayıcısı geçerli JSON döndürmedi")
        result = json.loads(cleaned[start : end + 1])
    if not isinstance(result, dict):
        raise ValueError("OCR sağlayıcısı geçersiz yanıt döndürdü")
    documents = result.get("documents")
    if not isinstance(documents, list):
        documents = [result]
    normalized = [_normalize_document(doc) for doc in documents if isinstance(doc, dict)]
    return {"document_count": len(normalized), "documents": normalized}


def _normalize_document(document: dict[str, Any]) -> dict[str, Any]:
    text_fields = {
        "document_type": 32,
        "first_name": 120,
        "last_name": 120,
        "id_number": 32,
        "birth_date": 10,
        "gender": 1,
        "nationality": 8,
        "expiry_date": 10,
        "document_number": 32,
        "birth_place": 120,
        "issue_date": 10,
        "mother_name": 120,
        "father_name": 120,
        "address": 500,
    }
    result: dict[str, Any] = {"is_valid": bool(document.get("is_valid"))}
    for field, limit in text_fields.items():
        value = document.get(field)
        result[field] = str(value).strip()[:limit] if value not in (None, "") else None
    result["gender"] = result["gender"] if result["gender"] in {"M", "F"} else None
    result["document_type"] = result["document_type"] if result["document_type"] in {"tc_kimlik", "passport", "drivers_license", "old_nufus_cuzdani", "other"} else "other"
    warnings = document.get("warnings")
    result["warnings"] = [str(item)[:200] for item in warnings[:10]] if isinstance(warnings, list) else []
    return result


async def _openai_scan(image_bytes: bytes, mime_type: str, api_key: str, model: str) -> dict[str, Any]:
    from openai import AsyncOpenAI

    encoded = base64.b64encode(image_bytes).decode("ascii")
    client = AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": ID_EXTRACTION_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Read all visible identity documents and return JSON only."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
                ],
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=2500,
    )
    return _parse_json(response.choices[0].message.content or "")


async def _gemini_scan(image_bytes: bytes, mime_type: str, api_key: str) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = await client.aio.models.generate_content(
        model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ID_EXTRACTION_PROMPT,
        ],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return _parse_json(response.text or "")


def _tesseract_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _date_to_iso(value: str) -> str | None:
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _label_value(text: str, labels: list[str]) -> str | None:
    expression = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"(?:{expression})\s*[:/]?\s*([^\n]+)", text, flags=re.I)
    if not match:
        return None
    value = re.sub(r"\s{2,}.*$", "", match.group(1)).strip(" :-")
    return value[:120] or None


def _parse_tesseract_text(text: str) -> dict[str, Any]:
    upper = text.upper()
    tc_match = re.search(r"\b[1-9]\d{10}\b", text)
    passport_match = re.search(r"\b[A-Z]{1,2}\d{6,8}\b", upper)
    dates = [iso for raw in re.findall(r"\b(?:\d{2}[./-]\d{2}[./-]\d{4}|\d{4}-\d{2}-\d{2})\b", text) if (iso := _date_to_iso(raw))]
    first_name = _label_value(text, ["Adı", "Ad", "Given Names", "Given Name", "First Name", "Prénom"])
    last_name = _label_value(text, ["Soyadı", "Soyad", "Surname", "Family Name", "Nom"])
    document_type = "tc_kimlik" if tc_match else ("passport" if passport_match or "PASSPORT" in upper else "other")
    nationality = "TR" if any(token in upper for token in ("TÜRKİYE", "TURKEY", "TURKIYE")) else None
    gender = "F" if any(token in upper for token in ("KADIN", "FEMALE", " F ")) else None
    if gender is None and any(token in upper for token in ("ERKEK", "MALE", " M ")):
        gender = "M"
    is_valid = bool(first_name or last_name) and bool(tc_match or passport_match)
    return {
        "is_valid": is_valid,
        "document_type": document_type,
        "first_name": first_name,
        "last_name": last_name,
        "id_number": tc_match.group(0) if tc_match else None,
        "document_number": passport_match.group(0) if passport_match else None,
        "birth_date": dates[0] if dates else None,
        "expiry_date": dates[-1] if len(dates) > 1 else None,
        "gender": gender,
        "nationality": nationality,
        "birth_place": _label_value(text, ["Doğum Yeri", "Birth Place", "Place of Birth"]),
        "issue_date": dates[1] if len(dates) > 2 else None,
        "mother_name": _label_value(text, ["Anne Adı", "Mother Name"]),
        "father_name": _label_value(text, ["Baba Adı", "Father Name"]),
        "address": None,
        "warnings": ["Yerel OCR sonucu; alanları kimlik belgesiyle karşılaştırın"],
    }


async def _tesseract_scan(image_bytes: bytes) -> dict[str, Any]:
    import pytesseract

    def run() -> dict[str, Any]:
        with Image.open(io.BytesIO(image_bytes)) as source:
            image = source.convert("L")
            image = ImageEnhance.Contrast(image).enhance(1.6)
            image = image.filter(ImageFilter.SHARPEN)
            try:
                text = pytesseract.image_to_string(image, lang="tur+eng", config="--psm 6")
            except pytesseract.TesseractError:
                text = pytesseract.image_to_string(image, lang="eng", config="--psm 6")
        if len(text.strip()) < 5:
            raise ValueError("Görüntüde okunabilir kimlik metni bulunamadı")
        document = _parse_tesseract_text(text)
        if not document["is_valid"]:
            raise ValueError("Kimlik alanları güvenilir biçimde okunamadı; daha net fotoğraf çekin")
        return {"document_count": 1, "documents": [document]}

    return await asyncio.to_thread(run)


def provider_catalog(api_keys: dict[str, str] | None = None) -> list[dict[str, Any]]:
    keys = api_keys or {}
    openai_available = bool(keys.get("openai") or os.environ.get("OPENAI_API_KEY"))
    gemini_available = bool(keys.get("gemini") or os.environ.get("GEMINI_API_KEY"))
    return [
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "available": openai_available, "cost": "provider"},
        {"id": "gpt-4o", "name": "GPT-4o", "available": openai_available, "cost": "provider"},
        {"id": "gemini-flash", "name": "Gemini Flash", "available": gemini_available, "cost": "provider"},
        {"id": "tesseract", "name": "Yerel Tesseract OCR", "available": _tesseract_available(), "cost": 0},
    ]


async def scan_document(
    image_base64: str,
    *,
    provider: str | None,
    smart_mode: bool,
    api_keys: dict[str, str] | None = None,
) -> dict[str, Any]:
    image_bytes, mime_type = _decode_image(image_base64)
    keys = api_keys or {}
    openai_key = keys.get("openai") or os.environ.get("OPENAI_API_KEY", "")
    gemini_key = keys.get("gemini") or os.environ.get("GEMINI_API_KEY", "")
    available = {item["id"] for item in provider_catalog(keys) if item["available"]}

    if provider:
        chain = [provider]
        if smart_mode:
            chain.extend(item for item in ("gpt-4o-mini", "gemini-flash", "gpt-4o", "tesseract") if item != provider)
    else:
        chain = ["gpt-4o-mini", "gemini-flash", "gpt-4o", "tesseract"]
    chain = [item for item in chain if item in available]
    if not chain:
        raise RuntimeError("Kullanılabilir OCR sağlayıcısı yok; API anahtarı girin veya yerel OCR'ı etkinleştirin")

    errors: list[str] = []
    async with _scan_slots:
        async with asyncio.timeout(SCAN_TIMEOUT_SECONDS):
            for candidate in chain:
                try:
                    if candidate == "gemini-flash":
                        extracted = await _gemini_scan(image_bytes, mime_type, gemini_key)
                    elif candidate == "tesseract":
                        extracted = await _tesseract_scan(image_bytes)
                    else:
                        extracted = await _openai_scan(image_bytes, mime_type, openai_key, candidate)
                    documents = extracted.get("documents", [])
                    valid_fields = sum(bool(doc.get(field)) for doc in documents for field in ("first_name", "last_name", "id_number", "document_number", "birth_date"))
                    confidence_score = min(98, 45 + valid_fields * 8) if documents else 0
                    return {
                        "success": True,
                        "mode": "embedded",
                        "extracted_data": extracted,
                        "documents": documents,
                        "document_count": len(documents),
                        "scan": {
                            "confidence_score": confidence_score,
                            "confidence_level": "high" if confidence_score >= 80 else "medium" if confidence_score >= 60 else "low",
                            "provider": candidate,
                            "provider_info": {"name": candidate, "fallback_used": candidate != chain[0]},
                            "review_status": "needs_review",
                        },
                        "provider": candidate,
                        "provider_info": {"name": candidate, "fallback_used": candidate != chain[0]},
                    }
                except Exception as exc:
                    errors.append(f"{candidate}: {exc}")
    raise RuntimeError("OCR tamamlanamadı: " + "; ".join(errors)[:500])


def health(api_keys: dict[str, str] | None = None) -> dict[str, Any]:
    providers = provider_catalog(api_keys)
    return {
        "available": any(item["available"] for item in providers),
        "mode": "embedded",
        "providers": providers,
        "image_retention": False,
        "max_concurrent_scans": MAX_CONCURRENT_SCANS,
    }
