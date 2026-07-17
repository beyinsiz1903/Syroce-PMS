"""Nilvera status mapping for e-invoices."""

import logging
from enum import StrEnum

logger = logging.getLogger(__name__)


class ProviderInvoiceOutcome(StrEnum):
    """Normalized provider status outcomes."""
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


def map_nilvera_status(raw_status: str | None, raw_code: str | None) -> ProviderInvoiceOutcome:
    """
    Map raw Nilvera status string to ProviderInvoiceOutcome.

    Nilvera V1 E-Invoice Status values (as interpreted):
    - "Kuyrukta", "İşleniyor", "GİB'e Gönderilecek", vb -> PENDING
    - "Başarılı", "Onaylandı" -> ACCEPTED
    - "Hatalı", "Reddedildi" -> REJECTED
    - "İptal Edildi" -> CANCELLED

    Any unrecognized status will be mapped to UNKNOWN to force manual reconciliation.
    """
    if not raw_status:
        return ProviderInvoiceOutcome.UNKNOWN

    status_lower = raw_status.strip().replace("İ", "i").lower()

    pending_statuses = {
        "kuyrukta",
        "işleniyor",
        "isleniyor",
        "i\u0307şleniyor",
        "gib'e gönderilecek",
        "gibe gonderilecek",
        "gönderim bekliyor",
        "gonderim bekliyor",
        "zarflanıyor",
        "zarflaniyor",
        "gib'e gönderildi",
        "gibe gonderildi",
        "alıcıya iletildi",
        "aliciya iletildi",
        "okundu",  # Still pending final acceptance from buyer if ticari
        "waiting",
        "processing",
        "pending",
    }

    accepted_statuses = {
        "başarılı",
        "basarili",
        "başarili",
        "başarilı",
        "onaylandı",
        "onaylandi",
        "kabul edildi",
        "accepted",
        "success",
    }

    rejected_statuses = {
        "hatalı",
        "hatali",
        "reddedildi",
        "red",
        "rejected",
        "failed",
        "error",
    }

    cancelled_statuses = {
        "iptal edildi",
        "i\u0307ptal edildi",
        "iptal",
        "cancelled",
        "canceled",
    }

    if status_lower in accepted_statuses:
        return ProviderInvoiceOutcome.ACCEPTED

    if status_lower in rejected_statuses:
        return ProviderInvoiceOutcome.REJECTED

    if status_lower in pending_statuses:
        return ProviderInvoiceOutcome.PENDING

    if status_lower in cancelled_statuses:
        return ProviderInvoiceOutcome.CANCELLED

    logger.warning(f"Unrecognized Nilvera status received: '{raw_status}' (Code: {raw_code}). Mapping to UNKNOWN.")
    return ProviderInvoiceOutcome.UNKNOWN
