"""
Multi-Provider OCR Yönetimi
- GPT-4o (yüksek kalite), GPT-4o-mini (hızlı/ucuz), Gemini Flash (Google alternatifi)
- Akıllı yönlendirme (görüntü kalitesine göre otomatik provider seçimi)
- Provider sağlık kontrolü ve fallback zinciri
- Maliyet takibi
"""
import os
import json
import uuid
import time
import asyncio
from typing import Optional
from datetime import datetime, timezone

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Provider tanımları
PROVIDERS = {
    "gpt-4o": {
        "name": "GPT-4o",
        "provider_type": "openai",
        "model": "gpt-4o",
        "description": "En yüksek doğruluk, yavaş, pahalı",
        "speed": "slow",
        "quality": "high",
        "cost_per_scan": 0.015,
        "max_retries": 2,
        "timeout": 30,
        "supports_vision": True,
        "priority": 1,
    },
    "gpt-4o-mini": {
        "name": "GPT-4o Mini",
        "provider_type": "openai",
        "model": "gpt-4o-mini",
        "description": "İyi doğruluk, hızlı, ucuz",
        "speed": "fast",
        "quality": "medium",
        "cost_per_scan": 0.003,
        "max_retries": 2,
        "timeout": 15,
        "supports_vision": True,
        "priority": 2,
    },
    "gemini-flash": {
        "name": "Gemini 2.0 Flash",
        "provider_type": "google",
        "model": "gemini-2.0-flash",
        "description": "Google alternatifi, hızlı, uygun maliyet",
        "speed": "fast",
        "quality": "medium-high",
        "cost_per_scan": 0.004,
        "max_retries": 2,
        "timeout": 20,
        "supports_vision": True,
        "priority": 3,
    },
    "tesseract": {
        "name": "Tesseract OCR",
        "provider_type": "local",
        "model": "tesseract",
        "description": "Offline, ücretsiz, düşük doğruluk",
        "speed": "fast",
        "quality": "low",
        "cost_per_scan": 0.0,
        "max_retries": 1,
        "timeout": 10,
        "supports_vision": False,
        "priority": 99,
    },
}

# Smart routing kuralları
SMART_ROUTING_RULES = {
    "high_quality_image": {
        "description": "Yüksek kaliteli görüntü - ucuz provider yeterli",
        "min_quality_score": 80,
        "provider_chain": ["gpt-4o-mini", "gemini-flash", "gpt-4o", "tesseract"],
    },
    "medium_quality_image": {
        "description": "Orta kaliteli görüntü - orta seviye provider",
        "min_quality_score": 50,
        "provider_chain": ["gpt-4o-mini", "gpt-4o", "gemini-flash", "tesseract"],
    },
    "low_quality_image": {
        "description": "Düşük kaliteli görüntü - en iyi provider gerekli",
        "min_quality_score": 0,
        "provider_chain": ["gpt-4o", "gemini-flash", "gpt-4o-mini", "tesseract"],
    },
}

# Provider sağlık durumu (runtime tracking)
_provider_health = {}


def get_provider_info(provider_id: str) -> Optional[dict]:
    """Provider bilgisini al"""
    return PROVIDERS.get(provider_id)


def list_providers() -> list:
    """Tüm provider'ları listele"""
    providers = []
    for pid, pinfo in PROVIDERS.items():
        health = _provider_health.get(pid, {"status": "unknown", "last_check": None})
        providers.append({
            "id": pid,
            **pinfo,
            "health_status": health.get("status", "unknown"),
            "last_check": health.get("last_check"),
            "success_rate": health.get("success_rate", None),
        })
    return providers


def get_smart_provider_chain(quality_score: int) -> list:
    """Görüntü kalitesine göre akıllı provider sırası belirle"""
    if quality_score >= 80:
        rule = SMART_ROUTING_RULES["high_quality_image"]
    elif quality_score >= 50:
        rule = SMART_ROUTING_RULES["medium_quality_image"]
    else:
        rule = SMART_ROUTING_RULES["low_quality_image"]

    # Filter out unhealthy providers
    chain = []
    for pid in rule["provider_chain"]:
        health = _provider_health.get(pid, {})
        if health.get("status") != "down":
            chain.append(pid)

    return chain if chain else rule["provider_chain"]  # Fallback to all if none available


def update_provider_health(provider_id: str, success: bool, response_time: float = 0):
    """Provider sağlık durumunu güncelle"""
    if provider_id not in _provider_health:
        _provider_health[provider_id] = {
            "status": "healthy",
            "total_calls": 0,
            "success_count": 0,
            "fail_count": 0,
            "avg_response_time": 0,
            "last_check": None,
            "consecutive_fails": 0,
        }

    health = _provider_health[provider_id]
    health["total_calls"] += 1
    health["last_check"] = datetime.now(timezone.utc).isoformat()

    if success:
        health["success_count"] += 1
        health["consecutive_fails"] = 0
        health["status"] = "healthy"
        # Update average response time
        total = health["total_calls"]
        health["avg_response_time"] = (
            (health["avg_response_time"] * (total - 1) + response_time) / total
        )
    else:
        health["fail_count"] += 1
        health["consecutive_fails"] += 1
        if health["consecutive_fails"] >= 3:
            health["status"] = "down"
        elif health["consecutive_fails"] >= 1:
            health["status"] = "degraded"

    health["success_rate"] = (
        round(health["success_count"] / health["total_calls"] * 100, 1)
        if health["total_calls"] > 0 else 0
    )


ID_EXTRACTION_PROMPT = """You are an expert ID document reader for a hotel check-in system. You analyze images of identity documents (ID cards, passports, driver's licenses) and extract structured information.

CRITICAL: The image may contain ONE or MULTIPLE identity documents. You MUST detect and extract data from ALL visible documents separately.

IMPORTANT RULES:
1. Count ALL visible identity documents in the image
2. Extract ALL visible text fields from EACH document separately
3. Return ONLY valid JSON - no markdown, no extra text, no code blocks
4. If a field is not visible or unclear, set it to null
5. Normalize dates to YYYY-MM-DD format
6. For gender, use "M" (Male/Erkek) or "F" (Female/Kadin)
7. Detect the document type automatically for each document
8. If the image is blurry, cropped, or not an ID document, set "is_valid" to false
9. For Turkish ID cards (TC Kimlik), extract TC Kimlik No
10. For passports, extract passport number and MRZ data if visible
11. For driver's licenses, extract license number

ALWAYS return a JSON object with a "documents" array. Even if there is only 1 document, wrap it in the array.

Return this exact JSON structure (no markdown, no code fences):
{
    "document_count": 1 or 2 or more,
    "documents": [
        {
            "is_valid": true or false,
            "document_type": "tc_kimlik" | "passport" | "drivers_license" | "old_nufus_cuzdani" | "other",
            "first_name": "string or null",
            "last_name": "string or null",
            "id_number": "string or null",
            "birth_date": "YYYY-MM-DD or null",
            "gender": "M" | "F" | null,
            "nationality": "string or null",
            "expiry_date": "YYYY-MM-DD or null",
            "document_number": "string or null",
            "birth_place": "string or null",
            "issue_date": "YYYY-MM-DD or null",
            "mother_name": "string or null",
            "father_name": "string or null",
            "address": "string or null",
            "warnings": ["list of any issues or uncertain fields"],
            "raw_extracted_text": "all visible text from this specific document"
        }
    ]
}"""


async def extract_with_provider(provider_id: str, image_base64: str) -> dict:
    """Belirtilen provider ile kimlik tarama yap"""
    provider = PROVIDERS.get(provider_id)
    if not provider:
        raise ValueError(f"Bilinmeyen provider: {provider_id}")

    if provider_id == "tesseract":
        # Local Tesseract OCR
        from ocr_fallback import ocr_scan_document
        return ocr_scan_document(image_base64)

    from llm_client import chat_with_vision_json

    start_time = time.time()

    try:
        result = await chat_with_vision_json(
            system_message=ID_EXTRACTION_PROMPT,
            user_text="Analyze ALL identity documents visible in this image. There may be 1 or more documents. Extract data from EACH document separately and return them in the documents array. Return ONLY the JSON structure, no markdown.",
            images_base64=[image_base64],
            model=provider["model"],
        )

        elapsed = time.time() - start_time

        if "documents" in result and isinstance(result["documents"], list):
            pass
        else:
            result = {"document_count": 1, "documents": [result]}

        update_provider_health(provider_id, True, elapsed)

        return {
            "success": True,
            "provider": provider_id,
            "provider_name": provider["name"],
            "response_time": round(elapsed, 2),
            "estimated_cost": provider["cost_per_scan"],
            **result,
        }

    except Exception:
        elapsed = time.time() - start_time
        update_provider_health(provider_id, False, elapsed)
        raise


async def smart_scan(image_base64: str, quality_score: int = 70, preferred_provider: Optional[str] = None) -> dict:
    """Akıllı tarama: kaliteye göre provider seç, fallback zinciri uygula"""

    if preferred_provider and preferred_provider in PROVIDERS:
        # Kullanıcı tercih belirtti, önce onu dene
        chain = [preferred_provider]
        # Fallback olarak akıllı zinciri ekle
        smart_chain = get_smart_provider_chain(quality_score)
        for p in smart_chain:
            if p not in chain:
                chain.append(p)
    else:
        chain = get_smart_provider_chain(quality_score)

    errors = []
    for provider_id in chain:
        try:
            result = await extract_with_provider(provider_id, image_base64)
            result["fallback_used"] = provider_id != chain[0]
            result["original_provider"] = chain[0]
            result["provider_chain"] = chain
            return result
        except Exception as e:
            errors.append({
                "provider": provider_id,
                "error": str(e),
            })
            continue

    # Tüm provider'lar başarısız
    return {
        "success": False,
        "error": "Tüm AI sağlayıcılar başarısız oldu",
        "errors": errors,
        "documents": [],
        "provider_chain": chain,
    }


def get_provider_stats() -> dict:
    """Provider istatistiklerini al"""
    stats = {}
    for pid, health in _provider_health.items():
        provider = PROVIDERS.get(pid, {})
        stats[pid] = {
            "name": provider.get("name", pid),
            "status": health.get("status", "unknown"),
            "total_calls": health.get("total_calls", 0),
            "success_rate": health.get("success_rate", 0),
            "avg_response_time": round(health.get("avg_response_time", 0), 2),
            "consecutive_fails": health.get("consecutive_fails", 0),
            "cost_per_scan": provider.get("cost_per_scan", 0),
        }
    return stats


def estimate_scan_cost(provider_id: str) -> dict:
    """Tarama maliyet tahmini"""
    provider = PROVIDERS.get(provider_id)
    if not provider:
        return {"error": "Bilinmeyen provider"}

    return {
        "provider": provider_id,
        "provider_name": provider["name"],
        "estimated_cost_usd": provider["cost_per_scan"],
        "speed": provider["speed"],
        "quality": provider["quality"],
    }
