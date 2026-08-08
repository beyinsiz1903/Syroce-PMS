from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from core.integrations.nilvera.errors import NilveraValidationError
from core.integrations.nilvera.incoming_answer import (
    NilveraIncomingAnswerDecision,
    NilveraIncomingAnswerPayload,
    NilveraIncomingAnswerService,
    NilveraIncomingAnswerState,
)

PROVIDER_UUID = "11112222-3333-4444-5555-666677778888"


@pytest.mark.asyncio
async def test_send_approved_answer_uses_documented_contract_without_retry():
    client = SimpleNamespace(post=AsyncMock(return_value="accepted"))
    service = NilveraIncomingAnswerService(client)

    await service.send_answer(
        PROVIDER_UUID,
        NilveraIncomingAnswerDecision.APPROVED,
        correlation_id="safe-correlation",
    )

    client.post.assert_awaited_once_with(
        "/einvoice/Purchase/SendAnswer",
        json={"UUID": PROVIDER_UUID, "AnswerCode": "approved"},
        correlation_id="safe-correlation",
        retryable=False,
    )


@pytest.mark.asyncio
async def test_send_rejected_answer_includes_only_bounded_note():
    client = SimpleNamespace(post=AsyncMock(return_value=None))
    service = NilveraIncomingAnswerService(client)

    await service.send_answer(
        PROVIDER_UUID,
        NilveraIncomingAnswerDecision.REJECTED,
        reject_note="  sandbox rejection  ",
    )

    payload = client.post.await_args.kwargs["json"]
    assert payload == {
        "UUID": PROVIDER_UUID,
        "AnswerCode": "rejected",
        "RejectNote": "sandbox rejection",
    }


def test_rejected_payload_requires_note():
    with pytest.raises(ValidationError, match="RejectNote is required"):
        NilveraIncomingAnswerPayload(
            UUID=PROVIDER_UUID,
            AnswerCode=NilveraIncomingAnswerDecision.REJECTED,
        )


def test_approved_payload_rejects_note():
    with pytest.raises(ValidationError, match="RejectNote is not allowed"):
        NilveraIncomingAnswerPayload(
            UUID=PROVIDER_UUID,
            AnswerCode=NilveraIncomingAnswerDecision.APPROVED,
            RejectNote="must not be sent",
        )


@pytest.mark.asyncio
async def test_send_answer_rejects_invalid_uuid_without_echoing_value():
    sensitive_value = "provider-identity-that-must-not-leak"
    client = SimpleNamespace(post=AsyncMock())
    service = NilveraIncomingAnswerService(client)

    with pytest.raises(NilveraValidationError) as exc_info:
        await service.send_answer(
            sensitive_value,
            NilveraIncomingAnswerDecision.APPROVED,
        )

    assert sensitive_value not in str(exc_info.value)
    client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_answer_rejects_undocumented_success_response():
    client = SimpleNamespace(post=AsyncMock(return_value={"unexpected": True}))
    service = NilveraIncomingAnswerService(client)

    with pytest.raises(NilveraValidationError, match="unexpected response type"):
        await service.send_answer(
            PROVIDER_UUID,
            NilveraIncomingAnswerDecision.APPROVED,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("answer_code", "expected"),
    [
        (None, NilveraIncomingAnswerState.UNKNOWN),
        ("waitingForApproval", NilveraIncomingAnswerState.WAITING),
        ("approved", NilveraIncomingAnswerState.APPROVED),
        ("rejected", NilveraIncomingAnswerState.REJECTED),
        ("documentAnsweredAutomatically", NilveraIncomingAnswerState.ANSWERED_AUTOMATICALLY),
    ],
)
async def test_fetch_answer_state_maps_documented_values(answer_code, expected):
    client = SimpleNamespace()
    service = NilveraIncomingAnswerService(client)
    service._incoming.fetch_incoming_invoice_status = AsyncMock(return_value=SimpleNamespace(answer_code=answer_code))

    assert await service.fetch_answer_state(PROVIDER_UUID) == expected


@pytest.mark.asyncio
async def test_fetch_answer_state_rejects_unknown_contract_value():
    client = SimpleNamespace()
    service = NilveraIncomingAnswerService(client)
    service._incoming.fetch_incoming_invoice_status = AsyncMock(return_value=SimpleNamespace(answer_code="newProviderValue"))

    with pytest.raises(NilveraValidationError, match="unsupported"):
        await service.fetch_answer_state(PROVIDER_UUID)
