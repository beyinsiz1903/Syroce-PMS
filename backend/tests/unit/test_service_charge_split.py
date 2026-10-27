from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from bson import ObjectId
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse

from modules.pms_core.service_charge_split import partition, split_service_charge
from routers.reservation_detail import ChargeSplit
from tests.unit.test_folio_allocation import Collection


@pytest.fixture
def scenario(monkeypatch):
    monkeypatch.setattr('modules.pms_core.service_charge_split.audit_log', AsyncMock())
    booking = {"tenant_id": "hotel", "currency": "TRY", "status": "checked_in"}
    folio = {"tenant_id": "hotel", "currency": "TRY", "status": "open"}
    return SimpleNamespace(
        bookings=Collection([{**booking, "id": "source"}, {**booking, "id": "target"}]),
        folios=Collection([{**folio, "id": "f1", "booking_id": "source"}, {**folio, "id": "f2", "booking_id": "target"}]),
        folio_charges=Collection([{ "id": "meal", "tenant_id": "hotel", "booking_id": "source", "folio_id": "f1", "currency": "TRY",
            "charge_category": "food", "amount": 100, "tax_amount": 20, "tax_breakdown": {"vat": 20}, "total": 120,
            "quantity": 1, "business_date": "2026-10-01", "date": "2026-10-01T12:00:00Z", "voided": False }]),
        extra_charges=Collection(), payments=Collection(), invoices=Collection(), folio_operations=Collection())


def body(**overrides):
    return ChargeSplit(**{"charge_id": "meal", "target_booking_id": "target", "split_amount": 48,
        "reason": "Birlikte yemek ödemesini diğer odaya aktarma", **overrides})


async def run(database, payload=None, key=None, session=True):
    return await split_service_charge(database, "hotel", "operator", "source", payload or body(), key or uuid4(), session=object() if session else None)


@pytest.mark.asyncio
async def test_partial_transfer_conserves_revenue_tax_day_and_derived_balances(scenario):
    result = await run(scenario)
    old, new = scenario.folio_charges.rows
    assert result["remaining_amount"] == 72
    assert (old["amount"], old["tax_amount"], old["total"]) == (60, 12, 72)
    assert (new["amount"], new["tax_amount"], new["total"]) == (40, 8, 48)
    assert new["business_date"] == old["business_date"] == "2026-10-01"
    assert old["tax_breakdown"]["vat"] + new["tax_breakdown"]["vat"] == 20
    assert new["date"] == "2026-10-01T12:00:00Z" and new["booking_id"] == "target"
    assert [row["balance"] for row in scenario.folios.rows] == [72, 48]
    assert not scenario.payments.rows
    assert scenario.folio_operations.rows[0]["original_charge"]["total"] == 120


@pytest.mark.asyncio
async def test_replay_is_single_transfer_and_changed_payload_conflicts(scenario):
    key = uuid4()
    first = await run(scenario, key=key)
    assert await run(scenario, key=key) == {**first, "replayed": True}
    assert len(scenario.folio_charges.rows) == 2
    with pytest.raises(HTTPException) as error:
        await run(scenario, body(split_amount=12), key=key)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_motor_insert_mutation_and_old_replay_are_json_safe(scenario):
    insert = scenario.folio_charges.insert_one

    async def motor_insert(document, **kwargs):
        # Actual Motor/PyMongo behaviour missed by the ordinary in-memory fake.
        document.setdefault("_id", ObjectId())
        return await insert(document, **kwargs)

    scenario.folio_charges.insert_one = motor_insert
    key = uuid4()
    first = await run(scenario, key=key)
    assert "_id" not in first["new_charge"]
    JSONResponse(jsonable_encoder(first))
    # A transfer committed before this fix stored that ObjectId inside its
    # replay body. Replaying must repair the response, not transfer again.
    scenario.folio_operations.rows[0]["result"]["new_charge"]["_id"] = ObjectId()
    second = await run(scenario, key=key)
    assert second["replayed"] and "_id" not in second["new_charge"]
    JSONResponse(jsonable_encoder(second))
    assert len(scenario.folio_charges.rows) == 2


@pytest.mark.asyncio
async def test_quantity_extra_transfers_without_losing_or_inventing_tax(scenario):
    scenario.extra_charges.rows = [{**scenario.folio_charges.rows.pop(), "amount": 60, "quantity": 2}]
    extra = scenario.extra_charges.rows[0]
    extra.pop("folio_id")
    extra.pop("tax_amount")
    extra.pop("tax_breakdown")
    result = await run(scenario)
    left, right = scenario.extra_charges.rows[0], result["new_charge"]
    assert left["amount"] == left["total"] == 72
    assert right["amount"] == right["total"] == 48
    assert left["quantity"] == right["quantity"] == 1
    assert "tax_amount" not in right and "tax_breakdown" not in right


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["closed", "currency", "charge_owner", "voided", "missing_day", "invoice", "room_charge", "overpaid", "same_folio", "unknown_currency", "mixed_target", "full_comp"])
async def test_unsafe_transfer_rejected_before_any_writes(scenario, problem):
    payload = body()
    if problem == "closed":
        scenario.bookings.rows[1]["status"] = "checked_out"
    elif problem == "currency":
        scenario.folios.rows[1]["currency"] = "EUR"
    elif problem == "charge_owner":
        scenario.folio_charges.rows[0]["booking_id"] = "someone-else"
    elif problem == "voided":
        scenario.folio_charges.rows[0]["voided"] = True
    elif problem == "missing_day":
        scenario.folio_charges.rows[0].pop("business_date")
    elif problem == "invoice":
        scenario.invoices.rows.append({"tenant_id": "hotel", "booking_id": "source", "status": "draft"})
    elif problem == "room_charge":
        scenario.folio_charges.rows[0]["charge_category"] = "room"
    elif problem == "overpaid":
        scenario.payments.rows.append({"tenant_id": "hotel", "folio_id": "f1", "amount": 100, "currency": "TRY", "status": "paid"})
    elif problem == "same_folio":
        payload = body(target_booking_id="source", target_folio_id="f1")
    elif problem == "unknown_currency":
        scenario.bookings.rows[0].pop("currency")
        scenario.folios.rows[0].pop("currency")
    elif problem == "mixed_target":
        scenario.payments.rows.append({"tenant_id": "hotel", "folio_id": "f2", "amount": 1, "currency": "USD", "status": "paid"})
    elif problem == "full_comp":
        scenario.bookings.rows[1].update(is_complimentary=True, complimentary_scope="full")
    before = deepcopy(vars(scenario))
    with pytest.raises(HTTPException):
        await run(scenario, payload)
    for name, collection in vars(scenario).items():
        assert collection.rows == before[name].rows


@pytest.mark.asyncio
async def test_transaction_required(scenario):
    with pytest.raises(HTTPException) as error:
        await run(scenario, session=False)
    assert error.value.status_code == 503


def test_cent_allocation_never_manufactures_net_tax_or_discount():
    for tax_cents in range(1, 20):
        for net_cents in range(1, 20):
            gross = tax_cents + net_cents
            for wanted in [1, max(1, gross // 2), gross]:
                row = {"total": gross / 100, "amount": net_cents / 100, "tax_amount": tax_cents / 100,
                    "tax_breakdown": {"vat": tax_cents / 100}, "subtotal": (net_cents + 1) / 100, "discount_amount": .01}
                left, right = partition(row, wanted / 100)
                for key in ["total", "amount", "tax_amount", "subtotal", "discount_amount"]:
                    assert round(left[key] + right[key], 2) == row[key]
                for part in [left, right]:
                    assert round(part["amount"] + part["tax_amount"], 2) == part["total"]
                    assert round(part["subtotal"] - part["discount_amount"], 2) == part["amount"]
                    assert sum(part["tax_breakdown"].values()) == part["tax_amount"]


def test_multicomponent_tax_never_allocates_a_cent_to_zero_tax():
    row = {"total": .1, "amount": .07, "tax_amount": .03, "tax_breakdown": {"a": .01, "b": .01, "c": .01, "z": 0}}
    left, right = partition(row, .04)
    assert right["tax_amount"] == .01
    for part in [left, right]:
        assert part["tax_breakdown"]["z"] == 0
        assert round(sum(part["tax_breakdown"].values()), 2) == part["tax_amount"]


@pytest.mark.asyncio
@pytest.mark.parametrize('category', ['spa', 'minibar', 'food'])
async def test_canonical_department_vat_can_move_to_another_room_without_changing_revenue(scenario, category):
    scenario.folio_charges.rows[0].update(charge_category=category, tax_amount=0, vat_amount=20,
        tax_breakdown={'vat': 20}, amount=100, total=120)
    result = await run(scenario)
    old, new = scenario.folio_charges.rows
    assert result['success']
    assert (old['amount'], old['vat_amount'], old['tax_amount'], old['total']) == (60, 12, 0, 72)
    assert (new['amount'], new['vat_amount'], new['tax_amount'], new['total']) == (40, 8, 0, 48)
    assert sum(row['total'] for row in (old, new)) == 120
    assert old['tax_breakdown']['vat'] + new['tax_breakdown']['vat'] == 20


def test_canonical_vat_and_other_tax_keep_cent_exact_components():
    for total in range(3, 31):
        for wanted in range(1, total):
            row = {'amount': (total - 2) / 100, 'vat_amount': .01, 'tax_amount': .01,
                'tax_breakdown': {'vat': .01, 'other': .01}, 'total': total / 100}
            left, right = partition(row, wanted / 100)
            for part in (left, right):
                assert round(part['amount'] + part['vat_amount'] + part['tax_amount'], 2) == part['total']
            for field in ('amount', 'vat_amount', 'tax_amount', 'total'):
                assert round(left[field] + right[field], 2) == row[field]


@pytest.mark.parametrize("row,extra", [
    ({"total": 120, "amount": 120, "quantity": 2}, True),
    ({"total": 120, "amount": 120, "tax_amount": 0, "tax_breakdown": {"vat": None}}, False),
    ({"total": 120, "amount": 130, "tax_amount": -10}, False),
    ({"total": "NaN"}, False),
])
def test_ambiguous_or_invalid_legacy_components_fail_closed(row, extra):
    with pytest.raises(HTTPException) as error:
        partition(row, 48, extra=extra)
    assert error.value.status_code == 409
