from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from routers.vcc_router import VCCStore, _mask_card


def test_vcc_normalizes_and_validates_sensitive_fields():
    future_year = (datetime.now(UTC).year + 2) % 100
    card = VCCStore(
        card_holder="  TEST   HOLDER ",
        card_number="4111 1111 1111 1111",
        expiry=f"12/{future_year:02d}",
        cvv="123",
        card_type="virtual",
    )
    assert card.card_holder == "TEST HOLDER"
    assert card.card_number == "4111111111111111"
    assert card.expiry == f"12/{future_year:02d}"
    assert _mask_card(card.card_number) == "411111******1111"


@pytest.mark.parametrize(
    "overrides",
    [
        {"card_number": "4111111111111112"},
        {"expiry": "13/99"},
        {"expiry": "01/20"},
        {"cvv": "12"},
        {"cvv": "ABC"},
        {"card_type": "unknown"},
    ],
)
def test_vcc_rejects_invalid_card_data(overrides):
    payload = {
        "card_holder": "Test Holder",
        "card_number": "4111111111111111",
        "expiry": "12/99",
        "cvv": "123",
        "card_type": "virtual",
    }
    payload.update(overrides)
    with pytest.raises(ValidationError):
        VCCStore(**payload)

