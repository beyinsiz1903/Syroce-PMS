"""Task #311 — odeme soyutlamasi sozlesme testleri (DB'siz, hedefli).

Kapsam: DTO fail-closed dogrulama, maskeleme/PAN sizinti yoklugu, capability
tabanli UnsupportedOperation, tenant fail-closed saglayici secimi (sahte db).
Gercek PSP cagrisi YOK; tam stress YOK (doktrin).
"""
import asyncio

import pytest

from core.payments import (
    CardMaterial,
    InvalidPaymentRequest,
    PaymentOperation,
    PaymentProvider,
    PaymentRequest,
    PaymentResult,
    PaymentStatus,
    ProviderCapabilities,
    ProviderNotConfigured,
    UnsupportedOperation,
    available_providers,
    get_provider_for_tenant,
    make_vault_card_ref,
    mask_pan,
    parse_vault_card_ref,
    register_provider,
    unregister_provider,
)

_PAN = "4111" + "1111" + "1111" + "1111"  # Luhn sentinel, source-scan safe


# ── DTO dogrulama (fail-closed) ───────────────────────────────────


def test_charge_request_valid():
    req = PaymentRequest(
        operation=PaymentOperation.CHARGE,
        tenant_id="t1",
        currency="try",
        idempotency_key="idem-1",
        amount_minor=12345,
        vault_card_ref=make_vault_card_ref("card-1"),
    )
    assert req.currency == "TRY"  # normalize edildi
    assert req.amount_minor == 12345


@pytest.mark.parametrize("bad_amount", [0, -5, 12.5, True, None])
def test_charge_amount_must_be_positive_int(bad_amount):
    with pytest.raises(InvalidPaymentRequest):
        PaymentRequest(
            operation=PaymentOperation.CHARGE,
            tenant_id="t1",
            currency="TRY",
            idempotency_key="idem",
            amount_minor=bad_amount,
            vault_card_ref="vault_v1:card-1",
        )


@pytest.mark.parametrize("bad_cur", ["", "T", "TRYX", "12", "T1Y", None])
def test_currency_required_and_iso(bad_cur):
    with pytest.raises(InvalidPaymentRequest):
        PaymentRequest(
            operation=PaymentOperation.CHARGE,
            tenant_id="t1",
            currency=bad_cur,
            idempotency_key="idem",
            amount_minor=100,
            vault_card_ref="vault_v1:card-1",
        )


def test_idempotency_and_tenant_required():
    with pytest.raises(InvalidPaymentRequest):
        PaymentRequest(
            operation=PaymentOperation.CHARGE,
            tenant_id="",
            currency="TRY",
            idempotency_key="idem",
            amount_minor=100,
            vault_card_ref="vault_v1:card-1",
        )
    with pytest.raises(InvalidPaymentRequest):
        PaymentRequest(
            operation=PaymentOperation.CHARGE,
            tenant_id="t1",
            currency="TRY",
            idempotency_key="",
            amount_minor=100,
            vault_card_ref="vault_v1:card-1",
        )


def test_charge_requires_vault_ref():
    with pytest.raises(InvalidPaymentRequest):
        PaymentRequest(
            operation=PaymentOperation.CHARGE,
            tenant_id="t1",
            currency="TRY",
            idempotency_key="idem",
            amount_minor=100,
        )


@pytest.mark.parametrize(
    "op", [PaymentOperation.CAPTURE, PaymentOperation.REFUND, PaymentOperation.VOID]
)
def test_capture_refund_void_require_reference(op):
    with pytest.raises(InvalidPaymentRequest):
        PaymentRequest(
            operation=op,
            tenant_id="t1",
            currency="TRY",
            idempotency_key="idem",
            amount_minor=(None if op == PaymentOperation.VOID else 100),
        )


def test_void_amount_optional():
    req = PaymentRequest(
        operation=PaymentOperation.VOID,
        tenant_id="t1",
        currency="TRY",
        idempotency_key="idem",
        reference="psp-123",
    )
    assert req.amount_minor is None


# ── Maskeleme / PAN sizinti yoklugu ───────────────────────────────


def test_mask_pan():
    masked = mask_pan(_PAN)
    assert masked.startswith("411111")
    assert masked.endswith("1111")
    assert "*" in masked
    assert _PAN not in masked


def test_card_material_repr_does_not_leak_pan():
    cm = CardMaterial(pan=_PAN, expiry="12/30", holder="A B", cvv="123")
    for rendered in (repr(cm), str(cm), f"{cm}"):
        assert _PAN not in rendered
        assert "123" not in rendered  # cvv sizmaz
    assert cm.masked.endswith("1111")


def test_card_material_clear():
    cm = CardMaterial(pan=_PAN, expiry="12/30", cvv="123")
    cm.clear()
    assert cm.pan is None and cm.expiry is None and cm.cvv is None


def test_vault_ref_roundtrip():
    ref = make_vault_card_ref("card-9")
    assert ref == "vault_v1:card-9"
    assert parse_vault_card_ref(ref) == "card-9"
    assert parse_vault_card_ref("card-9") == "card-9"  # prefix'siz tolere


def test_payment_result_has_no_pan_fields():
    res = PaymentResult(
        status=PaymentStatus.SUCCEEDED,
        operation=PaymentOperation.CHARGE,
        provider="fake",
        tenant_id="t1",
        idempotency_key="idem",
        amount_minor=100,
        currency="TRY",
        masked_card=mask_pan(_PAN),
    )
    assert res.ok is True
    blob = repr(res)
    assert _PAN not in blob


# ── Capability tabanli safe-default ───────────────────────────────


class _ChargeOnlyProvider(PaymentProvider):
    @property
    def name(self):
        return "fake_charge_only"

    @property
    def capabilities(self):
        return ProviderCapabilities(supports_charge=True)

    def is_configured(self):
        return True

    async def charge(self, request):
        return PaymentResult(
            status=PaymentStatus.SUCCEEDED,
            operation=PaymentOperation.CHARGE,
            provider=self.name,
            tenant_id=request.tenant_id,
            idempotency_key=request.idempotency_key,
            amount_minor=request.amount_minor,
            currency=request.currency,
        )


def _charge_req():
    return PaymentRequest(
        operation=PaymentOperation.CHARGE,
        tenant_id="t1",
        currency="TRY",
        idempotency_key="idem",
        amount_minor=100,
        vault_card_ref="vault_v1:c1",
    )


def test_supported_op_works():
    prov = _ChargeOnlyProvider()
    res = asyncio.run(prov.charge(_charge_req()))
    assert res.ok


def test_unsupported_ops_raise():
    prov = _ChargeOnlyProvider()
    refund_req = PaymentRequest(
        operation=PaymentOperation.REFUND,
        tenant_id="t1",
        currency="TRY",
        idempotency_key="idem",
        amount_minor=100,
        reference="psp-1",
    )
    with pytest.raises(UnsupportedOperation):
        asyncio.run(prov.refund(refund_req))


# ── Tenant fail-closed saglayici secimi ───────────────────────────


class _FakeSettingsCursor:
    def __init__(self, doc):
        self._doc = doc

    async def find_one(self, query, projection=None):
        return self._doc


class _FakeDB:
    def __init__(self, settings_doc):
        self.tenant_settings = _FakeSettingsCursor(settings_doc)


def _register_fake(name, configured=True):
    class _P(_ChargeOnlyProvider):
        @property
        def name(self):
            return name

        def is_configured(self):
            return configured

    register_provider(name, lambda: _P())
    return name


def test_no_active_provider_fail_closed():
    db = _FakeDB({})  # ayar yok
    with pytest.raises(ProviderNotConfigured):
        asyncio.run(get_provider_for_tenant(db, "t1"))


def test_unknown_provider_fail_closed():
    db = _FakeDB({"active_payment_provider": "nope_unknown"})
    with pytest.raises(ProviderNotConfigured):
        asyncio.run(get_provider_for_tenant(db, "t1"))


def test_unconfigured_provider_fail_closed():
    name = _register_fake("fake_unconfigured_311", configured=False)
    try:
        db = _FakeDB({"active_payment_provider": name})
        with pytest.raises(ProviderNotConfigured):
            asyncio.run(get_provider_for_tenant(db, "t1"))
    finally:
        unregister_provider(name)


def test_happy_path_returns_provider():
    name = _register_fake("fake_ok_311", configured=True)
    try:
        db = _FakeDB({"active_payment_provider": name.upper()})  # case-insensitive
        prov = asyncio.run(get_provider_for_tenant(db, "t1"))
        assert prov.is_configured()
        assert name in available_providers()
    finally:
        unregister_provider(name)


def test_provider_not_configured_maps_to_503():
    err = ProviderNotConfigured("x")
    assert err.error_code == "not_configured"
    assert err.http_status == 503
