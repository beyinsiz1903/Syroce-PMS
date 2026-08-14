from pathlib import Path

import pytest

from core.integrations.nilvera.credit_pool import (
    ALLOCATION_STEP,
    MIN_PURCHASE_CREDITS,
    NilveraCreditPoolError,
    _validate_step,
)


def test_purchase_minimum_and_allocation_step_contract() -> None:
    assert MIN_PURCHASE_CREDITS == 100_000
    assert ALLOCATION_STEP == 100
    _validate_step(100_000, minimum=MIN_PURCHASE_CREDITS)
    _validate_step(100, minimum=ALLOCATION_STEP)

    with pytest.raises(NilveraCreditPoolError):
        _validate_step(99_900, minimum=MIN_PURCHASE_CREDITS)
    with pytest.raises(NilveraCreditPoolError):
        _validate_step(150, minimum=ALLOCATION_STEP)


def test_credit_pool_service_has_no_provider_io() -> None:
    source = Path("core/integrations/nilvera/credit_pool.py").read_text()
    forbidden = (
        "NilveraHttpClient",
        ".post(",
        ".put(",
        ".patch(",
        ".delete(",
        "SEND_ANSWER",
        "CREATE_PURCHASE_RETURN",
        "SEND_INVOICE_MODEL",
    )
    assert not [token for token in forbidden if token in source]


def test_credit_pool_api_is_guarded_and_local_only() -> None:
    source = Path("api/routes/nilvera_credit_pool.py").read_text()
    assert 'Depends(require_admin)' in source
    assert source.count("require_super_admin_guard(not_found=False)") >= 5
    assert "NilveraHttpClient" not in source
    assert "provider" not in source.lower() or "provider writes" in source.lower()


def test_credit_pool_tracks_expiry_audit_and_low_balance() -> None:
    source = Path("core/integrations/nilvera/credit_pool.py").read_text()
    assert "timedelta(days=365)" in source
    assert '"event_type": event_type' in source
    assert '"low_balance_threshold"' in source
    assert '"next_expiry_at"' in source
    assert '"expired_unused"' in source


def test_credit_pool_router_is_mounted_via_admin_domain() -> None:
    aggregator = Path("domains/admin/router/__init__.py").read_text()
    bridge = Path("domains/admin/router/nilvera_credits.py").read_text()
    assert "_nilvera_credit_pool_r" in aggregator
    assert "router.include_router(_nilvera_credit_pool_r)" in aggregator
    assert "api.routes.nilvera_credit_pool" in bridge
