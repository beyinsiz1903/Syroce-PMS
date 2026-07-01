"""
Agency v1 — KATI DTO birim testleri (ADR Karar 1).

Saf testtir: backend/Mongo/secret gerektirmez. Yalniz Pydantic dogrulama
sinirini kapsar: gecerli govde kabul; bilinmeyen alan / gecersiz tarih /
uyumsuz schema_version / kotu enum / sira ihlali -> ValidationError (uca 422).
Sahte-yesil URETILMEZ; davranis gercek DTO kodundan gozlenir. PII test sabitidir.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from routers.agency_v1.dtos import (
    SCHEMA_VERSION,
    AgencyReservationCreate,
    AgencyReservationModify,
)


def _valid_create_payload() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "agency_reservation_id": "AG-123",
        "confirmation_number": "CN-9",
        "status": "confirmed",
        "arrival_date": "2026-07-01",
        "departure_date": "2026-07-03",
        "room_type_id": "RT-1",
        "rate_plan_id": "RP-1",
        "occupancy": {"adults": 2, "children": 1, "child_ages": [6]},
        "room_count": 1,
        "meal_plan": "BB",
        "pricing": {
            "total": 8400.0,
            "sub_total": 8000.0,
            "tax_total": 400.0,
            "currency": "TRY",
            "breakdown": [
                {"date": "2026-07-01", "sell_rate": 4200.0, "currency": "TRY"},
                {"date": "2026-07-02", "sell_rate": 4200.0, "currency": "TRY"},
            ],
        },
        "commission": {"amount": 840.0, "rate": 10.0},
        "payment_type": "prepaid",
        "guest": {
            "first_name": "Test",
            "last_name": "Misafir",
            "email": "t@example.com",
            "nationality": "TR",
        },
        "special_requests": "ust kat",
    }


def test_create_valid_payload_accepts():
    model = AgencyReservationCreate.model_validate(_valid_create_payload())
    assert model.agency_reservation_id == "AG-123"
    assert model.meal_plan.value == "BB"
    assert model.status.value == "confirmed"
    assert model.payment_type.value == "prepaid"


def test_create_unknown_field_rejected():
    payload = _valid_create_payload()
    payload["totally_unknown"] = "x"
    with pytest.raises(ValidationError):
        AgencyReservationCreate.model_validate(payload)


def test_create_nested_unknown_field_rejected():
    payload = _valid_create_payload()
    payload["guest"]["ssn"] = "999"  # kanonik disi alan
    with pytest.raises(ValidationError):
        AgencyReservationCreate.model_validate(payload)


def test_create_bad_date_format_rejected():
    payload = _valid_create_payload()
    payload["arrival_date"] = "01-07-2026"
    with pytest.raises(ValidationError):
        AgencyReservationCreate.model_validate(payload)


def test_create_departure_not_after_arrival_rejected():
    payload = _valid_create_payload()
    payload["departure_date"] = payload["arrival_date"]
    with pytest.raises(ValidationError):
        AgencyReservationCreate.model_validate(payload)


def test_create_invalid_meal_plan_rejected():
    payload = _valid_create_payload()
    payload["meal_plan"] = "XX"
    with pytest.raises(ValidationError):
        AgencyReservationCreate.model_validate(payload)


def test_create_invalid_status_rejected():
    payload = _valid_create_payload()
    payload["status"] = "teleported"
    with pytest.raises(ValidationError):
        AgencyReservationCreate.model_validate(payload)


def test_create_invalid_payment_type_rejected():
    payload = _valid_create_payload()
    payload["payment_type"] = "cash_under_table"
    with pytest.raises(ValidationError):
        AgencyReservationCreate.model_validate(payload)


def test_create_canonical_but_non_agency_status_rejected():
    # checked_out kanonik enum'da var ama acente sozlesmesinde gecersiz -> 422.
    payload = _valid_create_payload()
    payload["status"] = "checked_out"
    with pytest.raises(ValidationError):
        AgencyReservationCreate.model_validate(payload)


def test_create_missing_currency_rejected():
    payload = _valid_create_payload()
    del payload["pricing"]["currency"]
    with pytest.raises(ValidationError):
        AgencyReservationCreate.model_validate(payload)


def test_create_breakdown_missing_currency_rejected():
    payload = _valid_create_payload()
    del payload["pricing"]["breakdown"][0]["currency"]
    with pytest.raises(ValidationError):
        AgencyReservationCreate.model_validate(payload)


def test_create_wrong_schema_version_rejected():
    payload = _valid_create_payload()
    payload["schema_version"] = "1999-01"
    with pytest.raises(ValidationError):
        AgencyReservationCreate.model_validate(payload)


def test_create_missing_required_field_rejected():
    payload = _valid_create_payload()
    del payload["room_type_id"]
    with pytest.raises(ValidationError):
        AgencyReservationCreate.model_validate(payload)


def test_create_child_age_out_of_range_rejected():
    payload = _valid_create_payload()
    payload["occupancy"]["child_ages"] = [40]
    with pytest.raises(ValidationError):
        AgencyReservationCreate.model_validate(payload)


def test_modify_partial_accepts():
    model = AgencyReservationModify.model_validate(
        {"schema_version": SCHEMA_VERSION, "special_requests": "geç giris"}
    )
    assert model.special_requests == "geç giris"
    assert model.status is None


def test_modify_requires_at_least_one_mutable_field():
    with pytest.raises(ValidationError):
        AgencyReservationModify.model_validate({"schema_version": SCHEMA_VERSION})


def test_modify_unknown_field_rejected():
    with pytest.raises(ValidationError):
        AgencyReservationModify.model_validate(
            {"schema_version": SCHEMA_VERSION, "nope": 1}
        )


def test_modify_date_order_when_both_present():
    with pytest.raises(ValidationError):
        AgencyReservationModify.model_validate(
            {
                "schema_version": SCHEMA_VERSION,
                "arrival_date": "2026-07-05",
                "departure_date": "2026-07-05",
            }
        )
