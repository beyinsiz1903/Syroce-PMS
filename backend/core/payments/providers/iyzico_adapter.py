"""Iyzico tahsilat adaptoru — PaymentProvider arayuzunu uygular.

TR yerel acquiring + TL settlement. Cekirdek kod bu adaptoru DOGRUDAN bilmez;
yalnizca registry uzerinden tenant'in aktif saglayicisi olarak secilir.

Para/PCI doktrini:
- Tutarlar kanonik DTO'da kurus-tam (int); Iyzico'nun bekledigi ondalik string'e
  Decimal ile cevrilir (float aritmetigi YOK).
- Ham PAN/CVV YALNIZCA `resolve_card_material` ile adapter sinirinda cozulur ve
  try/finally icinde `clear()` edilir; sonuc yalnizca maskeli kart tasir.
- PAN/CVV/secret/istek govdesi ASLA loglanmaz.
- idempotency_key -> Iyzico conversationId (PSP tarafinda da idempotent eslesme).

Gercek PSP cagrisi env kimlik bilgisi (IYZICO_API_KEY/SECRET_KEY) ister; yoksa
`is_configured()` False ve her islem ProviderNotConfigured (503) atar (fail-closed).
SDK testlerde enjekte edilebilir (`IyzicoProvider(sdk=...)`).
"""
from __future__ import annotations

import asyncio
import json
import logging
from decimal import ROUND_HALF_UP, Decimal

from core import iyzico
from core.database import db

from ..contracts import (
    PaymentError,
    PaymentOperation,
    PaymentProvider,
    PaymentRequest,
    PaymentResult,
    PaymentStatus,
    ProviderCapabilities,
    ProviderNotConfigured,
)
from ..registry import register_provider
from ..vault import CardMaterial, resolve_card_material

logger = logging.getLogger(__name__)

PROVIDER_NAME = "iyzico"


class ProviderCallError(PaymentError):
    """PSP cagrisi belirsiz/agir hatayla sonuclandi (durum bilinmiyor).

    Tahsilat sonucu KESIN degildir (cift-charge riski) -> cagiran intent'i
    'unknown' birakip mutabakata (reconcile) erteler; kilit serbest birakilmaz.
    """

    error_code = "provider_call_error"
    http_status = 502


def minor_to_price_str(amount_minor: int) -> str:
    """Kurus-tam integer'i Iyzico'nun bekledigi ondalik string'e cevir.

    Decimal ile; float aritmetigi yok. 150 -> '1.50', 99 -> '0.99'.
    """
    value = (Decimal(int(amount_minor)) / Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return str(value)


def _split_expiry(expiry: str | None) -> tuple[str, str]:
    """'MM/YY' | 'MM/YYYY' | 'MMYY' | 'MMYYYY' -> (ay 2hane, yil 4hane)."""
    if not expiry:
        return "", ""
    e = str(expiry).strip().replace(" ", "")
    if "/" in e:
        month, _, year = e.partition("/")
    elif len(e) in (4, 6):
        month, year = e[:2], e[2:]
    else:
        month, year = e, ""
    month = month.zfill(2)
    if len(year) == 2:
        year = "20" + year
    return month, year


class IyzicoProvider(PaymentProvider):
    def __init__(self, sdk=None, options_provider=None):
        self._sdk = sdk
        self._options_provider = options_provider or iyzico.get_options

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_authorize_capture=True,
            supports_charge=True,
            supports_refund=True,
            supports_void=True,
            supports_3ds=True,
            supports_moto=True,
            supports_vcc=True,
            supports_partial_refund=True,
        )

    def is_configured(self) -> bool:
        return iyzico.is_configured()

    # ── ic yardimcilar ────────────────────────────────────────────

    def _sdk_module(self):
        if self._sdk is not None:
            return self._sdk
        import iyzipay  # type: ignore

        return iyzipay

    def _options(self) -> dict:
        return self._options_provider()

    def _require_configured(self) -> None:
        if not self.is_configured():
            raise ProviderNotConfigured("iyzico yapilandirilmamis")

    @staticmethod
    def _read_body(resp) -> dict:
        """SDK yanitini dict'e cevir (read().decode() -> json | dict)."""
        if isinstance(resp, dict):
            return resp
        body = resp.read()
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        if isinstance(body, str):
            return json.loads(body or "{}")
        return {}

    async def _call(self, op_factory, request_payload: dict) -> dict:
        """SDK cagrisini thread'de calistir (bloklayan HTTP event loop'u kilitlemesin).

        İstek govdesi (kart icerebilir) ASLA loglanmaz. Beklenmeyen hata ->
        ProviderCallError (durum belirsiz, mutabakata birak).
        """
        options = self._options()

        def _do():
            instance = op_factory()
            resp = instance.create(request_payload, options)
            return self._read_body(resp)

        try:
            return await asyncio.to_thread(_do)
        except Exception as exc:  # noqa: BLE001
            logger.error("iyzico cagrisi basarisiz: %s", type(exc).__name__)
            raise ProviderCallError("iyzico cagrisi basarisiz") from exc

    def _build_card(self, request: PaymentRequest, material: CardMaterial) -> dict:
        month, year = _split_expiry(material.expiry)
        holder = (
            material.holder
            or request.metadata.get("buyer_name")
            or "CARD HOLDER"
        )
        card: dict = {
            "cardHolderName": holder,
            "cardNumber": material.pan,
            "expireMonth": month,
            "expireYear": year,
            "registerCard": "0",
        }
        if material.cvv:
            card["cvc"] = material.cvv
        return card

    def _build_buyer_and_address(self, request: PaymentRequest) -> tuple[dict, dict]:
        md = request.metadata or {}
        buyer_id = str(md.get("buyer_id") or request.booking_id or request.tenant_id)
        name = md.get("buyer_name") or "Misafir"
        surname = md.get("buyer_surname") or "Misafir"
        ip = md.get("buyer_ip") or "127.0.0.1"
        email = md.get("buyer_email") or "noreply@example.com"
        city = md.get("city") or "Istanbul"
        country = md.get("country") or "Turkey"
        addr_line = md.get("address") or "N/A"
        buyer = {
            "id": buyer_id,
            "name": name,
            "surname": surname,
            "identityNumber": md.get("identity_number") or "11111111111",
            "email": email,
            "registrationAddress": addr_line,
            "city": city,
            "country": country,
            "ip": ip,
        }
        address = {
            "contactName": f"{name} {surname}".strip(),
            "city": city,
            "country": country,
            "address": addr_line,
        }
        return buyer, address

    def _basket_items(self, request: PaymentRequest, price: str) -> list[dict]:
        return [
            {
                "id": request.booking_id or request.idempotency_key,
                "name": request.descriptor or "Konaklama",
                "category1": "Accommodation",
                "itemType": "VIRTUAL",
                "price": price,
            }
        ]

    def _build_payment_payload(
        self, request: PaymentRequest, material: CardMaterial
    ) -> dict:
        price = minor_to_price_str(request.amount_minor)
        buyer, address = self._build_buyer_and_address(request)
        payload = {
            "locale": "tr",
            "conversationId": request.idempotency_key,
            "price": price,
            "paidPrice": price,
            "currency": request.currency,
            "installment": "1",
            "basketId": request.booking_id or request.idempotency_key,
            "paymentChannel": "WEB",
            "paymentGroup": "PRODUCT",
            "paymentCard": self._build_card(request, material),
            "buyer": buyer,
            "shippingAddress": address,
            "billingAddress": address,
            "basketItems": self._basket_items(request, price),
        }
        return payload

    def _parse_charge_result(
        self,
        request: PaymentRequest,
        body: dict,
        operation: PaymentOperation,
        masked_card: str | None,
        *,
        action_field: str | None = None,
    ) -> PaymentResult:
        status_raw = str(body.get("status") or "")
        common = {
            "operation": operation,
            "provider": PROVIDER_NAME,
            "tenant_id": request.tenant_id,
            "idempotency_key": request.idempotency_key,
            "amount_minor": request.amount_minor,
            "currency": request.currency,
            "masked_card": masked_card,
            "raw_provider_status": status_raw,
        }
        if status_raw == "success":
            if action_field and body.get(action_field):
                return PaymentResult(
                    status=PaymentStatus.REQUIRES_ACTION,
                    provider_ref=str(body.get("paymentId") or "") or None,
                    requires_action_url=str(body.get(action_field)),
                    **common,
                )
            txn_ref = None
            items = body.get("paymentItems") or []
            if items and isinstance(items, list):
                txn_ref = str(items[0].get("paymentTransactionId") or "") or None
            return PaymentResult(
                status=PaymentStatus.SUCCEEDED,
                provider_ref=str(body.get("paymentId") or "") or None,
                provider_txn_ref=txn_ref,
                **common,
            )
        return PaymentResult(
            status=PaymentStatus.FAILED,
            error_code=str(body.get("errorCode") or "") or None,
            error_message=str(body.get("errorMessage") or "") or None,
            **common,
        )

    def _parse_refund_void_result(
        self, request: PaymentRequest, body: dict, operation: PaymentOperation
    ) -> PaymentResult:
        status_raw = str(body.get("status") or "")
        common = {
            "operation": operation,
            "provider": PROVIDER_NAME,
            "tenant_id": request.tenant_id,
            "idempotency_key": request.idempotency_key,
            "amount_minor": request.amount_minor,
            "currency": request.currency,
            "raw_provider_status": status_raw,
        }
        if status_raw == "success":
            return PaymentResult(
                status=PaymentStatus.SUCCEEDED,
                provider_ref=str(body.get("paymentId") or "") or None,
                provider_txn_ref=str(body.get("paymentTransactionId") or "") or None,
                **common,
            )
        return PaymentResult(
            status=PaymentStatus.FAILED,
            error_code=str(body.get("errorCode") or "") or None,
            error_message=str(body.get("errorMessage") or "") or None,
            **common,
        )

    async def _charge_like(
        self, request: PaymentRequest, operation: PaymentOperation
    ) -> PaymentResult:
        self._require_configured()
        material = await resolve_card_material(
            db, tenant_id=request.tenant_id, vault_card_ref=request.vault_card_ref
        )
        masked = material.masked
        try:
            payload = self._build_payment_payload(request, material)
            sdk = self._sdk_module()
            if request.three_ds_return_url:
                payload["callbackUrl"] = request.three_ds_return_url
                body = await self._call(sdk.ThreedsInitialize, payload)
                return self._parse_charge_result(
                    request, body, operation, masked,
                    action_field="threeDSHtmlContent",
                )
            op_factory = (
                sdk.PaymentPreAuth
                if operation == PaymentOperation.AUTHORIZE
                else sdk.Payment
            )
            body = await self._call(op_factory, payload)
            return self._parse_charge_result(request, body, operation, masked)
        finally:
            material.clear()

    # ── arayuz islemleri ──────────────────────────────────────────

    async def charge(self, request: PaymentRequest) -> PaymentResult:
        return await self._charge_like(request, PaymentOperation.CHARGE)

    async def authorize(self, request: PaymentRequest) -> PaymentResult:
        return await self._charge_like(request, PaymentOperation.AUTHORIZE)

    async def capture(self, request: PaymentRequest) -> PaymentResult:
        self._require_configured()
        sdk = self._sdk_module()
        payload = {
            "locale": "tr",
            "conversationId": request.idempotency_key,
            "paymentId": request.reference,
            "paidPrice": minor_to_price_str(request.amount_minor),
            "currency": request.currency,
        }
        body = await self._call(sdk.PaymentPostAuth, payload)
        return self._parse_charge_result(
            request, body, PaymentOperation.CAPTURE, None
        )

    async def refund(self, request: PaymentRequest) -> PaymentResult:
        self._require_configured()
        sdk = self._sdk_module()
        payload = {
            "locale": "tr",
            "conversationId": request.idempotency_key,
            "paymentTransactionId": request.reference,
            "price": minor_to_price_str(request.amount_minor),
            "currency": request.currency,
            "ip": (request.metadata or {}).get("buyer_ip") or "127.0.0.1",
        }
        body = await self._call(sdk.Refund, payload)
        return self._parse_refund_void_result(
            request, body, PaymentOperation.REFUND
        )

    async def void(self, request: PaymentRequest) -> PaymentResult:
        self._require_configured()
        sdk = self._sdk_module()
        payload = {
            "locale": "tr",
            "conversationId": request.idempotency_key,
            "paymentId": request.reference,
            "ip": (request.metadata or {}).get("buyer_ip") or "127.0.0.1",
        }
        body = await self._call(sdk.Cancel, payload)
        return self._parse_refund_void_result(
            request, body, PaymentOperation.VOID
        )


# Import-time kayit: tenant ayari 'iyzico' ise registry bu fabrikayi kullanir.
register_provider(PROVIDER_NAME, lambda: IyzicoProvider())
