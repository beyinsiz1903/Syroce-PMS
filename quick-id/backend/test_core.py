"""
Core POC - ID Card Reader using OpenAI GPT-4o Vision
Tests the core workflow: Image -> OpenAI Vision -> Structured JSON extraction
"""

import asyncio
import os
import base64
import json
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("ERROR: OPENAI_API_KEY not found in environment")
    exit(1)

print(f"OPENAI_API_KEY loaded: {'yes' if OPENAI_API_KEY else 'no'}")

ID_EXTRACTION_PROMPT = """You are an expert ID document reader. You analyze images of identity documents (ID cards, passports, driver's licenses) and extract structured information.

IMPORTANT RULES:
1. Extract ALL visible text fields from the document
2. Return ONLY valid JSON - no markdown, no extra text
3. If a field is not visible or unclear, set it to null
4. Normalize dates to YYYY-MM-DD format
5. For gender, use "M" (Male/Erkek) or "F" (Female/Kadin)
6. Detect the document type automatically
7. If the image is blurry, cropped, or not an ID document, set "is_valid" to false

Return this exact JSON structure:
{
    "is_valid": true/false,
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
    "warnings": ["list of any issues or uncertain fields"],
    "raw_extracted_text": "all visible text from the document"
}
"""


async def test_image_extraction(image_path: str, test_name: str):
    """Test extraction from a single image file"""
    from llm_client import chat_with_vision_json

    print(f"\n{'='*60}")
    print(f"TEST: {test_name}")
    print(f"Image: {image_path}")
    print(f"{'='*60}")

    if not os.path.exists(image_path):
        print(f"ERROR: Image file not found: {image_path}")
        return False

    with open(image_path, "rb") as f:
        image_data = f.read()

    image_base64 = base64.b64encode(image_data).decode("utf-8")
    print(f"Image loaded: {len(image_data)} bytes")

    try:
        print("Sending image to OpenAI GPT-4o Vision...")
        extracted = await chat_with_vision_json(
            system_message=ID_EXTRACTION_PROMPT,
            user_text="Please analyze this identity document image and extract all information. Return ONLY the JSON structure as specified.",
            images_base64=[image_base64],
            model="gpt-4o",
        )
        print(f"JSON parsed successfully")
        print(f"\nExtracted Data:")
        print(json.dumps(extracted, indent=2, ensure_ascii=False))

        required_fields = ["is_valid", "document_type", "first_name", "last_name"]
        missing = [f for f in required_fields if f not in extracted]
        if missing:
            print(f"Missing required fields: {missing}")
            return False

        if extracted.get("is_valid"):
            print(f"\nPASS - Document recognized as: {extracted.get('document_type')}")
            print(f"  Name: {extracted.get('first_name')} {extracted.get('last_name')}")
            print(f"  ID/Passport: {extracted.get('id_number') or extracted.get('document_number')}")
        else:
            print(f"\nDocument marked as invalid - Warnings: {extracted.get('warnings')}")

        return True

    except Exception as e:
        print(f"FAIL - Error: {type(e).__name__}: {e}")
        return False


async def main():
    print("=" * 60)
    print("Core POC - ID Card Reader Vision Test")
    print("=" * 60)

    results = {}

    results["passport_portugal"] = await test_image_extraction(
        "test_images/passport_portugal.jpg",
        "Portuguese Passport"
    )

    results["passport_german"] = await test_image_extraction(
        "test_images/passport_german.jpg",
        "German Passport"
    )

    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"  {status} - {name}")
    print(f"\nTotal: {passed}/{total} passed")

    return passed == total


if __name__ == "__main__":
    asyncio.run(main())
