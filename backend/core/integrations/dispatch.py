import hashlib
from datetime import timedelta

from models.schemas.invoice_sync import InvoiceDocumentKind, InvoiceProvider, InvoiceSyncState

_TRANSITIONS = {
    None: {InvoiceSyncState.PREPARED},
    InvoiceSyncState.PREPARED: {
        InvoiceSyncState.PREPARED,
        InvoiceSyncState.QUEUED,
        InvoiceSyncState.CANCELLED,
    },
    InvoiceSyncState.QUEUED: {
        InvoiceSyncState.QUEUED,
        InvoiceSyncState.SENDING,
        InvoiceSyncState.CANCELLED,
    },
    InvoiceSyncState.SENDING: {
        InvoiceSyncState.SENDING,
        InvoiceSyncState.SUBMITTED,
        InvoiceSyncState.RETRYABLE_ERROR,
        InvoiceSyncState.PERMANENT_ERROR,
        InvoiceSyncState.REJECTED,
    },
    InvoiceSyncState.SUBMITTED: {
        InvoiceSyncState.SUBMITTED,
        InvoiceSyncState.ACCEPTED,
        InvoiceSyncState.REJECTED,
        InvoiceSyncState.RETRYABLE_ERROR,
        InvoiceSyncState.PERMANENT_ERROR,
    },
    InvoiceSyncState.RETRYABLE_ERROR: {
        InvoiceSyncState.QUEUED,
        InvoiceSyncState.CANCELLED,
        InvoiceSyncState.PERMANENT_ERROR,
    },
    InvoiceSyncState.ACCEPTED: {InvoiceSyncState.ACCEPTED},
    InvoiceSyncState.REJECTED: {InvoiceSyncState.REJECTED},
    InvoiceSyncState.PERMANENT_ERROR: {InvoiceSyncState.PERMANENT_ERROR},
    InvoiceSyncState.CANCELLED: {InvoiceSyncState.CANCELLED},
}

_TERMINAL_STATES = {
    InvoiceSyncState.ACCEPTED,
    InvoiceSyncState.REJECTED,
    InvoiceSyncState.PERMANENT_ERROR,
    InvoiceSyncState.CANCELLED,
}


def can_transition(current: InvoiceSyncState | None, target: InvoiceSyncState) -> bool:
    if current not in _TRANSITIONS:
        return False
    return target in _TRANSITIONS[current]


def assert_transition(current: InvoiceSyncState | None, target: InvoiceSyncState) -> None:
    if not can_transition(current, target):
        raise ValueError(f"Invalid state transition from {current} to {target}")


def is_terminal(state: InvoiceSyncState) -> bool:
    return state in _TERMINAL_STATES


def generate_idempotency_key(tenant_id: str, invoice_id: str, provider: InvoiceProvider, document_kind: InvoiceDocumentKind) -> str:
    if not tenant_id or not str(tenant_id).strip():
        raise ValueError("Tenant ID is required")
    if not invoice_id or not str(invoice_id).strip():
        raise ValueError("Invoice ID is required")

    t_id = str(tenant_id).strip()
    i_id = str(invoice_id).strip()
    p = provider.value.strip().upper()
    k = document_kind.value.strip().upper()

    canonical = f"v1|tenant={t_id}|invoice={i_id}|provider={p}|kind={k}"
    hash_val = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"v1:{hash_val}"


def get_retry_delay(attempt: int) -> timedelta | None:
    """Returns delay for the next attempt. attempt is the number of failed attempts so far."""
    delays = {
        1: timedelta(seconds=30),
        2: timedelta(minutes=2),
        3: timedelta(minutes=10),
        4: timedelta(minutes=30),
        5: timedelta(hours=2),
        6: timedelta(hours=6),
    }
    return delays.get(attempt)
