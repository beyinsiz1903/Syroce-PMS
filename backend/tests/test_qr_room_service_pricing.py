from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from domains.guest.qr_request_description import compute_payload_fingerprint
from domains.guest.qr_submission_service import _room_charge_for_item
from models.schemas.qr_catalogue import GuestServiceItem
from models.schemas.qr_catalogue_submission import StructuredRequestSubmit


def _item(**overrides):
    data = {
        "tenant_id": "tenant-a",
        "property_id": "property-a",
        "service_code": "fnb.club_sandwich",
        "department_code": "fnb",
        "labels": {"tr": "Kulüp sandviç", "en": "Club sandwich"},
        "icon": "utensils",
        "input_type": "quantity",
        "input_config": {"min": 1, "max": 5, "default": 1},
        "is_chargeable": True,
        "room_charge_enabled": True,
        "unit_price_minor": 15074,
        "currency": "try",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    data.update(overrides)
    return GuestServiceItem.model_validate(data)


def test_room_service_price_uses_integer_minor_units_and_server_quantity():
    charge = _room_charge_for_item(_item().model_dump(), {"quantity": 3})
    assert charge == {
        "unit_price_minor": 15074,
        "quantity": 3,
        "total_minor": 45222,
        "currency": "TRY",
        "folio_category": "room_service",
    }


def test_room_charge_configuration_must_be_complete():
    with pytest.raises(ValueError, match="positive unit_price_minor"):
        _item(unit_price_minor=0)
    with pytest.raises(ValueError, match="requires is_chargeable"):
        _item(is_chargeable=False)


def test_room_charge_rejects_invalid_catalogue_snapshot():
    with pytest.raises(HTTPException) as exc:
        _room_charge_for_item({"room_charge_enabled": True, "unit_price_minor": 0}, {"quantity": 1})
    assert exc.value.status_code == 503


def test_room_charge_consent_is_part_of_idempotency_contract():
    submitted = StructuredRequestSubmit.model_validate({
        "language": "tr", "idempotency_key": "k", "items": [{"service_code": "fnb.club_sandwich"}],
    })
    confirmed = StructuredRequestSubmit.model_validate({
        "language": "tr", "idempotency_key": "k", "confirm_room_charge": True,
        "items": [{"service_code": "fnb.club_sandwich"}],
    })
    assert compute_payload_fingerprint(submitted.language, submitted.items, submitted.confirm_room_charge) != compute_payload_fingerprint(
        confirmed.language, confirmed.items, confirmed.confirm_room_charge
    )
