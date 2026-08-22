import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil

from core.integrations.incoming_invoice_repository import IncomingInvoiceRepository
from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.document_service import NilveraDocumentService
from core.integrations.nilvera.errors import NilveraValidationError
from core.integrations.nilvera.incoming import NilveraIncomingService
from core.integrations.nilvera.incoming_mapper import (
    IncomingInvoiceDetail,
    IncomingInvoiceStatus,
    IncomingInvoiceSummary,
)
from core.integrations.nilvera.incoming_xml_mapper import (
    IncomingInvoiceXml,
    NilveraIncomingXmlMapper,
)
from core.integrations.nilvera.provisioner import get_nilvera_tenant_config
from models.schemas.incoming_invoice import (
    IncomingInvoice,
    IncomingInvoiceAnswerStatus,
    IncomingInvoiceLine,
    IncomingInvoiceProfile,
    IncomingInvoiceProviderStatus,
)
from models.schemas.invoice_sync import InvoiceProvider

logger = logging.getLogger("core.integrations.incoming_invoice_sync_service")


@dataclass(frozen=True)
class IncomingInvoiceSyncResult:
    invoices_seen: int
    invoices_created: int
    invoices_changed: int
    lines_created: int
    lines_changed: int
    lines_deactivated: int
    unknown_invoices: int
    pending_invoices: int
    provider_error_invoices: int


class IncomingInvoiceSyncService:
    _PAGE_SIZE = 100
    _MAX_PAGES = 1000

    @classmethod
    async def sync_tenant(
        cls,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
        *,
        client: NilveraHttpClient | None = None,
    ) -> IncomingInvoiceSyncResult:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        if client is not None:
            return await cls._sync_with_client(tenant_id, start_date, end_date, client)

        tenant_config = await get_nilvera_tenant_config(tenant_id, decrypt_api_key=True)
        if not tenant_config.get("enabled"):
            raise RuntimeError("NILVERA_TENANT_DISABLED")
        api_key = tenant_config.get("api_key")
        if not isinstance(api_key, str) or not api_key:
            raise RuntimeError("NILVERA_TENANT_CREDENTIAL_UNAVAILABLE")

        async with NilveraHttpClient(api_key=api_key) as owned_client:
            return await cls._sync_with_client(
                tenant_id,
                start_date,
                end_date,
                owned_client,
            )

    @classmethod
    async def _sync_with_client(
        cls,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
        client: NilveraHttpClient,
    ) -> IncomingInvoiceSyncResult:
        incoming_service = NilveraIncomingService(client)
        document_service = NilveraDocumentService(client)
        summaries: list[IncomingInvoiceSummary] = []

        page_number = 1
        expected_total_count: int | None = None
        expected_total_pages: int | None = None
        effective_total_pages: int | None = None
        while True:
            page = await incoming_service.fetch_incoming_invoices(
                start_date,
                end_date,
                page=page_number,
                page_size=cls._PAGE_SIZE,
            )
            if page.total_pages > cls._MAX_PAGES:
                raise NilveraValidationError("Incoming invoice pagination exceeds the safety limit")
            if expected_total_count is None:
                expected_total_count = page.total_count
                expected_total_pages = page.total_pages
                if expected_total_pages > 0:
                    effective_total_pages = expected_total_pages
                elif expected_total_count > 0:
                    effective_total_pages = ceil(expected_total_count / cls._PAGE_SIZE)
                if effective_total_pages is not None and effective_total_pages > cls._MAX_PAGES:
                    raise NilveraValidationError("Incoming invoice pagination exceeds the safety limit")
            elif page.total_count != expected_total_count or page.total_pages != expected_total_pages:
                raise NilveraValidationError("Incoming invoice pagination metadata changed during sync")
            summaries.extend(page.items)

            if effective_total_pages is not None:
                if page_number >= effective_total_pages:
                    break
                if not page.items:
                    raise NilveraValidationError("Incoming invoice pagination ended before the final page")
            elif len(page.items) < cls._PAGE_SIZE:
                break
            if page_number >= cls._MAX_PAGES:
                raise NilveraValidationError("Incoming invoice pagination exceeds the safety limit")
            page_number += 1

        if expected_total_count is not None and expected_total_count > 0 and len(summaries) != expected_total_count:
            raise NilveraValidationError("Incoming invoice pagination item count is inconsistent")
        if len({summary.provider_uuid for summary in summaries}) != len(summaries):
            raise NilveraValidationError("Incoming invoice pagination contains duplicate identities")

        snapshots: list[tuple[IncomingInvoice, tuple[IncomingInvoiceLine, ...]]] = []
        for summary in summaries:
            detail = await incoming_service.fetch_incoming_invoice_detail(summary.provider_uuid)
            status = await incoming_service.fetch_incoming_invoice_status(summary.provider_uuid)
            xml_content = await document_service.download_purchase_xml(summary.provider_uuid)
            xml_invoice = NilveraIncomingXmlMapper.map_document(xml_content)

            snapshots.append(
                cls._build_snapshot(
                    tenant_id,
                    summary,
                    detail,
                    status,
                    xml_invoice,
                )
            )

        created = changed = 0
        lines_created = lines_changed = lines_deactivated = 0
        unknown = pending = provider_errors = 0
        for invoice, lines in snapshots:
            upsert = await IncomingInvoiceRepository.upsert_snapshot(invoice, lines)
            created += int(upsert.created)
            changed += int(upsert.changed)
            lines_created += upsert.lines_created
            lines_changed += upsert.lines_changed
            lines_deactivated += upsert.lines_deactivated
            unknown += int(invoice.provider_status == IncomingInvoiceProviderStatus.UNKNOWN)
            pending += int(invoice.provider_status == IncomingInvoiceProviderStatus.WAITING)
            provider_errors += int(invoice.provider_status == IncomingInvoiceProviderStatus.ERROR)
            try:
                from core.integrations.nilvera_gl_automation import handle_incoming_invoice_synced

                await handle_incoming_invoice_synced(tenant_id, invoice.id)
            except Exception as exc:
                # Provider read/snapshot persistence must not be rolled back by
                # a closed GL period or an incomplete account mapping.  The GL
                # automation layer persists its own blocked review item.
                logger.warning(
                    "Incoming invoice GL candidate registration failed tenant=%s invoice=%s error_type=%s",
                    tenant_id,
                    invoice.id,
                    type(exc).__name__,
                )

        return IncomingInvoiceSyncResult(
            invoices_seen=len(summaries),
            invoices_created=created,
            invoices_changed=changed,
            lines_created=lines_created,
            lines_changed=lines_changed,
            lines_deactivated=lines_deactivated,
            unknown_invoices=unknown,
            pending_invoices=pending,
            provider_error_invoices=provider_errors,
        )

    @classmethod
    def _build_snapshot(
        cls,
        tenant_id: str,
        summary: IncomingInvoiceSummary,
        detail: IncomingInvoiceDetail,
        status: IncomingInvoiceStatus,
        xml_invoice: IncomingInvoiceXml,
    ) -> tuple[IncomingInvoice, tuple[IncomingInvoiceLine, ...]]:
        cls._validate_consistency(summary, detail, status, xml_invoice)
        now = datetime.now(UTC)
        invoice_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"syroce:nilvera:incoming:{tenant_id}:{summary.provider_uuid}",
            )
        )
        provider_status = cls._map_provider_status(status.status_code)
        invoice = IncomingInvoice(
            id=invoice_id,
            tenant_id=tenant_id,
            provider=InvoiceProvider.NILVERA,
            provider_uuid=summary.provider_uuid,
            invoice_number=detail.invoice_number,
            sender_vkn_tckn=xml_invoice.supplier_tax_number,
            sender_title=xml_invoice.supplier_name,
            profile=IncomingInvoiceProfile(detail.invoice_profile),
            answer_status=cls._map_answer_status(status.answer_code),
            provider_status=provider_status,
            provider_gib_code=status.gib_code,
            issue_date=detail.issue_date,
            issue_date_timezone_assumed=detail.issue_date_timezone_assumed,
            received_at=now,
            payable_amount=summary.payable_amount,
            currency=detail.currency,
            exchange_rate=xml_invoice.exchange_rate,
            created_at=now,
            updated_at=now,
        )

        lines = tuple(
            IncomingInvoiceLine(
                id=str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"syroce:nilvera:incoming-line:{invoice_id}:{xml_line.line_number}",
                    )
                ),
                tenant_id=tenant_id,
                incoming_invoice_id=invoice_id,
                provider_line_id=xml_line.provider_line_id,
                line_number=xml_line.line_number,
                name=xml_line.name,
                quantity=xml_line.quantity,
                unit_code=xml_line.unit_code,
                unit_price=xml_line.unit_price,
                discount_amount=xml_line.discount_amount,
                line_extension_amount=xml_line.line_extension_amount,
                kdv_rate=xml_line.kdv_rate,
                kdv_amount=xml_line.kdv_amount,
                other_taxes=list(xml_line.other_taxes),
                currency=xml_line.currency,
                active=True,
                created_at=now,
                updated_at=now,
            )
            for xml_line in xml_invoice.lines
        )
        return invoice, lines

    @staticmethod
    def _validate_consistency(
        summary: IncomingInvoiceSummary,
        detail: IncomingInvoiceDetail,
        status: IncomingInvoiceStatus,
        xml_invoice: IncomingInvoiceXml,
    ) -> None:
        if not (summary.provider_uuid == detail.provider_uuid == xml_invoice.provider_uuid):
            raise NilveraValidationError("Incoming invoice sources have different identities")
        if not (summary.invoice_number == detail.invoice_number == xml_invoice.invoice_number):
            raise NilveraValidationError("Incoming invoice sources have different invoice numbers")
        if detail.invoice_profile != status.invoice_profile:
            raise NilveraValidationError("Incoming invoice sources have different profiles")
        try:
            IncomingInvoiceProfile(detail.invoice_profile)
        except ValueError:
            raise NilveraValidationError("Incoming invoice has an unsupported profile") from None
        if summary.currency != detail.currency:
            raise NilveraValidationError("Incoming invoice sources have different currencies")
        if any(line.currency != detail.currency for line in xml_invoice.lines):
            raise NilveraValidationError("Incoming invoice line currency does not match the invoice")
        if xml_invoice.exchange_rate is not None:
            if xml_invoice.exchange_rate_source_currency != detail.currency:
                raise NilveraValidationError("Incoming invoice exchange-rate source currency does not match the invoice")
            if xml_invoice.exchange_rate_target_currency not in {"TRY", "TRL"}:
                raise NilveraValidationError("Incoming invoice exchange-rate target currency must be TRY")
        if detail.number_of_items != len(xml_invoice.lines):
            raise NilveraValidationError("Incoming invoice line count does not match the detail")

    @staticmethod
    def _map_answer_status(answer_code: str | None) -> IncomingInvoiceAnswerStatus:
        if answer_code is None:
            return IncomingInvoiceAnswerStatus.PENDING
        normalized = "".join(character for character in answer_code.lower() if character.isalnum())
        mapping = {
            "unknown": IncomingInvoiceAnswerStatus.UNKNOWN,
            "waitingforapproval": IncomingInvoiceAnswerStatus.PENDING,
            "approved": IncomingInvoiceAnswerStatus.APPROVED,
            "rejected": IncomingInvoiceAnswerStatus.REJECTED,
            "documentansweredautomatically": IncomingInvoiceAnswerStatus.ANSWERED_AUTOMATICALLY,
        }
        try:
            return mapping[normalized]
        except KeyError:
            raise NilveraValidationError("Incoming invoice has an unsupported answer code") from None

    @staticmethod
    def _map_provider_status(status_code: str) -> IncomingInvoiceProviderStatus:
        normalized = "".join(character for character in status_code.upper() if character.isalnum())
        mapping = {
            "UNKNOWN": IncomingInvoiceProviderStatus.UNKNOWN,
            "WAITING": IncomingInvoiceProviderStatus.WAITING,
            "PENDING": IncomingInvoiceProviderStatus.WAITING,
            "SUCCEED": IncomingInvoiceProviderStatus.SUCCEED,
            "SUCCESS": IncomingInvoiceProviderStatus.SUCCEED,
            "ERROR": IncomingInvoiceProviderStatus.ERROR,
        }
        try:
            return mapping[normalized]
        except KeyError:
            raise NilveraValidationError("Incoming invoice has an unsupported provider status") from None
