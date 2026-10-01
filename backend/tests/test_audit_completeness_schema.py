from modules.security_hardening.audit_completeness import _audit_entry_category


def test_audit_category_supports_current_resource_type_schema():
    assert _audit_entry_category({"resource_type": "auth", "action": "token_refresh"}) == "auth"


def test_audit_category_keeps_legacy_entity_type_compatibility():
    assert _audit_entry_category({"entity_type": "folio", "action": "payment"}) == "folio"
    assert _audit_entry_category({}) == "unknown"
