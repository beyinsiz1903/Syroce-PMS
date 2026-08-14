from pathlib import Path

from scripts.nilvera_sandbox_selector import CREATE_RETURN_RECONCILIATION_TARGET


def test_historical_ambiguity_terminal_target_is_selected():
    assert CREATE_RETURN_RECONCILIATION_TARGET.endswith(
        "test_nilvera_create_return_historical_terminal.py::"
        "test_sandbox_reconcile_create_return_historical_ambiguity"
    )


def test_historical_ambiguity_terminal_path_preserves_fail_closed_guards():
    source = (
        Path(__file__).parents[1]
        / "integration/test_nilvera_create_return_historical_terminal.py"
    ).read_text()

    assert "await receiver.get(" in source
    assert "NilveraEndpoints.GET_DRAFT_INVOICE_MODEL" in source
    assert "await receiver.post(" not in source
    assert "await receiver.put(" not in source
    assert "await receiver.patch(" not in source
    assert "await receiver.delete(" not in source
    assert 'record_property("provider_write_count", "0")' in source
    assert "raw_match_count != 2" in source
    assert "CONFLICT_CREATE_RETURN_HISTORICAL_METADATA_DIFFERENCES" in source
    assert "await _verify_provider_free_gl_reversal()" in source
    assert 'record_property("terminal_state", "AMBIGUOUS_DUPLICATE_RETURN_DRAFTS")' in source
    assert "return" in source
