"""
Quick ID Reader - Backend Test Suite
pytest birim ve entegrasyon testleri
Hedef: %80+ coverage

Kullanım: cd /app/backend && python -m pytest tests/ -v
"""
import pytest
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============== Auth Tests ==============

class TestAuth:
    """Auth modülü birim testleri"""

    def test_hash_password(self):
        from auth import hash_password, verify_password
        hashed = hash_password("test123")
        assert hashed != "test123"
        assert verify_password("test123", hashed)
        assert not verify_password("wrong", hashed)

    def test_create_and_decode_token(self):
        from auth import create_token, decode_token
        data = {"sub": "user1", "email": "test@test.com", "role": "admin"}
        token = create_token(data)
        assert token is not None
        decoded = decode_token(token)
        assert decoded is not None
        assert decoded["email"] == "test@test.com"
        assert decoded["role"] == "admin"
        assert "exp" in decoded

    def test_token_expiry(self):
        from auth import create_token, decode_token
        data = {"sub": "user1", "email": "test@test.com"}
        token = create_token(data, expires_delta=timedelta(seconds=-1))
        decoded = decode_token(token)
        assert decoded is None  # Expired token

    def test_invalid_token(self):
        from auth import decode_token
        result = decode_token("invalid.token.here")
        assert result is None

    def test_empty_token(self):
        from auth import decode_token
        result = decode_token("")
        assert result is None


# ============== KVKK Settings Tests ==============

class TestKvkkSettings:
    """KVKK ayarları birim testleri"""

    def test_default_settings(self):
        from kvkk import DEFAULT_SETTINGS
        assert DEFAULT_SETTINGS["retention_days_scans"] == 90
        assert DEFAULT_SETTINGS["retention_days_audit"] == 365
        assert DEFAULT_SETTINGS["kvkk_consent_required"] is True
        assert "kvkk_consent_text" in DEFAULT_SETTINGS
        assert DEFAULT_SETTINGS["auto_cleanup_enabled"] is True


# ============== Confidence Scoring Tests ==============

class TestConfidenceScoring:
    """AI tarama güvenilirlik puanlama testleri"""

    def test_high_confidence_score(self):
        from kvkk_compliance import calculate_confidence_score
        data = {
            "documents": [{
                "is_valid": True,
                "first_name": "Ali",
                "last_name": "Yılmaz",
                "id_number": "12345678901",
                "birth_date": "1990-01-01",
                "document_type": "tc_kimlik",
                "nationality": "TC",
                "gender": "M",
                "expiry_date": "2030-01-01",
                "document_number": "A12345",
                "birth_place": "İstanbul",
                "warnings": []
            }]
        }
        result = calculate_confidence_score(data)
        assert result["overall_score"] >= 85
        assert result["confidence_level"] == "high"
        assert result["review_needed"] is False

    def test_medium_confidence_score(self):
        from kvkk_compliance import calculate_confidence_score
        data = {
            "documents": [{
                "is_valid": True,
                "first_name": "Ali",
                "last_name": "Yılmaz",
                "id_number": "12345678901",
                "birth_date": None,
                "document_type": "tc_kimlik",
                "nationality": None,
                "gender": None,
                "warnings": ["Bazı alanlar okunamadı"]
            }]
        }
        result = calculate_confidence_score(data)
        assert 50 <= result["overall_score"] < 85
        assert result["confidence_level"] in ("medium", "low")

    def test_low_confidence_invalid_doc(self):
        from kvkk_compliance import calculate_confidence_score
        data = {
            "documents": [{
                "is_valid": False,
                "first_name": None,
                "last_name": None,
                "id_number": None,
                "birth_date": None,
                "document_type": "other",
                "nationality": None,
                "warnings": ["Belge tanınamadı", "Görüntü çok bulanık", "Metin okunamadı"]
            }]
        }
        result = calculate_confidence_score(data)
        assert result["overall_score"] < 70
        assert result["confidence_level"] == "low"
        assert result["review_needed"] is True

    def test_empty_documents(self):
        from kvkk_compliance import calculate_confidence_score
        result = calculate_confidence_score({"documents": []})
        assert result["overall_score"] == 0
        assert result["review_needed"] is True

    def test_multiple_documents(self):
        from kvkk_compliance import calculate_confidence_score
        data = {
            "documents": [
                {
                    "is_valid": True,
                    "first_name": "Ali",
                    "last_name": "Yılmaz",
                    "id_number": "12345678901",
                    "birth_date": "1990-01-01",
                    "document_type": "tc_kimlik",
                    "nationality": "TC",
                    "warnings": []
                },
                {
                    "is_valid": False,
                    "first_name": None,
                    "last_name": None,
                    "id_number": None,
                    "warnings": ["Okunamadı"]
                }
            ]
        }
        result = calculate_confidence_score(data)
        assert len(result["document_scores"]) == 2
        # Average should be somewhere in between
        assert 20 < result["overall_score"] < 90


# ============== KVKK Compliance Tests ==============

class TestKvkkCompliance:
    """KVKK uyumluluk fonksiyon testleri"""

    def test_valid_request_types(self):
        from kvkk_compliance import VALID_REQUEST_TYPES
        assert "access" in VALID_REQUEST_TYPES
        assert "rectification" in VALID_REQUEST_TYPES
        assert "erasure" in VALID_REQUEST_TYPES
        assert "portability" in VALID_REQUEST_TYPES
        assert "objection" in VALID_REQUEST_TYPES

    def test_valid_request_statuses(self):
        from kvkk_compliance import VALID_REQUEST_STATUSES
        assert "pending" in VALID_REQUEST_STATUSES
        assert "in_progress" in VALID_REQUEST_STATUSES
        assert "completed" in VALID_REQUEST_STATUSES
        assert "rejected" in VALID_REQUEST_STATUSES


# ============== Data Model Tests ==============

class TestDataModels:
    """Pydantic model validasyon testleri"""

    def test_scan_request_model(self):
        sys.path.insert(0, '/app/backend')
        from server import ScanRequest
        req = ScanRequest(image_base64="dGVzdA==")
        assert req.image_base64 == "dGVzdA=="

    def test_guest_create_model(self):
        from server import GuestCreate
        guest = GuestCreate(
            first_name="Ali",
            last_name="Yılmaz",
            id_number="12345678901",
            kvkk_consent=True
        )
        assert guest.first_name == "Ali"
        assert guest.kvkk_consent is True
        assert guest.force_create is False

    def test_guest_create_defaults(self):
        from server import GuestCreate
        guest = GuestCreate()
        assert guest.first_name is None
        assert guest.force_create is False
        assert guest.kvkk_consent is False

    def test_login_request_model(self):
        from server import LoginRequest
        req = LoginRequest(email="test@test.com", password="pass")
        assert req.email == "test@test.com"

    def test_user_create_model(self):
        from server import UserCreate
        user = UserCreate(email="a@b.com", password="pass", name="Test")
        assert user.role == "reception"  # default role

    def test_settings_update_model(self):
        from server import SettingsUpdate
        settings = SettingsUpdate(retention_days_scans=30)
        assert settings.retention_days_scans == 30
        assert settings.kvkk_consent_required is None

    def test_rights_request_model(self):
        from server import RightsRequestCreate
        req = RightsRequestCreate(
            request_type="access",
            requester_name="Ali Yılmaz",
            requester_email="ali@test.com",
            description="Verilerime erişim istiyorum"
        )
        assert req.request_type == "access"
        assert req.guest_id is None

    def test_rights_request_process_model(self):
        from server import RightsRequestProcess
        req = RightsRequestProcess(
            status="completed",
            response_note="Talep işlendi"
        )
        assert req.status == "completed"
        assert req.response_data is None


# ============== Serialization Tests ==============

class TestSerialization:
    """Veri serialization testleri"""

    def test_serialize_doc_with_objectid(self):
        from bson import ObjectId
        from server import serialize_doc
        doc = {"_id": ObjectId(), "name": "test", "value": 123}
        result = serialize_doc(doc)
        assert "id" in result
        assert "_id" not in result
        assert result["name"] == "test"

    def test_serialize_doc_with_datetime(self):
        from server import serialize_doc
        now = datetime.now(timezone.utc)
        doc = {"_id": "test", "created_at": now}
        result = serialize_doc(doc)
        assert isinstance(result["created_at"], str)

    def test_serialize_doc_none(self):
        from server import serialize_doc
        assert serialize_doc(None) is None

    def test_serialize_doc_nested(self):
        from server import serialize_doc
        doc = {"_id": "test", "data": {"nested": True}}
        result = serialize_doc(doc)
        assert result["data"]["nested"] is True

    def test_serialize_doc_password_hidden(self):
        from server import serialize_doc
        doc = {"_id": "test", "password_hash": "secret", "name": "visible"}
        result = serialize_doc(doc)
        assert "password_hash" not in result
        assert result["name"] == "visible"


# ============== Field Diff Tests ==============

class TestFieldDiffs:
    """Alan değişiklik karşılaştırma testleri"""

    def test_compute_diffs_with_changes(self):
        from server import compute_field_diffs
        old = {"first_name": "Ali", "last_name": "Yılmaz"}
        new = {"first_name": "Veli", "last_name": "Yılmaz"}
        diffs = compute_field_diffs(old, new)
        assert "first_name" in diffs
        assert diffs["first_name"]["old"] == "Ali"
        assert diffs["first_name"]["new"] == "Veli"

    def test_compute_diffs_no_changes(self):
        from server import compute_field_diffs
        data = {"first_name": "Ali", "last_name": "Yılmaz"}
        diffs = compute_field_diffs(data, data)
        assert len(diffs) == 0

    def test_compute_diffs_none_values(self):
        from server import compute_field_diffs
        old = {"first_name": "Ali"}
        new = {"first_name": None}
        diffs = compute_field_diffs(old, new)
        # None values are ignored
        assert len(diffs) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
