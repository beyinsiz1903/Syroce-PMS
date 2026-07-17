import pytest
from datetime import timedelta
import hashlib

from models.schemas.invoice_sync import InvoiceSyncState, InvoiceProvider, InvoiceDocumentKind
from core.integrations.dispatch import (
    can_transition,
    assert_transition,
    is_terminal,
    generate_idempotency_key,
    get_retry_delay,
    _TRANSITIONS,
    _TERMINAL_STATES
)

def test_all_state_strings_parseable():
    assert InvoiceSyncState("PREPARED") == InvoiceSyncState.PREPARED
    with pytest.raises(ValueError):
        InvoiceSyncState("UNKNOWN_STATE")

def test_enums():
    assert InvoiceProvider("NILVERA") == InvoiceProvider.NILVERA
    assert InvoiceDocumentKind("E_INVOICE") == InvoiceDocumentKind.E_INVOICE

def test_is_terminal():
    for state in _TERMINAL_STATES:
        assert is_terminal(state)
    
    non_terminal = set(InvoiceSyncState) - _TERMINAL_STATES
    for state in non_terminal:
        assert not is_terminal(state)

def test_valid_transitions():
    for source, targets in _TRANSITIONS.items():
        for target in targets:
            assert can_transition(source, target)
            assert_transition(source, target)  # should not raise

def test_invalid_transitions():
    all_states = set(InvoiceSyncState)
    for source, targets in _TRANSITIONS.items():
        invalid_targets = all_states - targets
        for target in invalid_targets:
            assert not can_transition(source, target)
            with pytest.raises(ValueError):
                assert_transition(source, target)

def test_self_transitions():
    # Terminal states can transition to themselves
    for state in _TERMINAL_STATES:
        assert can_transition(state, state)
    
    assert can_transition(InvoiceSyncState.PREPARED, InvoiceSyncState.PREPARED)
    assert can_transition(InvoiceSyncState.QUEUED, InvoiceSyncState.QUEUED)
    assert can_transition(InvoiceSyncState.SENDING, InvoiceSyncState.SENDING)
    assert can_transition(InvoiceSyncState.SUBMITTED, InvoiceSyncState.SUBMITTED)

def test_idempotency_key_generation():
    key = generate_idempotency_key("tenant1", "inv1", InvoiceProvider.NILVERA, InvoiceDocumentKind.E_INVOICE)
    assert key.startswith("v1:")
    assert len(key) == 3 + 64 # "v1:" + 64 hex chars
    
    # Same inputs, same key
    key2 = generate_idempotency_key("tenant1", "inv1", InvoiceProvider.NILVERA, InvoiceDocumentKind.E_INVOICE)
    assert key == key2

    # Different inputs, different key
    assert key != generate_idempotency_key("tenant2", "inv1", InvoiceProvider.NILVERA, InvoiceDocumentKind.E_INVOICE)
    assert key != generate_idempotency_key("tenant1", "inv2", InvoiceProvider.NILVERA, InvoiceDocumentKind.E_INVOICE)

def test_idempotency_key_whitespace_and_case():
    # Should strip whitespace and uppercase enums
    key1 = generate_idempotency_key(" tenant1 ", " inv1\n", InvoiceProvider.NILVERA, InvoiceDocumentKind.E_INVOICE)
    key2 = generate_idempotency_key("tenant1", "inv1", InvoiceProvider.NILVERA, InvoiceDocumentKind.E_INVOICE)
    assert key1 == key2

def test_idempotency_key_empty_validation():
    with pytest.raises(ValueError):
        generate_idempotency_key("", "inv1", InvoiceProvider.NILVERA, InvoiceDocumentKind.E_INVOICE)
    with pytest.raises(ValueError):
        generate_idempotency_key("tenant1", "   ", InvoiceProvider.NILVERA, InvoiceDocumentKind.E_INVOICE)

def test_get_retry_delay():
    assert get_retry_delay(1) == timedelta(seconds=30)
    assert get_retry_delay(2) == timedelta(minutes=2)
    assert get_retry_delay(3) == timedelta(minutes=10)
    assert get_retry_delay(4) == timedelta(minutes=30)
    assert get_retry_delay(5) == timedelta(hours=2)
    assert get_retry_delay(6) == timedelta(hours=6)
    assert get_retry_delay(7) is None
