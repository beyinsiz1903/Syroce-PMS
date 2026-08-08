import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.config import NilveraEndpoints
from core.integrations.nilvera.errors import NilveraValidationError
from core.integrations.nilvera.incoming import NilveraIncomingService


class NilveraIncomingAnswerDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class NilveraIncomingAnswerState(StrEnum):
    UNKNOWN = "unknown"
    WAITING = "waitingForApproval"
    APPROVED = "approved"
    REJECTED = "rejected"
    ANSWERED_AUTOMATICALLY = "documentAnsweredAutomatically"


class NilveraIncomingAnswerPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    provider_uuid: uuid.UUID = Field(alias="UUID")
    answer_code: NilveraIncomingAnswerDecision = Field(alias="AnswerCode")
    reject_note: str | None = Field(default=None, alias="RejectNote", max_length=1000)

    @model_validator(mode="after")
    def validate_reject_note(self):
        if self.reject_note is not None:
            self.reject_note = self.reject_note.strip() or None
        if self.answer_code == NilveraIncomingAnswerDecision.REJECTED and self.reject_note is None:
            raise ValueError("RejectNote is required for rejected answers")
        if self.answer_code == NilveraIncomingAnswerDecision.APPROVED and self.reject_note is not None:
            raise ValueError("RejectNote is not allowed for approved answers")
        return self


class NilveraIncomingAnswerService:
    def __init__(self, client: NilveraHttpClient):
        self._client = client
        self._incoming = NilveraIncomingService(client)

    async def send_answer(
        self,
        provider_uuid: str,
        decision: NilveraIncomingAnswerDecision,
        *,
        reject_note: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        try:
            normalized_uuid = uuid.UUID(provider_uuid)
        except (TypeError, ValueError):
            raise NilveraValidationError("Incoming answer has an invalid document UUID") from None

        payload = NilveraIncomingAnswerPayload(
            UUID=normalized_uuid,
            AnswerCode=decision,
            RejectNote=reject_note,
        )
        response = await self._client.post(
            NilveraEndpoints.SEND_ANSWER,
            json=payload.model_dump(mode="json", by_alias=True, exclude_none=True),
            correlation_id=correlation_id,
            retryable=False,
        )
        if response is not None and not isinstance(response, str):
            raise NilveraValidationError("Incoming answer returned an unexpected response type")

    async def fetch_answer_state(self, provider_uuid: str) -> NilveraIncomingAnswerState:
        status = await self._incoming.fetch_incoming_invoice_status(provider_uuid)
        if status.answer_code is None:
            return NilveraIncomingAnswerState.UNKNOWN

        normalized = "".join(character for character in status.answer_code.lower() if character.isalnum())
        mapping = {
            "unknown": NilveraIncomingAnswerState.UNKNOWN,
            "waitingforapproval": NilveraIncomingAnswerState.WAITING,
            "approved": NilveraIncomingAnswerState.APPROVED,
            "rejected": NilveraIncomingAnswerState.REJECTED,
            "documentansweredautomatically": NilveraIncomingAnswerState.ANSWERED_AUTOMATICALLY,
        }
        try:
            return mapping[normalized]
        except KeyError:
            raise NilveraValidationError("Incoming answer status is unsupported") from None
