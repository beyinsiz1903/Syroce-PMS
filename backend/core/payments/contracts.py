"""Saglayici-bagimsiz odeme sozlesmeleri (port + kanonik DTO'lar).

Cekirdek finans/folio kodu hicbir odeme kurulusuna (PSP) dogrudan baglanmaz.
Bu modul ortak `PaymentProvider` arayuzunu (port) ve kanonik istek/sonuc
DTO'larini tanimlar. Iyzico/Stripe/Param gibi somut adaptorler ayri
gorevlerde bu sozlesmeyi uygular (Interface-First, Zero Bloat).

Para guvenligi doktrini:
- Tutarlar daima kurus-tam (minor units) integer; float YOK.
- Sonuc nesneleri yalnizca maskeli kart bilgisi tasir; ham PAN/CVV ASLA bulunmaz.
- Idempotency_key her mutasyonlu islemde zorunlu.
- Yetkilendirme/tenant kapsami daima sunucu tarafi kimlikten gelir.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

# ── Hatalar ───────────────────────────────────────────────────────


class PaymentError(Exception):
    """Tum odeme katmani hatalarinin tabani."""

    error_code: str = "payment_error"
    http_status: int = 500


class ProviderNotConfigured(PaymentError):
    """Tenant icin aktif/yapilandirilmis bir saglayici yok — fail-closed.

    Router katmani bunu 503 not_configured'a esler; islem sessizce gecmez.
    """

    error_code = "not_configured"
    http_status = 503


class UnsupportedOperation(PaymentError):
    """Secili saglayici bu islemi (or. 3DS, partial refund) desteklemiyor."""

    error_code = "unsupported_operation"
    http_status = 422


class InvalidPaymentRequest(PaymentError, ValueError):
    """Kanonik istek DTO dogrulamasi basarisiz (fail-closed)."""

    error_code = "invalid_request"
    http_status = 400


# ── Enumlar ───────────────────────────────────────────────────────


class PaymentOperation(str, Enum):
    AUTHORIZE = "authorize"
    CAPTURE = "capture"
    CHARGE = "charge"
    REFUND = "refund"
    VOID = "void"


class PaymentStatus(str, Enum):
    SUCCEEDED = "succeeded"
    PENDING = "pending"
    REQUIRES_ACTION = "requires_action"  # 3DS yonlendirmesi gerekli
    FAILED = "failed"


# ── Yetenek bayraklari ────────────────────────────────────────────


@dataclass(frozen=True)
class ProviderCapabilities:
    """Adaptorun hangi islemleri/ozellikleri destekledigini bildirir."""

    supports_authorize_capture: bool = False
    supports_charge: bool = False
    supports_refund: bool = False
    supports_void: bool = False
    supports_3ds: bool = False
    supports_moto: bool = False
    supports_vcc: bool = False
    supports_partial_refund: bool = False


# ── DTO yardimcilari ──────────────────────────────────────────────


def _validate_currency(currency: str) -> str:
    if not currency or not isinstance(currency, str):
        raise InvalidPaymentRequest("currency zorunlu")
    cur = currency.strip().upper()
    if len(cur) != 3 or not cur.isalpha():
        raise InvalidPaymentRequest(f"gecersiz currency: {currency!r}")
    return cur


def _validate_amount(amount_minor: int | None, *, required: bool) -> int | None:
    if amount_minor is None:
        if required:
            raise InvalidPaymentRequest("amount_minor zorunlu")
        return None
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int):
        raise InvalidPaymentRequest("amount_minor kurus-tam integer olmali")
    if amount_minor <= 0:
        raise InvalidPaymentRequest("amount_minor pozitif olmali")
    return amount_minor


# ── Kanonik istek/sonuc DTO'lari ──────────────────────────────────


@dataclass(frozen=True)
class PaymentRequest:
    """Saglayici-bagimsiz kanonik odeme istegi.

    - amount_minor: kurus-tam integer (VOID icin opsiyonel/None).
    - currency: ISO 4217 (3 harf) zorunlu.
    - idempotency_key: ayni istegin tekrari icin tekillik anahtari.
    - vault_card_ref: kart kasasi referansi (CHARGE/AUTHORIZE icin zorunlu);
      ham PAN ASLA bu DTO'da tasinmaz.
    - reference: onceki PSP islem referansi (CAPTURE/REFUND/VOID icin zorunlu).
    """

    operation: PaymentOperation
    tenant_id: str
    currency: str
    idempotency_key: str
    amount_minor: int | None = None
    vault_card_ref: str | None = None
    booking_id: str | None = None
    reference: str | None = None
    descriptor: str | None = None
    three_ds_return_url: str | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.tenant_id:
            raise InvalidPaymentRequest("tenant_id zorunlu")
        if not self.idempotency_key:
            raise InvalidPaymentRequest("idempotency_key zorunlu")
        object.__setattr__(self, "currency", _validate_currency(self.currency))

        op = self.operation
        amount_required = op != PaymentOperation.VOID
        validated = _validate_amount(self.amount_minor, required=amount_required)
        object.__setattr__(self, "amount_minor", validated)

        if op in (PaymentOperation.CHARGE, PaymentOperation.AUTHORIZE):
            if not self.vault_card_ref:
                raise InvalidPaymentRequest(
                    f"{op.value} icin vault_card_ref zorunlu"
                )
        if op in (
            PaymentOperation.CAPTURE,
            PaymentOperation.REFUND,
            PaymentOperation.VOID,
        ):
            if not self.reference:
                raise InvalidPaymentRequest(f"{op.value} icin reference zorunlu")


@dataclass(frozen=True)
class PaymentResult:
    """Saglayici-bagimsiz kanonik odeme sonucu.

    Yalnizca maskeli kart bilgisi tasir; ham PAN/CVV ASLA bulunmaz.
    """

    status: PaymentStatus
    operation: PaymentOperation
    provider: str
    tenant_id: str
    idempotency_key: str
    amount_minor: int | None = None
    currency: str | None = None
    provider_ref: str | None = None
    masked_card: str | None = None
    requires_action_url: str | None = None
    raw_provider_status: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def ok(self) -> bool:
        return self.status == PaymentStatus.SUCCEEDED


# ── Saglayici arayuzu (port) ──────────────────────────────────────


class PaymentProvider(abc.ABC):
    """Tum odeme adaptorlerinin uyacagi soyut arayuz.

    Islem metodlari guvenli-varsayilan olarak UnsupportedOperation atar;
    adaptor yalnizca destekledigi islemleri override eder ve `capabilities`
    bayraklarini buna gore bildirir.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Saglayici kanonik adi (or. 'iyzico')."""

    @property
    @abc.abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Desteklenen islem/ozellik bayraklari."""

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """Saglayicinin canli calismaya hazir olup olmadigi (env/sir mevcut)."""

    async def authorize(self, request: PaymentRequest) -> PaymentResult:
        raise UnsupportedOperation(f"{self.name} authorize desteklemiyor")

    async def capture(self, request: PaymentRequest) -> PaymentResult:
        raise UnsupportedOperation(f"{self.name} capture desteklemiyor")

    async def charge(self, request: PaymentRequest) -> PaymentResult:
        raise UnsupportedOperation(f"{self.name} charge desteklemiyor")

    async def refund(self, request: PaymentRequest) -> PaymentResult:
        raise UnsupportedOperation(f"{self.name} refund desteklemiyor")

    async def void(self, request: PaymentRequest) -> PaymentResult:
        raise UnsupportedOperation(f"{self.name} void desteklemiyor")
