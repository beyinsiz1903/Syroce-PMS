"""Real LOCAL replica regressions for remaining front-office service paths."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

from domains.guest import checkin_router
from domains.guest import qr_submission_service as qr
from domains.guest.experience_router import upsell
from tests.test_department_live_folio_acceptance import actor, db, wired  # noqa: F401


@pytest_asyncio.fixture
async def guest_services(wired, monkeypatch):  # noqa: F811
    for name in ("upsell_offers", "guest_service_submissions"):
        await wired.create_collection(name)
    monkeypatch.setattr(upsell, "db", wired)
    monkeypatch.setattr(checkin_router, "db", wired)
    monkeypatch.setattr("modules.pms_core.folio_hardening_service.db", wired)
    monkeypatch.setattr("core.utils.db", wired)
    await wired.upsell_offers.insert_one(
        {
            "id": "offer",
            "tenant_id": "t",
            "booking_id": "b",
            "folio_id": "actual-folio",
            "status": "pending",
            "price": 240,
            "currency": "TRY",
            "tax_rate": 0.2,
            "target_item": "QA dining package",
            "type": "dining_credit",
            "service_category": "food",
            "reason": "QA retained synthetic service",
            "service_date": "2026-10-30",
        }
    )
    item = {
        "service_code": "fnb.tea",
        "title": "QA tea",
        "property_id": "p",
        "booking_id": "b",
        "created_at": datetime.now(UTC),
        "room_charge": {"unit_price_minor": 10000, "quantity": 2, "total_minor": 20000, "currency": "TRY", "folio_category": "room_service", "tax_rate": 0.1},
    }
    await wired.guest_service_submissions.insert_one(
        {"tenant_id": "t", "property_id": "p", "booking_id": "b", "submission_group_id": "submission", "prepared_items": [item], "room_charge_status": "pending", "room_charge_consent": True}
    )
    return wired


async def accept():
    return await upsell.update_upsell_offer("offer", "accepted", actor(), None)


async def post_qr(database):
    ledger = await database.guest_service_submissions.find_one({"submission_group_id": "submission"})
    return await qr._post_room_service_charges("t", database, "b", "submission", ledger["prepared_items"])


async def test_upsell_preserves_currency_declared_gross_tax_and_source_day(guest_services):
    await accept()
    charge = await guest_services.folio_charges.find_one({"upsell_offer_id": "offer"})
    assert charge["currency"] == "TRY" and charge["total"] == 240
    assert (charge["amount"], charge["vat_amount"]) == (200, 40)
    assert charge["business_date"] == "2026-10-26" and charge["service_date"] == "2026-10-30"
    assert charge["charge_category"] == "food" and charge["posted_by"] == "manager"
    assert (await guest_services.bookings.find_one({"id": "b"}))["balance"] == 240


async def test_upsell_concurrent_retry_is_one_canonical_charge(guest_services):
    await asyncio.gather(accept(), accept())
    original = await guest_services.upsell_offers.find_one({"id": "offer"})
    await accept()
    assert await guest_services.upsell_offers.find_one({"id": "offer"}) == original
    assert await guest_services.folio_charges.count_documents({"upsell_offer_id": "offer"}) == 1
    assert await guest_services.audit_logs.count_documents({"action": "upsell_charge_posted"}) == 1


async def test_upsell_unknown_tax_is_not_zero_percent_evidence(guest_services):
    await guest_services.upsell_offers.update_one({"id": "offer"}, {"$unset": {"tax_rate": ""}})
    await accept()
    charge = await guest_services.folio_charges.find_one({"upsell_offer_id": "offer"})
    assert charge["vat_amount"] is None and charge["tax_amount"] is None


@pytest.mark.parametrize("field,value", [("currency", "EUR"), ("status", "checked_out"), ("tenant_id", "other")])
async def test_upsell_invalid_target_never_marks_offer_accepted(guest_services, field, value):
    await guest_services.bookings.update_one({"id": "b"}, {"$set": {field: value}})
    with pytest.raises(HTTPException):
        await accept()
    assert (await guest_services.upsell_offers.find_one({"id": "offer"}))["status"] == "pending"
    assert not await guest_services.folio_charges.count_documents({})


async def test_upsell_audit_failure_rolls_back_status_and_receivable(guest_services, monkeypatch):
    monkeypatch.setattr("core.department_folio.append_audit_log", AsyncMock(side_effect=RuntimeError("audit unavailable")))
    with pytest.raises(RuntimeError):
        await accept()
    assert (await guest_services.upsell_offers.find_one({"id": "offer"}))["status"] == "pending"
    assert not await guest_services.folio_charges.count_documents({})


async def test_qr_uses_persisted_source_current_day_and_explicit_tax(guest_services):
    await post_qr(guest_services)
    charge = await guest_services.folio_charges.find_one({"source_qr_submission_line_id": "submission:fnb.tea"})
    assert charge and charge["total"] == 200 and charge["currency"] == "TRY"
    assert charge["business_date"] == "2026-10-26" and charge["vat_amount"] == 18.18
    assert charge["amount"] == 181.82 and charge["source_fingerprint"]
    assert (await guest_services.bookings.find_one({"id": "b"}))["balance"] == 200


async def test_qr_retry_and_concurrency_do_not_double_charge(guest_services):
    await asyncio.gather(post_qr(guest_services), post_qr(guest_services))
    await post_qr(guest_services)
    assert await guest_services.folio_charges.count_documents({}) == 1
    assert await guest_services.audit_logs.count_documents({"action": "room_service_charge_posted"}) == 1


async def test_qr_multi_line_invalid_currency_rolls_back_every_charge(guest_services):
    ledger = await guest_services.guest_service_submissions.find_one({"submission_group_id": "submission"})
    bad = {**ledger["prepared_items"][0], "service_code": "fnb.bad", "room_charge": {**ledger["prepared_items"][0]["room_charge"], "currency": "EUR"}}
    await guest_services.guest_service_submissions.update_one({"submission_group_id": "submission"}, {"$push": {"prepared_items": bad}})
    with pytest.raises(HTTPException):
        await post_qr(guest_services)
    assert not await guest_services.folio_charges.count_documents({})
    assert (await guest_services.guest_service_submissions.find_one({"submission_group_id": "submission"}))["room_charge_status"] == "pending"


async def test_qr_legacy_charge_is_not_silently_reposted(guest_services):
    await guest_services.folio_charges.insert_one(
        {"tenant_id": "t", "id": "legacy", "folio_id": "actual-folio", "booking_id": "b", "total": 200, "currency": "TRY", "external_reference": "qr-room-service:submission:fnb.tea"}
    )
    with pytest.raises(HTTPException) as error:
        await post_qr(guest_services)
    assert error.value.status_code == 409
    assert await guest_services.folio_charges.count_documents({}) == 1


async def test_qr_does_not_trust_an_unpersisted_or_changed_payload(guest_services):
    ledger = await guest_services.guest_service_submissions.find_one({"submission_group_id": "submission"})
    changed = [{**ledger["prepared_items"][0], "title": "Changed title"}]
    with pytest.raises(HTTPException):
        await qr._post_room_service_charges("t", guest_services, "b", "submission", changed)
    assert not await guest_services.folio_charges.count_documents({})


async def test_upsell_explicit_zero_price_and_tax_are_not_replaced(guest_services):
    await guest_services.upsell_offers.update_one({"id": "offer"}, {"$unset": {"price": ""}, "$set": {"original_price": 100, "discounted_price": 0, "tax_rate": 0}})
    await accept()
    charge = await guest_services.folio_charges.find_one({"upsell_offer_id": "offer"})
    assert (charge["total"], charge["vat_amount"]) == (0, 0)


@pytest.mark.parametrize(
    "update",
    [
        {"currency": None},
        {"valid_until": "2020-01-01"},
        {"valid_until": "invalid"},
        {"status": "rejected"},
        {"status": "accepted", "folio_charge_id": None},
        {"folio_id": "foreign"},
    ],
)
async def test_upsell_ambiguous_old_source_or_expired_offer_is_blocked(guest_services, update):
    await guest_services.upsell_offers.update_one({"id": "offer"}, {"$set": update})
    with pytest.raises(HTTPException):
        await accept()
    assert not await guest_services.folio_charges.count_documents({})


async def test_legacy_and_modern_upsell_entrypoints_share_one_charge(guest_services):
    result = await checkin_router.accept_upsell_offer({"offer_id": "offer", "action": "accept"}, actor(), None)
    assert result["success"] and result["currency"] == "TRY" and result["amount"] == 240
    await accept()
    assert await guest_services.folio_charges.count_documents({}) == 1
    with pytest.raises(HTTPException):
        await checkin_router.accept_upsell_offer({"offer_id": "offer", "action": "reject"}, actor(), None)
    assert (await guest_services.upsell_offers.find_one({"id": "offer"}))["status"] == "accepted"


async def test_legacy_guest_cannot_accept_someone_elses_offer(guest_services):
    user = actor()
    user.role = "guest_app"
    with pytest.raises(HTTPException) as error:
        await checkin_router.accept_upsell_offer({"offer_id": "offer", "action": "accept"}, user, None)
    assert error.value.status_code == 403
    assert not await guest_services.folio_charges.count_documents({})


async def test_qr_consent_is_required_from_persisted_source(guest_services):
    await guest_services.guest_service_submissions.update_one({"submission_group_id": "submission"}, {"$set": {"room_charge_consent": False}})
    with pytest.raises(HTTPException):
        await post_qr(guest_services)
    assert not await guest_services.folio_charges.count_documents({})


async def test_qr_unknown_tax_stays_unknown_and_source_datetime_roundtrips_bson(guest_services):
    ledger = await guest_services.guest_service_submissions.find_one({"submission_group_id": "submission"})
    prepared = ledger["prepared_items"]
    prepared[0]["created_at"] = datetime(2026, 10, 30, 12, 1, 2, 123456, tzinfo=UTC)
    prepared[0]["room_charge"].pop("tax_rate")
    await guest_services.guest_service_submissions.update_one({"_id": ledger["_id"]}, {"$set": {"prepared_items": prepared}})
    await qr._post_room_service_charges("t", guest_services, "b", "submission", prepared)
    charge = await guest_services.folio_charges.find_one({})
    assert charge["total"] == 200 and charge["vat_amount"] is None and charge["service_date"] is None


async def test_qr_second_line_audit_failure_rolls_back_whole_bill(guest_services, monkeypatch):
    from core import department_folio

    original = department_folio.append_audit_log
    calls = 0

    async def audit(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second audit unavailable")
        return await original(*args, **kwargs)

    ledger = await guest_services.guest_service_submissions.find_one({"submission_group_id": "submission"})
    second = {**ledger["prepared_items"][0], "service_code": "fnb.second"}
    await guest_services.guest_service_submissions.update_one({"_id": ledger["_id"]}, {"$push": {"prepared_items": second}})
    monkeypatch.setattr(department_folio, "append_audit_log", audit)
    with pytest.raises(RuntimeError):
        await post_qr(guest_services)
    assert not await guest_services.folio_charges.count_documents({})
    assert not await guest_services.audit_logs.count_documents({})
    assert (await guest_services.folios.find_one({"id": "actual-folio"}))["balance"] == 0


async def test_qr_two_lines_post_once_and_reconcile_aggregate(guest_services):
    ledger = await guest_services.guest_service_submissions.find_one({"submission_group_id": "submission"})
    second = {**ledger["prepared_items"][0], "service_code": "fnb.second"}
    await guest_services.guest_service_submissions.update_one({"_id": ledger["_id"]}, {"$push": {"prepared_items": second}})
    await post_qr(guest_services)
    await post_qr(guest_services)
    assert await guest_services.folio_charges.count_documents({}) == 2
    assert (await guest_services.bookings.find_one({"id": "b"}))["balance"] == 400


@pytest.mark.parametrize("path", ["upsell", "qr"])
async def test_closed_business_day_blocks_every_source(guest_services, path):
    await guest_services.night_audit_runs.insert_one({"tenant_id": "t", "business_date": "2026-10-26", "status": "completed"})
    with pytest.raises(HTTPException):
        await (accept() if path == "upsell" else post_qr(guest_services))
    assert not await guest_services.folio_charges.count_documents({})


async def test_qr_full_catalogue_submission_consent_retry_and_snapshot(guest_services, monkeypatch):
    from models.schemas.qr_catalogue_submission import StructuredRequestSubmit

    monkeypatch.setattr(qr, "raw_db", guest_services)
    monkeypatch.setattr(qr, "resolve_catalogue_mode", AsyncMock(return_value="configured"))
    catalogue = {
        "service_code": "fnb.qa_soup",
        "department_code": "fnb",
        "enabled": True,
        "labels": {"tr": "QA çorba"},
        "input_type": "quantity",
        "input_config": {"min": 1, "max": 5},
        "is_chargeable": True,
        "room_charge_enabled": True,
        "unit_price_minor": 12000,
        "currency": "TRY",
        "tax_rate": 0.2,
    }
    monkeypatch.setattr(qr, "fetch_catalogue_data", AsyncMock(return_value=([], [catalogue])))
    await guest_services.guest_service_submissions.create_index([("tenant_id", 1), ("property_id", 1), ("booking_id", 1), ("idempotency_key", 1)], unique=True)
    await guest_services.qr_requests.create_index([("tenant_id", 1), ("submission_group_id", 1), ("service_code", 1)], unique=True)
    payload = StructuredRequestSubmit.model_validate(
        {"language": "tr", "idempotency_key": "full-qa", "confirm_room_charge": True, "items": [{"service_code": "fnb.qa_soup", "value": {"quantity": 2}}]}
    )
    args = ("t", "p", "r", "b", "qa-session", "101", payload, "QA Synthetic", None)
    result = await qr.handle_structured_submission(*args)
    # Reprice the catalogue after creation: retries must use the immutable consented source.
    catalogue["unit_price_minor"] = 99999
    retry = await qr.handle_structured_submission(*args)
    assert retry["room_charge_lines"] == result["room_charge_lines"]
    assert result["room_charge_lines"][0]["total_minor"] == 24000
    assert await guest_services.folio_charges.count_documents({}) == 1
    charge = await guest_services.folio_charges.find_one({})
    assert (charge["total"], charge["vat_amount"], charge["business_date"]) == (240, 40, "2026-10-26")
    assert await guest_services.qr_requests.count_documents({}) == 1
    with pytest.raises(HTTPException):
        await qr.handle_structured_submission(*args[:6], payload.model_copy(update={"confirm_room_charge": False}), *args[7:])


async def test_upsell_reports_only_canonical_posted_amounts_and_separate_currencies(guest_services):
    await accept()
    await guest_services.upsell_offers.insert_many(
        [
            {"id": "eur", "tenant_id": "t", "booking_id": "e", "status": "accepted", "price": 999, "folio_charge_id": "e-charge"},
            {"id": "old", "tenant_id": "t", "booking_id": "b", "status": "accepted", "price": 999999},
        ]
    )
    await guest_services.folio_charges.insert_one({"id": "e-charge", "tenant_id": "t", "booking_id": "e", "total": 50, "currency": "EUR", "source_upsell_offer_id": "eur", "voided": False})
    result = await upsell.list_upsell_offers(None, actor())
    assert result["summary"]["revenue_by_currency"] == {"TRY": 240, "EUR": 50}
    assert result["summary"]["revenue"] is None
    assert result["summary"]["unreconciled_accepted"] == 1
    await guest_services.folio_charges.update_one({"id": "e-charge"}, {"$set": {"voided": True}})
    result = await upsell.list_upsell_offers(None, actor())
    assert result["summary"]["revenue_by_currency"] == {"TRY": 240}
    assert result["summary"]["unreconciled_accepted"] == 2


async def test_manual_offer_idempotency_rejects_changed_financial_source(guest_services, monkeypatch):
    from starlette.requests import Request

    monkeypatch.setattr(upsell, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    request = Request({"type": "http", "headers": [(b"idempotency-key", b"offer-qa")]})
    payload = {"booking_id": "b", "type": "custom", "price": 180, "currency": "TRY", "tax_rate": 0.2, "service_date": "2026-10-30", "folio_id": "actual-folio"}
    first = await upsell.create_upsell_offer(payload, request, actor(), None)
    assert first["tax_rate"] == 0.2 and first["currency"] == "TRY"
    await guest_services.idempotency_keys.delete_many({})
    retry = await upsell.create_upsell_offer(payload, request, actor(), None)
    assert retry["id"] == first["id"]
    with pytest.raises(HTTPException) as error:
        await upsell.create_upsell_offer({**payload, "price": 190}, request, actor(), None)
    assert error.value.status_code == 409
    assert await guest_services.upsell_offers.count_documents({"source": "manual"}) == 1


async def test_insights_month_boundaries_and_currency_are_not_mixed(guest_services):
    from datetime import timedelta

    now = datetime.now(UTC)
    start = now.replace(day=1).date()
    following = (now.replace(day=28) + timedelta(days=4)).replace(day=1).date()
    await guest_services.bookings.insert_many(
        [
            {"id": "usd-month", "tenant_id": "t", "status": "confirmed", "currency": "USD", "total_amount": 200, "check_in": start.isoformat(), "check_out": (start + timedelta(days=2)).isoformat()},
            {"id": "try-month", "tenant_id": "t", "status": "confirmed", "currency": "TRY", "total_amount": 2000, "check_in": start.isoformat(), "check_out": (start + timedelta(days=2)).isoformat()},
            {
                "id": "next-month",
                "tenant_id": "t",
                "status": "confirmed",
                "currency": "TRY",
                "total_amount": 999999,
                "check_in": following.isoformat(),
                "check_out": (following + timedelta(days=2)).isoformat(),
            },
            {"id": "missing-unit", "tenant_id": "t", "status": "confirmed", "total_amount": 3000, "check_in": start.isoformat(), "check_out": (start + timedelta(days=2)).isoformat()},
        ]
    )
    result = await upsell.get_revenue_insights(actor())
    assert result["kpis"]["adr_by_currency"] == {"USD": 100, "TRY": 1000}
    assert result["kpis"]["adr"] is None
    assert result["kpis"]["unknown_currency_count"] == 1
