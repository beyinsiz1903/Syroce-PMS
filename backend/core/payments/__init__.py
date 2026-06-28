"""Saglayici-bagimsiz odeme katmani (port + DTO + kasa + secim).

Cekirdek kod somut bir PSP'ye dogrudan baglanmaz; bu paket ortak arayuzu,
kanonik DTO'lari, kart kasasi soyutlamasini ve tenant bazli fail-closed
saglayici secimini sunar. Somut adaptorler (Iyzico/Stripe/...) ayri
gorevlerde register_provider ile baglanir.
"""

from .contracts import (
    InvalidPaymentRequest,
    PaymentError,
    PaymentOperation,
    PaymentProvider,
    PaymentRequest,
    PaymentResult,
    PaymentStatus,
    ProviderCapabilities,
    ProviderNotConfigured,
    UnsupportedOperation,
)
from .registry import (
    available_providers,
    get_active_provider_name,
    get_provider_for_tenant,
    register_provider,
    unregister_provider,
)
from .vault import (
    CardMaterial,
    VaultCardNotFound,
    make_vault_card_ref,
    mask_pan,
    parse_vault_card_ref,
    resolve_card_material,
)

__all__ = [
    "InvalidPaymentRequest",
    "PaymentError",
    "PaymentOperation",
    "PaymentProvider",
    "PaymentRequest",
    "PaymentResult",
    "PaymentStatus",
    "ProviderCapabilities",
    "ProviderNotConfigured",
    "UnsupportedOperation",
    "available_providers",
    "get_active_provider_name",
    "get_provider_for_tenant",
    "register_provider",
    "unregister_provider",
    "CardMaterial",
    "VaultCardNotFound",
    "make_vault_card_ref",
    "mask_pan",
    "parse_vault_card_ref",
    "resolve_card_material",
]
