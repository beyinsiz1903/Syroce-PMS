"""Regression tests for deterministic CreateReturn source lookup."""

import inspect

from tests.nilvera_create_return_source import CreateReturnSourceReadiness, resolve_create_return_source_direct


def _source(*, status_state: str = "APPROVED", detail_state: str = "APPROVED", status_ready: bool = True, alias_match: bool = True):
    return CreateReturnSourceReadiness(
        correlation_label="safe-label",
        source_provider_uuid="00000000-0000-4000-8000-000000000000",
        sender_match=True,
        receiver_match=True,
        receiver_status_ready=status_ready,
        receiver_alias_match=alias_match,
        receiver_status_answer_state=status_state,
        receiver_detail_answer_state=detail_state,
    )


def test_direct_source_lookup_does_not_use_paginated_invoice_lists_or_provider_writes():
    source = inspect.getsource(resolve_create_return_source_direct)

    assert "LIST_SALE_INVOICES" not in source
    assert "LIST_PURCHASE_INVOICES" not in source
    assert "RECONCILIATION_MAX_PAGES" not in source
    assert ".post(" not in source
    assert ".put(" not in source
    assert ".patch(" not in source
    assert ".delete(" not in source
    assert "GET_SALE_INVOICE_DETAIL" in source
    assert "fetch_incoming_invoice_detail" in source
    assert "fetch_incoming_invoice_status" in source


def test_source_readiness_requires_terminal_answer_ready_status_and_alias_match():
    assert _source().ready is True
    assert _source(status_state="WAITING_FOR_APPROVAL", detail_state="WAITING_FOR_APPROVAL").ready is False
    assert _source(status_ready=False).ready is False
    assert _source(alias_match=False).ready is False


def test_automatic_answer_is_terminal_for_create_return_source():
    assert _source(status_state="ANSWERED_AUTOMATICALLY", detail_state="UNKNOWN").source_terminal is True
