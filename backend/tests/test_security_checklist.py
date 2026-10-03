"""Regression coverage for production go-live security checks."""

from infra.security_checklist import SecurityChecklistValidator


def test_credential_masking_check_exercises_the_real_masker():
    result = SecurityChecklistValidator().check_credential_masking()

    assert result["module_available"] is True
    assert result["masking_functional"] is True
    assert result["pass"] is True


def test_rate_limiting_check_uses_the_tenant_limiter():
    result = SecurityChecklistValidator().check_rate_limiting()

    assert result["module_available"] is True
    assert result["limiter_configured"] is True
    assert result["pass"] is True


def test_log_filtering_check_exercises_the_real_sanitizer():
    result = SecurityChecklistValidator().check_sensitive_log_filtering()

    assert result["sanitizer_available"] is True
    assert result["filtering_functional"] is True
    assert result["pass"] is True
