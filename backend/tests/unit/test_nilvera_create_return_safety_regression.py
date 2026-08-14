from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).parents[2]


def test_create_return_discovery_routes_to_corrected_draft_verifier():
    selector = (_backend_root() / "scripts/nilvera_sandbox_selector.py").read_text()
    discovery = (_backend_root() / "tests/integration/test_nilvera_create_return_discovery_v2.py").read_text()

    assert "test_nilvera_create_return_discovery_v2.py" in selector
    assert "test_sandbox_create_return_contract_discovery_v2" in selector
    assert "verify_return_draft(" in discovery
    assert "GET_SALE_INVOICE_DETAIL" not in discovery
    assert "GET_SALE_INVOICE_STATUS" not in discovery


def test_lifecycle_persists_generated_uuid_before_draft_verification():
    service = (_backend_root() / "core/integrations/invoice_lifecycle_service.py").read_text()
    start = service.index("async def _process_return_action")
    end = service.index("async def _verify_return_draft", start)
    body = service[start:end]

    response_index = body.index("generated_provider_uuid = str(response.provider_uuid)")
    persist_index = body.index("mark_provider_return_created(")
    verify_index = body.index("await cls._verify_return_draft(")

    assert response_index < persist_index < verify_index


def test_historical_duplicate_reconciliation_is_terminal_and_provider_get_only():
    diagnostic = (
        _backend_root() / "tests/integration/test_nilvera_create_return_draft_contract_diagnostic.py"
    ).read_text()

    assert "AMBIGUOUS_DUPLICATE_RETURN_DRAFTS" in diagnostic
    assert "GET_DRAFT_INVOICE_MODEL" in diagnostic
    assert "provider_write_count\", \"0" in diagnostic
    assert "await receiver.post(" not in diagnostic
    assert "await receiver.put(" not in diagnostic
    assert "await receiver.patch(" not in diagnostic
    assert "await receiver.delete(" not in diagnostic


def test_provider_free_gl_e2e_uses_synthetic_result_and_idempotency():
    diagnostic = (
        _backend_root() / "tests/integration/test_nilvera_create_return_draft_contract_diagnostic.py"
    ).read_text()

    assert "_verify_provider_free_gl_reversal" in diagnostic
    assert "00000000-0000-4000-8000-000000000001" in diagnostic
    assert "nilvera-return:{action_id}" in diagnostic
    assert "gl_reversal_idempotent\", \"true" in diagnostic
