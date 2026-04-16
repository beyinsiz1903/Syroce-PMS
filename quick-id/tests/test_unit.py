"""
Quick ID Reader - Otomatik Test Suite
CI/CD pipeline için test yapılandırması
"""
import pytest
import asyncio
import sys
import os

# Backend path'i ekle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# === MRZ Parser Tests ===
class TestMRZParser:
    """MRZ parsing unit testleri"""

    def test_td3_passport_parsing(self):
        from mrz_parser import parse_td3_passport
        lines = [
            "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
            "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
        ]
        result = parse_td3_passport(lines)
        assert result is not None
        assert result["mrz_type"] == "TD3"
        assert result["document_type"] == "passport"
        assert result["last_name"] == "ERIKSSON"
        assert result["first_name"] == "ANNA MARIA"

    def test_td1_id_card_parsing(self):
        from mrz_parser import parse_td1_id_card
        lines = [
            "I<UTOD231458907<<<<<<<<<<<<<<<",
            "7408122F1204159UTO<<<<<<<<<<<6",
            "ERIKSSON<<ANNA<MARIA<<<<<<<<<<",
        ]
        result = parse_td1_id_card(lines)
        assert result is not None
        assert result["mrz_type"] == "TD1"
        assert result["document_type"] == "id_card"

    def test_td2_document_parsing(self):
        from mrz_parser import parse_td2_document
        lines = [
            "I<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<",
            "D231458907UTO7408122F1204159<<<<<<06"
        ]
        result = parse_td2_document(lines)
        assert result is not None
        assert result["mrz_type"] == "TD2"

    def test_mrz_detection_from_text(self):
        from mrz_parser import detect_and_parse_mrz
        text = """
        Some text before
        P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<
        L898902C36UTO7408122F1204159ZE184226B<<<<<10
        Some text after
        """
        result = detect_and_parse_mrz(text)
        assert result is not None
        assert result["mrz_type"] == "TD3"

    def test_no_mrz_in_text(self):
        from mrz_parser import detect_and_parse_mrz
        result = detect_and_parse_mrz("Hello World, no MRZ here")
        assert result is None

    def test_ocr_error_correction(self):
        from mrz_parser import correct_numeric_field
        # O should become 0 in numeric fields
        assert correct_numeric_field("74O8122") == "7408122"
        # I should become 1
        assert correct_numeric_field("I204I59") == "1204159"

    def test_mrz_date_parsing(self):
        from mrz_parser import parse_mrz_date
        assert parse_mrz_date("740812") == "1974-08-12"
        assert parse_mrz_date("250101") == "2025-01-01"
        assert parse_mrz_date("invalid") is None

    def test_icao_compliance(self):
        from mrz_parser import check_icao_compliance
        result = check_icao_compliance({
            "issuing_country": "TUR",
            "nationality": "TUR",
            "checks": {"passport_number": True, "birth_date": True, "expiry_date": True},
            "mrz_type": "TD3",
            "line_lengths": [44, 44],
        })
        assert result["is_compliant"] is True

    def test_parse_mrz_from_text(self):
        from mrz_parser import parse_mrz_from_text
        result = parse_mrz_from_text("No MRZ data here")
        assert result["mrz_detected"] is False


# === Image Quality Tests ===
class TestImageQuality:
    """Görüntü kalite kontrolü testleri"""

    def test_invalid_base64(self):
        from image_quality import assess_image_quality
        result = assess_image_quality("not-valid-base64")
        assert result["quality_checked"] is False

    def test_empty_base64(self):
        from image_quality import assess_image_quality
        result = assess_image_quality("")
        assert result["quality_checked"] is False

    def test_quality_result_structure(self):
        from image_quality import assess_image_quality
        # Create a minimal valid PNG (1x1 pixel)
        import base64
        # Minimal 1x1 white PNG
        png_data = base64.b64encode(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8'
            b'\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        ).decode()
        result = assess_image_quality(png_data)
        # Should have the structure even if image is tiny
        assert "quality_checked" in result
        assert "overall_quality" in result
        assert "overall_score" in result


# === OCR Fallback Tests ===
class TestOCRFallback:
    """OCR fallback testleri"""

    def test_structured_data_extraction(self):
        from ocr_fallback import extract_structured_data
        text = """
        ADI: MEHMET
        SOYADI: YILMAZ
        T.C. KİMLİK NO: 12345678901
        DOĞUM TARİHİ: 15.06.1985
        CİNSİYET: ERKEK
        """
        result = extract_structured_data(text)
        assert result["first_name"] == "MEHMET"
        assert result["last_name"] == "YILMAZ"
        assert result["id_number"] == "12345678901"
        assert result["gender"] == "M"
        assert result["nationality"] == "TR"

    def test_empty_text_extraction(self):
        from ocr_fallback import extract_structured_data
        result = extract_structured_data("")
        assert result["first_name"] is None
        assert result["last_name"] is None

    def test_tesseract_availability(self):
        from ocr_fallback import is_tesseract_available
        # Just check the function runs without error
        result = is_tesseract_available()
        assert isinstance(result, bool)


# === OCR Providers Tests ===
class TestOCRProviders:
    """Multi-provider OCR testleri"""

    def test_list_providers(self):
        from ocr_providers import list_providers
        providers = list_providers()
        assert len(providers) >= 4
        ids = [p["id"] for p in providers]
        assert "gpt-4o" in ids
        assert "gpt-4o-mini" in ids
        assert "gemini-flash" in ids
        assert "tesseract" in ids

    def test_smart_provider_chain_high_quality(self):
        from ocr_providers import get_smart_provider_chain
        chain = get_smart_provider_chain(90)
        assert chain[0] == "gpt-4o-mini"  # High quality -> cheap provider first

    def test_smart_provider_chain_low_quality(self):
        from ocr_providers import get_smart_provider_chain
        chain = get_smart_provider_chain(30)
        assert chain[0] == "gpt-4o"  # Low quality -> best provider first

    def test_cost_estimate(self):
        from ocr_providers import estimate_scan_cost
        est = estimate_scan_cost("gpt-4o")
        assert est["estimated_cost_usd"] == 0.015
        assert est["quality"] == "high"

    def test_cost_estimate_tesseract(self):
        from ocr_providers import estimate_scan_cost
        est = estimate_scan_cost("tesseract")
        assert est["estimated_cost_usd"] == 0.0

    def test_provider_health_tracking(self):
        from ocr_providers import update_provider_health, get_provider_stats
        update_provider_health("gpt-4o", True, 1.5)
        stats = get_provider_stats()
        assert "gpt-4o" in stats
        assert stats["gpt-4o"]["total_calls"] >= 1


# === Room Assignment Tests ===
class TestRoomAssignment:
    """Oda atama unit testleri"""

    def test_room_types_defined(self):
        from room_assignment import ROOM_TYPES, ROOM_STATUSES
        assert len(ROOM_TYPES) > 0
        assert "available" in ROOM_STATUSES
        assert "occupied" in ROOM_STATUSES

    def test_serialize_room(self):
        from room_assignment import serialize_room
        from bson import ObjectId
        doc = {
            "_id": ObjectId(),
            "room_number": "101",
            "status": "available",
        }
        result = serialize_room(doc)
        assert "id" in result
        assert "_id" not in result
        assert result["room_number"] == "101"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
