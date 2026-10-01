from types import SimpleNamespace

import jwt

from core.tenant_middleware import TenantContextMiddleware
from shared_kernel.audit_helper import build_audit_entry


def _user(policy):
    return SimpleNamespace(role="front_desk", granted_permissions=[], guest_data_visibility=policy)


def test_legacy_audit_writer_emits_canonical_timeline_fields():
    entry = build_audit_entry(
        actor_id="user-1",
        tenant_id="hotel-1",
        entity_type="booking",
        entity_id="booking-1",
        action="booking_updated",
    )

    assert entry["operation_name"] == "booking_updated"
    assert entry["target_type"] == "booking"
    assert entry["target_id"] == "booking-1"
    assert entry["result_status"] == "success"
    assert entry["severity"] == "info"


def test_audit_response_masks_guest_data_and_always_redacts_secrets():
    from routers.audit_timeline import _normalize_audit_record

    record = _normalize_audit_record(
        {
            "action": "guest_updated",
            "entity_type": "guest",
            "entity_id": "guest-1",
            "after_snapshot": {
                "name": "Ayşe Yılmaz",
                "email": "ayse@example.com",
                "phone": "05551234567",
                "password": "do-not-store-this",
            },
        },
        _user({"name": "masked", "email": "hidden", "phone": "masked"}),
    )

    snapshot = record["after_snapshot"]
    assert snapshot["name"] != "Ayşe Yılmaz"
    assert snapshot["email"] is None
    assert snapshot["phone"].endswith("4567")
    assert snapshot["password"] == "***REDACTED***"
    assert record["operation_name"] == "guest_updated"
    assert record["target_type"] == "guest"


def test_middleware_accepts_only_access_token_identity():
    secret = "unit-test-secret-with-more-than-32-characters"
    middleware = TenantContextMiddleware(lambda *_: None, jwt_secret=secret)
    access = jwt.encode(
        {"tenant_id": "hotel-1", "user_id": "user-1", "type": "access"},
        secret,
        algorithm="HS256",
    )
    refresh = jwt.encode(
        {"tenant_id": "hotel-1", "user_id": "user-1", "type": "refresh"},
        secret,
        algorithm="HS256",
    )

    assert middleware._extract_identity([(b"authorization", f"Bearer {access}".encode())]) == {
        "tenant_id": "hotel-1",
        "user_id": "user-1",
        "role": "",
    }
    assert middleware._extract_identity([(b"authorization", f"Bearer {refresh}".encode())]) == {}
