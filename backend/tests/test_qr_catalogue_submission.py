import pytest
from datetime import datetime, UTC
import uuid

from domains.guest.qr_catalogue_service import validate_input_value
from domains.guest.qr_request_description import compute_payload_fingerprint
from domains.guest.qr_submission_service import generate_deterministic_description
from models.schemas.qr_catalogue_submission import StructuredRequestSubmit, LegacyRequestSubmit
from pydantic import ValidationError

def test_fingerprint_normalization():
    # Should ignore order of items and nulls
    payload1 = {
        "language": "EN ",
        "idempotency_key": "123",
        "items": [
            {"service_code": "b", "value": {"quantity": 2}},
            {"service_code": "a", "note": " test "}
        ]
    }
    payload2 = {
        "language": "en",
        "idempotency_key": "123",
        "items": [
            {"service_code": "a", "note": "test"},
            {"service_code": "b", "value": {"quantity": 2}}
        ]
    }
    
    m1 = StructuredRequestSubmit.model_validate(payload1)
    m2 = StructuredRequestSubmit.model_validate(payload2)
    
    f1 = compute_payload_fingerprint(m1.language, m1.items)
    f2 = compute_payload_fingerprint(m2.language, m2.items)
    assert f1 == f2

def test_fingerprint_mismatch():
    payload1 = {
        "language": "tr",
        "idempotency_key": "123",
        "items": [{"service_code": "a"}]
    }
    payload2 = {
        "language": "tr",
        "idempotency_key": "123",
        "items": [{"service_code": "a", "note": "note"}]
    }
    m1 = StructuredRequestSubmit.model_validate(payload1)
    m2 = StructuredRequestSubmit.model_validate(payload2)
    
    assert compute_payload_fingerprint(m1.language, m1.items) != compute_payload_fingerprint(m2.language, m2.items)

def test_value_shapes():
    val = validate_input_value("quantity", {"min": 1, "max": 5}, {"quantity": 3}, "UTC")
    assert val == {"quantity": 3}
    
    with pytest.raises(ValueError):
        validate_input_value("quantity", {"min": 1, "max": 5}, {"quantity": 6}, "UTC")
        
    val = validate_input_value("time", {"interval_minutes": 15}, {"time_value": "14:30"}, "Europe/Istanbul")
    assert val == {"time_value": "14:30"}
    
    with pytest.raises(ValueError):
        validate_input_value("time", {"interval_minutes": 15}, {"time_value": "14:20"}, "Europe/Istanbul")

def test_legacy_validation_tolerance():
    payload = {
        "category": "cleaning",
        "description": "Clean my room",
        "priority": "high",
        "language": "en",
        "extra_unknown_field": "should be dropped implicitly without forbid error in legacy"
    }
    LegacyRequestSubmit.model_validate(payload)

def test_structured_validation_intolerance():
    payload = {
        "idempotency_key": "123",
        "language": "en",
        "items": [{"service_code": "towel"}],
        "extra_unknown_field": "this must fail"
    }
    with pytest.raises(ValidationError):
        StructuredRequestSubmit.model_validate(payload)

def test_deterministic_description():
    desc = generate_deterministic_description(
        "quantity",
        {"quantity": 2},
        "Extra towel",
        {"en": "Towel"},
        {},
        "en",
        "en"
    )
    assert "Miktar: 2" in desc
    assert "Not: Extra towel" in desc
