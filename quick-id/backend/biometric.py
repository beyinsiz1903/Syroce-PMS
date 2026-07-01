"""
Biyometrik Yüz Eşleştirme Modülü
- Belge fotoğrafı ile canlı yüz karşılaştırma
- Liveness detection (spoofing önleme)
- Eşleştirme güven skoru
- Işık ve açı toleransı
"""
from datetime import datetime, timezone
from typing import Optional
import uuid
import json
import os
import random

LIVENESS_CHALLENGES = [
    {"challenge_id": "turn_right", "instruction": "Lütfen yüzünüzü sağa çevirin", "instruction_en": "Please turn your face to the right"},
    {"challenge_id": "turn_left", "instruction": "Lütfen yüzünüzü sola çevirin", "instruction_en": "Please turn your face to the left"},
    {"challenge_id": "look_up", "instruction": "Lütfen yukarı bakın", "instruction_en": "Please look up"},
    {"challenge_id": "smile", "instruction": "Lütfen gülümseyin", "instruction_en": "Please smile"},
    {"challenge_id": "blink", "instruction": "Lütfen gözlerinizi kırpın", "instruction_en": "Please blink your eyes"},
    {"challenge_id": "open_mouth", "instruction": "Lütfen ağzınızı açın", "instruction_en": "Please open your mouth"},
]


def get_liveness_challenge() -> dict:
    """Rastgele bir canlılık testi sorusu döndür"""
    challenge = random.choice(LIVENESS_CHALLENGES)
    return {
        "session_id": str(uuid.uuid4()),
        "challenge": challenge,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_in_seconds": 30,
    }


FACE_COMPARISON_PROMPT = """You are a biometric face matching expert for a hotel check-in verification system.

You will receive TWO images:
1. First image: A photo from an identity document (ID card, passport, etc.)
2. Second image: A live selfie/photo of a person

Your task is to compare the faces and determine if they are the SAME person.

ANALYSIS CRITERIA:
1. Facial structure similarity (jawline, cheekbones, forehead shape)
2. Eye shape and spacing
3. Nose shape and size
4. Mouth and lip shape
5. Overall proportions
6. Consider aging differences (document photo may be older)
7. Consider lighting and angle differences
8. Consider that document photos are often more formal/different quality

IMPORTANT RULES:
- Return ONLY valid JSON, no markdown, no extra text
- Be lenient with lighting/angle differences
- Consider natural aging (up to 10 years difference)
- Document photos are usually more formal/staged

Return this exact JSON structure:
{
    "match": true or false,
    "confidence_score": 0 to 100 (integer),
    "confidence_level": "high" (80-100) or "medium" (50-79) or "low" (0-49),
    "analysis": {
        "facial_structure": "match" or "partial" or "mismatch",
        "eyes": "match" or "partial" or "mismatch",
        "nose": "match" or "partial" or "mismatch",
        "mouth": "match" or "partial" or "mismatch",
        "overall_proportions": "match" or "partial" or "mismatch"
    },
    "notes": "Brief explanation of the comparison result",
    "warnings": ["list of any issues detected"],
    "image_quality": {
        "document_photo": "good" or "acceptable" or "poor",
        "selfie_photo": "good" or "acceptable" or "poor"
    }
}"""

LIVENESS_CHECK_PROMPT = """You are a liveness detection expert. Analyze the provided image to determine if this is a REAL live person or a SPOOF attempt (photo of a photo, video playback, mask, etc.).

The person was asked to perform this specific action: "{challenge_instruction}"

ANALYSIS CRITERIA:
1. Does the image appear to be a live capture (not a photo of a screen/photo)?
2. Is the person performing the requested action?
3. Look for signs of spoofing: screen edges, moiré patterns, flat appearance, printed paper edges
4. Check for natural skin texture, 3D depth cues, natural lighting on face
5. Check for proper head/face positioning indicating a live person

Return ONLY valid JSON:
{{
    "is_live": true or false,
    "challenge_completed": true or false,
    "confidence_score": 0 to 100,
    "spoof_indicators": ["list any detected spoof signs"],
    "analysis": {{
        "natural_lighting": true or false,
        "3d_depth_cues": true or false,
        "skin_texture": "natural" or "flat" or "pixelated",
        "screen_artifacts": false or true,
        "paper_edges": false or true
    }},
    "notes": "Brief explanation"
}}"""


async def compare_faces(document_image_b64: str, selfie_image_b64: str) -> dict:
    """İki yüzü karşılaştır: belge fotoğrafı vs canlı fotoğraf"""
    from llm_client import chat_with_vision_json

    try:
        result = await chat_with_vision_json(
            system_message=FACE_COMPARISON_PROMPT,
            user_text="Compare the faces in these two images. First image is from an identity document, second is a live selfie. Determine if they are the same person. Return ONLY JSON.",
            images_base64=[document_image_b64, selfie_image_b64],
            model="gpt-4o",
        )
        return result
    except Exception:
        return {
            "match": False,
            "confidence_score": 0,
            "confidence_level": "low",
            "notes": "Yüz karşılaştırma analizi başarısız",
            "warnings": ["AI yanıtı ayrıştırılamadı"],
        }


async def check_liveness(image_b64: str, challenge_id: str) -> dict:
    """Canlılık testi: fotoğraf/video spoofing kontrolü"""
    from llm_client import chat_with_vision_json

    challenge_instruction = "Yüzünüzü kameraya gösterin"
    for c in LIVENESS_CHALLENGES:
        if c["challenge_id"] == challenge_id:
            challenge_instruction = c["instruction"]
            break

    prompt = LIVENESS_CHECK_PROMPT.format(challenge_instruction=challenge_instruction)

    try:
        result = await chat_with_vision_json(
            system_message=prompt,
            user_text=f"Check if this is a live person performing the action: '{challenge_instruction}'. Detect any spoofing attempts. Return ONLY JSON.",
            images_base64=[image_b64],
            model="gpt-4o",
        )
        return result
    except Exception:
        return {
            "is_live": False,
            "challenge_completed": False,
            "confidence_score": 0,
            "notes": "Canlılık analizi başarısız",
            "spoof_indicators": ["AI yanıtı ayrıştırılamadı"],
        }
