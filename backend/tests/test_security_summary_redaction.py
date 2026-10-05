from routers.auth import _mask_security_actor, _safe_security_event


def test_security_actor_is_masked_for_plain_and_encrypted_values():
    assert _mask_security_actor("person@example.com") == "p***@example.com"
    assert _mask_security_actor("SYR1:encrypted-payload") == "Korunan kullanıcı"
    assert _mask_security_actor("opaque-user-id") == "Korunan kullanıcı"


def test_security_event_drops_raw_identifiers_and_unneeded_fields():
    event = _safe_security_event(
        {
            "id": "event-1",
            "tenant_id": "tenant-secret",
            "user_id": "user-secret",
            "user_email": "SYR1:encrypted-payload",
            "action": "token_refresh",
            "details": "Token refreshed via refresh (rotated jti=secret-jti)",
            "ip_address": "203.0.113.10",
            "timestamp": "2026-10-01T09:00:00+00:00",
        }
    )

    assert event == {
        "id": "event-1",
        "action": "token_refresh",
        "timestamp": "2026-10-01T09:00:00+00:00",
        "user_email": "Korunan kullanıcı",
        "details": "Oturum güvenle yenilendi",
    }
    assert "jti" not in str(event).lower()
    assert "tenant-secret" not in str(event)
    assert "203.0.113.10" not in str(event)
