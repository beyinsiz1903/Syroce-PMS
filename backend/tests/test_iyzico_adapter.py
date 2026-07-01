"""Task #312 — Iyzico adaptoru hedefli testleri (DB'siz, sahte SDK).

Kapsam: SDK istek sekillendirme (conversationId/price), basari/red ayristirma,
CardMaterial.clear() garanti, maskeleme/PAN sizinti yoklugu, fail-closed
not_configured. Gercek PSP cagrisi YOK; tam stress YOK (doktrin).
"""
import asyncio
import json

import pytest

import core.payments.providers.iyzico_adapter as adapter_mod
from core.payments import (
    CardMaterial,
    PaymentOperation,
    PaymentRequest,
    PaymentStatus,
    ProviderNotConfigured,
)
from core.payments.providers.iyzico_adapter import (
    IyzicoProvider,
    minor_to_price_str,
    _split_expiry,
)

_PAN = "5528" + "7900" + "0000" + "0008"  # Iyzico sandbox sentinel


# ── Sahte SDK ─────────────────────────────────────────────────────


class _FakeResp:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def _make_op(recorder: dict, key: str, response: dict):
    class _Op:
        def create(self, req, options):
            recorder[key] = req
            recorder["options"] = options
            return _FakeResp(response)

    return _Op


class FakeSDK:
    """iyzipay modulunu taklit eder; son istegi kaydeder."""

    def __init__(self, response: dict | None = None):
        self.recorder: dict = {}
        resp = response or {
            "status": "success",
            "paymentId": "PID123",
            "paymentItems": [{"paymentTransactionId": "TXN1"}],
        }
        self.Payment = _make_op(self.recorder, "payment", resp)
        self.PaymentPreAuth = _make_op(self.recorder, "preauth", resp)
        self.PaymentPostAuth = _make_op(self.recorder, "postauth", resp)
        self.Refund = _make_op(self.recorder, "refund", resp)
        self.Cancel = _make_op(self.recorder, "cancel", resp)
        self.ThreedsInitialize = _make_op(
            self.recorder,
            "threeds",
            {"status": "success", "paymentId": "PID3D", "threeDSHtmlContent": "PEh0bWw+"},
        )


def _provider(sdk: FakeSDK) -> IyzicoProvider:
    return IyzicoProvider(
        sdk=sdk,
        options_provider=lambda: {
            "api_key": "k",
            "secret_key": "s",
            "base_url": "https://sandbox-api.iyzipay.com",
        },
    )


@pytest.fixture(autouse=True)
def _force_configured(monkeypatch):
    # is_configured env'e bagli; testte True'ya sabitle (gercek sir kullanilmaz).
    monkeypatch.setattr(adapter_mod.iyzico, "is_configured", lambda: True)


def _patch_card(monkeypatch, material: CardMaterial):
    async def _fake_resolve(db, *, tenant_id, vault_card_ref):
        return material

    monkeypatch.setattr(adapter_mod, "resolve_card_material", _fake_resolve)


def _charge_req(**over) -> PaymentRequest:
    base = dict(
        operation=PaymentOperation.CHARGE,
        tenant_id="t1",
        currency="TRY",
        idempotency_key="idem-abc",
        amount_minor=15000,
        vault_card_ref="vault_v1:card-1",
        booking_id="bk-1",
        descriptor="Test",
    )
    base.update(over)
    return PaymentRequest(**base)


# ── Yardimcilar ───────────────────────────────────────────────────


def test_minor_to_price_str():
    assert minor_to_price_str(15000) == "150.00"
    assert minor_to_price_str(99) == "0.99"
    assert minor_to_price_str(150) == "1.50"


def test_split_expiry():
    assert _split_expiry("12/26") == ("12", "2026")
    assert _split_expiry("01/2027") == ("01", "2027")
    assert _split_expiry("1226") == ("12", "2026")
    assert _split_expiry(None) == ("", "")


def test_name_and_capabilities():
    p = _provider(FakeSDK())
    assert p.name == "iyzico"
    caps = p.capabilities
    assert caps.supports_charge and caps.supports_refund and caps.supports_void
    assert caps.supports_authorize_capture and caps.supports_3ds


# ── charge ────────────────────────────────────────────────────────


def test_charge_success_masked_and_request_shape(monkeypatch):
    sdk = FakeSDK()
    mat = CardMaterial(pan=_PAN, expiry="12/26", holder="AYSE YILMAZ", cvv="123")
    _patch_card(monkeypatch, mat)
    p = _provider(sdk)

    res = asyncio.run(p.charge(_charge_req()))

    assert res.ok and res.status == PaymentStatus.SUCCEEDED
    assert res.provider_ref == "PID123"
    assert res.provider_txn_ref == "TXN1"
    # Maskeli kart donduruldu; ham PAN sonucta YOK.
    assert res.masked_card and _PAN not in (res.masked_card or "")
    assert res.masked_card.startswith("552879") and res.masked_card.endswith("0008")
    # Istek sekli: conversationId=idempotency_key, price=Decimal string.
    req = sdk.recorder["payment"]
    assert req["conversationId"] == "idem-abc"
    assert req["price"] == "150.00" and req["paidPrice"] == "150.00"
    assert req["currency"] == "TRY"
    assert req["paymentCard"]["cardNumber"] == _PAN
    assert req["paymentCard"]["expireMonth"] == "12"
    assert req["paymentCard"]["expireYear"] == "2026"


def test_charge_clears_card_material(monkeypatch):
    sdk = FakeSDK()
    mat = CardMaterial(pan=_PAN, expiry="12/26", holder="X", cvv="123")
    _patch_card(monkeypatch, mat)
    p = _provider(sdk)

    asyncio.run(p.charge(_charge_req()))
    # try/finally clear() — ham veri cagri sonrasi bellekte tutulmaz.
    assert mat.pan is None and mat.cvv is None and mat.expiry is None


def test_charge_failure_maps_error(monkeypatch):
    sdk = FakeSDK(
        {"status": "failure", "errorCode": "10051", "errorMessage": "Yetersiz bakiye"}
    )
    mat = CardMaterial(pan=_PAN, expiry="12/26", holder="X", cvv="123")
    _patch_card(monkeypatch, mat)
    p = _provider(sdk)

    res = asyncio.run(p.charge(_charge_req()))
    assert not res.ok and res.status == PaymentStatus.FAILED
    assert res.error_code == "10051"
    assert res.error_message == "Yetersiz bakiye"
    assert mat.pan is None  # yine de temizlendi


def test_charge_3ds_requires_action(monkeypatch):
    sdk = FakeSDK()
    mat = CardMaterial(pan=_PAN, expiry="12/26", holder="X", cvv="123")
    _patch_card(monkeypatch, mat)
    p = _provider(sdk)

    res = asyncio.run(p.charge(_charge_req(three_ds_return_url="https://x/callback")))
    assert res.status == PaymentStatus.REQUIRES_ACTION
    assert res.requires_action_url == "PEh0bWw+"
    assert sdk.recorder["threeds"]["callbackUrl"] == "https://x/callback"


# ── refund / void / authorize / capture ───────────────────────────


def test_void_request_shape():
    sdk = FakeSDK()
    p = _provider(sdk)
    req = PaymentRequest(
        operation=PaymentOperation.VOID,
        tenant_id="t1",
        currency="TRY",
        idempotency_key="idem-void",
        reference="PID123",
    )
    res = asyncio.run(p.void(req))
    assert res.ok
    assert sdk.recorder["cancel"]["paymentId"] == "PID123"
    assert sdk.recorder["cancel"]["conversationId"] == "idem-void"


def test_refund_request_shape():
    sdk = FakeSDK()
    p = _provider(sdk)
    req = PaymentRequest(
        operation=PaymentOperation.REFUND,
        tenant_id="t1",
        currency="TRY",
        idempotency_key="idem-ref",
        amount_minor=5000,
        reference="TXN1",
    )
    res = asyncio.run(p.refund(req))
    assert res.ok
    assert sdk.recorder["refund"]["paymentTransactionId"] == "TXN1"
    assert sdk.recorder["refund"]["price"] == "50.00"


def test_authorize_uses_preauth(monkeypatch):
    sdk = FakeSDK()
    mat = CardMaterial(pan=_PAN, expiry="12/26", holder="X", cvv="123")
    _patch_card(monkeypatch, mat)
    p = _provider(sdk)
    res = asyncio.run(p.authorize(_charge_req(operation=PaymentOperation.AUTHORIZE)))
    assert res.ok
    assert "preauth" in sdk.recorder  # PaymentPreAuth kullanildi


def test_capture_uses_postauth():
    sdk = FakeSDK()
    p = _provider(sdk)
    req = PaymentRequest(
        operation=PaymentOperation.CAPTURE,
        tenant_id="t1",
        currency="TRY",
        idempotency_key="idem-cap",
        amount_minor=15000,
        reference="PID123",
    )
    res = asyncio.run(p.capture(req))
    assert res.ok
    assert sdk.recorder["postauth"]["paymentId"] == "PID123"
    assert sdk.recorder["postauth"]["paidPrice"] == "150.00"


# ── fail-closed ───────────────────────────────────────────────────


def test_not_configured_raises(monkeypatch):
    monkeypatch.setattr(adapter_mod.iyzico, "is_configured", lambda: False)
    p = _provider(FakeSDK())
    assert p.is_configured() is False
    with pytest.raises(ProviderNotConfigured):
        asyncio.run(p.charge(_charge_req()))
