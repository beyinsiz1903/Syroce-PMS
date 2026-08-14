"""Fail-closed deterministic source lookup for Nilvera CreateReturn Sandbox E2E.

This module intentionally avoids paginated Sale/Purchase list discovery. The
Sandbox fixture UUID is deterministic and was already verified when the source
fixture was created, so CreateReturn preflight can validate that exact UUID via
non-retrying GET-only detail/status calls before any provider mutation.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.integrations.nilvera.config import NilveraEndpoints
from core.integrations.nilvera.incoming import NilveraIncomingService
from core.integrations.nilvera.taxpayer import NilveraTaxpayerService
from tests.nilvera_sandbox_fixture import (
    ANSWER_STATE_APPROVED,
    ANSWER_STATE_AUTOMATIC,
    ReadOnlySandboxClient,
    SandboxFixtureBlocked,
    SandboxFixtureFailed,
    build_fixture_identity,
    build_fixture_request_uuid,
    classify_incoming_answer_state,
    company_identity_matches,
    ensure_distinct_sandbox_keys,
    fixture_correlation_label,
    select_company_owned_alias,
)


@dataclass(frozen=True)
class CreateReturnSourceReadiness:
    correlation_label: str
    source_provider_uuid: str
    sender_match: bool
    receiver_match: bool
    receiver_status_ready: bool
    receiver_alias_match: bool
    receiver_status_answer_state: str
    receiver_detail_answer_state: str

    @property
    def source_terminal(self) -> bool:
        return bool(
            {self.receiver_status_answer_state, self.receiver_detail_answer_state}
            & {ANSWER_STATE_APPROVED, ANSWER_STATE_AUTOMATIC}
        )

    @property
    def ready(self) -> bool:
        return (
            self.sender_match
            and self.receiver_match
            and self.receiver_status_ready
            and self.receiver_alias_match
            and self.source_terminal
        )


def _normalized(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


async def resolve_create_return_source_direct(
    *,
    sender_client: ReadOnlySandboxClient,
    receiver_client: ReadOnlySandboxClient,
    sender_key: str,
    receiver_key: str,
    hmac_key: str,
    run_id: str,
    seller_tax_number: str,
    buyer_tax_number: str,
    reference_time: datetime,
) -> CreateReturnSourceReadiness:
    """Validate the exact deterministic fixture UUID with GET-only calls.

    No list endpoint is used here. All provider calls pass through
    ``ReadOnlySandboxClient``, which forces ``retryable=False`` and blocks every
    non-GET method.
    """
    if reference_time.tzinfo is None or reference_time.utcoffset() is None:
        raise SandboxFixtureBlocked("BLOCKED_RECONCILIATION_REFERENCE_TIME")

    ensure_distinct_sandbox_keys(sender_key, receiver_key)
    sender_match = await company_identity_matches(sender_client, seller_tax_number)
    receiver_match = await company_identity_matches(receiver_client, buyer_tax_number)
    if not sender_match or not receiver_match:
        raise SandboxFixtureBlocked(
            "BLOCKED_SANDBOX_COMPANY_MISMATCH",
            sender_match=sender_match,
            receiver_match=receiver_match,
        )

    identity = build_fixture_identity(year=reference_time.year, run_id=run_id, hmac_key=hmac_key)
    source_provider_uuid = str(build_fixture_request_uuid(identity, hmac_key))
    correlation_label = fixture_correlation_label(identity, hmac_key)

    try:
        sender_detail = await sender_client.get(
            NilveraEndpoints.GET_SALE_INVOICE_DETAIL.format(uuid=source_provider_uuid),
            correlation_id=correlation_label,
        )
    except Exception as exc:
        raise SandboxFixtureBlocked("BLOCKED_CREATE_RETURN_SOURCE_SALE_DIRECT_LOOKUP") from exc

    if (
        not isinstance(sender_detail, dict)
        or _normalized(sender_detail.get("InvoiceProfile")) != "ticarifatura"
        or _normalized(sender_detail.get("InvoiceType")) != "satis"
    ):
        raise SandboxFixtureFailed("FIXTURE_CREATE_RETURN_SOURCE_SALE_MISMATCH")

    incoming_service = NilveraIncomingService(receiver_client)
    try:
        receiver_detail = await incoming_service.fetch_incoming_invoice_detail(source_provider_uuid)
        receiver_status = await incoming_service.fetch_incoming_invoice_status(source_provider_uuid)
    except Exception as exc:
        raise SandboxFixtureBlocked("BLOCKED_CREATE_RETURN_SOURCE_PURCHASE_DIRECT_LOOKUP") from exc

    if (
        str(receiver_detail.provider_uuid) != source_provider_uuid
        or receiver_detail.invoice_profile != "TICARIFATURA"
        or receiver_detail.invoice_type != "SATIS"
    ):
        raise SandboxFixtureFailed("FIXTURE_CREATE_RETURN_SOURCE_PURCHASE_MISMATCH")

    receiver_status_ready = _normalized(receiver_status.status_code) in {"succeed", "success"}
    receiver_status_answer_state = classify_incoming_answer_state(receiver_status.answer_code)
    receiver_detail_answer_state = classify_incoming_answer_state(receiver_detail.answer_code)

    try:
        aliases = await NilveraTaxpayerService(sender_client).get_taxpayer_aliases(
            buyer_tax_number,
            correlation_label,
        )
        buyer_aliases = [alias for alias in aliases.aliases if "pk" in alias.lower()]
        if not buyer_aliases:
            raise SandboxFixtureBlocked("BLOCKED_FIXTURE_BUYER_ALIAS")
        receiver_alias_match = await select_company_owned_alias(receiver_client, buyer_aliases) is not None
    except SandboxFixtureBlocked:
        raise
    except Exception as exc:
        raise SandboxFixtureBlocked("BLOCKED_CREATE_RETURN_SOURCE_ALIAS_LOOKUP") from exc

    return CreateReturnSourceReadiness(
        correlation_label=correlation_label,
        source_provider_uuid=source_provider_uuid,
        sender_match=sender_match,
        receiver_match=receiver_match,
        receiver_status_ready=receiver_status_ready,
        receiver_alias_match=receiver_alias_match,
        receiver_status_answer_state=receiver_status_answer_state,
        receiver_detail_answer_state=receiver_detail_answer_state,
    )
