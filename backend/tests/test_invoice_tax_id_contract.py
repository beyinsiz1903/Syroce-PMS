"""F8 § 98 (Wave 3) — InvoiceCreate VKN/TCKN customer identity contract.

The e-Fatura/e-Arşiv stress spec recorded a REVIEW because InvoiceCreate had
no Turkish tax-identity field. These tests lock the optional, validated
customer_tax_id (VKN=10 / TCKN=11 digits) so the dry-run path can carry a
valid identifier without breaking existing callers.
"""

import pytest
from pydantic import ValidationError

from models.schemas.invoicing import InvoiceCreate


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
