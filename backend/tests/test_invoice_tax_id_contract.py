"""F8 § 98 (Wave 3) — InvoiceCreate VKN/TCKN customer identity contract.

The e-Fatura/e-Arşiv stress spec recorded a REVIEW because InvoiceCreate had
no Turkish tax-identity field. These tests lock the optional, validated
customer_tax_id (VKN=10 / TCKN=11 digits) so the dry-run path can carry a
valid identifier without breaking existing callers.
"""

import pytest
from pydantic import ValidationError

from models.schemas.invoicing import InvoiceCreate
from routers.finance.accounting import (
    AccountingInvoiceCreateRequest,
    _normalize_customer_tax_number,
)


def _base(**extra):
    payload = dict(
        customer_name="Acme A.S.",
        customer_email="billing@acme.test",
        items=[{"description": "Room", "quantity": 1, "unit_price": 100, "total": 100}],
        subtotal=100.0,
        tax=20.0,
        total=120.0,
        due_date="2026-06-30",
    )
    payload.update(extra)
    return payload


def test_tax_id_optional_absent():
    inv = InvoiceCreate(**_base())
    assert inv.customer_tax_id is None


def test_tax_id_vkn_10_digits_ok():
    inv = InvoiceCreate(**_base(customer_tax_id="1234567890"))
    assert inv.customer_tax_id == "1234567890"


def test_tax_id_tckn_11_digits_ok():
    inv = InvoiceCreate(**_base(customer_tax_id="12345678901", customer_tax_office="Kadikoy"))
    assert inv.customer_tax_id == "12345678901"
    assert inv.customer_tax_office == "Kadikoy"


def test_tax_id_blank_normalized_to_none():
    inv = InvoiceCreate(**_base(customer_tax_id="   "))
    assert inv.customer_tax_id is None


@pytest.mark.parametrize("bad", ["123", "123456789", "123456789012", "12345abc90", "ABCDEFGHIJ"])
def test_tax_id_invalid_rejected(bad):
    with pytest.raises(ValidationError):
        InvoiceCreate(**_base(customer_tax_id=bad))


# ── Package C: AccountingInvoiceCreateRequest customer_tax_number parity ──
# The /accounting/invoices manual-create path previously accepted any string
# for customer_tax_number while the InvoiceCreate path validated VKN/TCKN. These
# lock the parity validator (additive, optional, backward-compatible).


def _acc_base(**extra):
    payload = dict(
        invoice_type="standard",
        customer_name="Acme A.S.",
        due_date="2026-06-30",
    )
    payload.update(extra)
    return payload


def test_acc_tax_number_optional_absent():
    req = AccountingInvoiceCreateRequest(**_acc_base())
    assert req.customer_tax_number is None


def test_acc_tax_number_vkn_10_digits_ok():
    req = AccountingInvoiceCreateRequest(**_acc_base(customer_tax_number="1234567890"))
    assert req.customer_tax_number == "1234567890"


def test_acc_tax_number_tckn_11_digits_ok():
    req = AccountingInvoiceCreateRequest(**_acc_base(customer_tax_number="12345678901"))
    assert req.customer_tax_number == "12345678901"


def test_acc_tax_number_blank_normalized_to_none():
    req = AccountingInvoiceCreateRequest(**_acc_base(customer_tax_number="   "))
    assert req.customer_tax_number is None


@pytest.mark.parametrize("bad", ["123", "123456789", "123456789012", "12345abc90", "ABCDEFGHIJ"])
def test_acc_tax_number_invalid_rejected(bad):
    with pytest.raises(ValidationError):
        AccountingInvoiceCreateRequest(**_acc_base(customer_tax_number=bad))


# ── Package C: shared helper used by the raw-dict update path ──
# update_accounting_invoice takes a dict (not a pydantic model), so it calls
# _normalize_customer_tax_number directly. Lock the same contract there.


def test_normalize_helper_none_and_blank():
    assert _normalize_customer_tax_number(None) is None
    assert _normalize_customer_tax_number("   ") is None


@pytest.mark.parametrize("ok", ["1234567890", "12345678901"])
def test_normalize_helper_valid(ok):
    assert _normalize_customer_tax_number(ok) == ok


@pytest.mark.parametrize("bad", ["123", "123456789", "123456789012", "12345abc90", "ABCDEFGHIJ"])
def test_normalize_helper_invalid_raises(bad):
    with pytest.raises(ValueError):
        _normalize_customer_tax_number(bad)
