from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.agency_finance_directory import extranet_directory, finance_partners, linked_extranet_id
from core.agency_record_classification import LEGACY_DEMO_IDENTITIES, archived_agency, readonly_finance
from core.agency_record_classification import test_or_demo as is_test_or_demo
from core.agency_reports import build_report
from routers import agency_statements as statements
from routers import travel_agent_arap as arap
from tests.unit.test_agency_reports import _booking
from tests.unit.test_agency_statements_symmetric import _Coll, _match

TODAY = date(2026, 10, 17)
USER = SimpleNamespace(tenant_id="t1", email="hotel@example.com")


@pytest.fixture
def world():
    return SimpleNamespace(
        agencies=_Coll(), agency_transactions=SimpleNamespace(insert_one=AsyncMock()),
        agency_payment_plans=_Coll(), bookings=_Coll(), marketplace_bookings=_Coll(),
        agency_statements=_Coll(),
        agency_contracts=_Coll([
            {"tenant_id": "t1", "agency_id": "a1", "agency_name": "Test Acente E2E", "status": "approved", "contract_code": "SOZ-1"},
            {"tenant_id": "t1", "agency_id": "a1", "status": "expired", "contract_code": "SOZ-OLD"},
            {"tenant_id": "t2", "agency_id": "other", "status": "approved", "contract_code": "SOZ-2"},
            {"tenant_id": "t1", "agency_id": "pending", "status": "pending"},
        ]),
        marketplace_agencies=_Coll([
            {"id": "a1", "name": "Test Acente E2E", "contact_email": "agent@example.com", "api_key": "DO_NOT_EXPOSE"},
            {"id": "other", "name": "Other hotel's agency"},
        ]),
    )


@pytest.mark.asyncio
async def test_approved_agency_visible_without_local_card_or_first_booking(world):
    result = await extranet_directory(world, "t1", today=TODAY)
    assert len(result["agencies"]) == 1
    row = result["agencies"][0]
    assert (row["id"], row["name"], row["approved"], row["currencies"]) == ("a1", "Test Acente E2E", True, [])
    assert "api_key" not in row
    assert world.agencies.rows == []  # no shadow copies / implicit writes
    assert result["as_of"] == "2026-10-17"


@pytest.mark.asyncio
async def test_current_statement_balance_and_future_sales_not_mixed(world):
    world.marketplace_bookings.rows = [_booking("b1", check_in="2026-11-20")]
    world.agency_statements.rows = [
        {"id": "try-due", "tenant_id": "t1", "agency_id": "a1", "currency": "TRY", "status": "agreed", "agreed_at": "2026-10-01",
         "totals": {"net_balance": 6800}, "payments": [{"amount": 1000, "direction": "agency_to_hotel"}]},
        {"id": "eur-due", "tenant_id": "t1", "agency_id": "a1", "currency": "EUR", "status": "agreed", "agreed_at": "2026-10-01",
         "totals": {"net_balance": -150}, "payments": []},
        {"id": "try-commission", "tenant_id": "t1", "agency_id": "a1", "currency": "TRY", "status": "issued",
         "totals": {"net_balance": -300}, "payments": []},
    ]
    result = await extranet_directory(world, "t1", today=TODAY)
    rows = {row["currency"]: row for row in result["agencies"][0]["currencies"]}
    assert rows["TRY"]["receivables"]["agency_owes_hotel"] == 5800
    assert rows["TRY"]["receivables"]["hotel_owes_agency"] == 300  # no netting of opposite directions
    assert rows["EUR"]["receivables"]["hotel_owes_agency"] == 150
    assert rows["TRY"]["forward"]["90"]["gross"] == 8000
    assert rows["TRY"]["unbilled"]["agency_owes_hotel"] == 0  # future sale isn't a receivable


@pytest.mark.asyncio
async def test_canonical_payment_seen_by_hotel_directory_and_agency_portal(world, monkeypatch):
    world.agency_statements.rows = [{"id": "s1", "tenant_id": "t1", "agency_id": "a1", "currency": "EUR", "status": "agreed",
                                    "agreed_at": "2026-10-01", "totals": {"net_balance": 100}, "payments": [], "lines": []}]
    monkeypatch.setattr(statements, "get_system_db", lambda: world)
    monkeypatch.setattr(statements, "_notify", AsyncMock())
    before = await extranet_directory(world, "t1", today=TODAY)
    assert before["agencies"][0]["currencies"][0]["receivables"]["agency_owes_hotel"] == 100
    data = statements.PaymentCreate(amount=100, currency="EUR", paid_at="2026-10-17", method="bank_transfer", reference="EFT-TEST-1", direction="agency_to_hotel")
    await statements._record_payment_as("s1", data, statements.Party("hotel", USER.email, tenant_id="t1"))
    hotel = await extranet_directory(world, "t1", today=TODAY)
    agency = await build_report(world, side="agency", scope={"agency_id": "a1"}, period_start="2026-10-01", period_end="2026-10-17", today=TODAY)
    assert world.agency_statements.rows[0]["status"] == "settled"
    assert all(row["receivables"]["agency_owes_hotel"] == 0 for row in hotel["agencies"][0]["currencies"])
    assert all(row["receivables"]["agency_owes_hotel"] == 0 for row in agency["rows"])
    world.agency_transactions.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_accessible_after_contract_removal_and_other_tenant_never_leaks(world):
    world.agency_statements.rows = [
        {"id": "s1", "tenant_id": "t1", "agency_id": "historic", "agency_name": "Past partner", "currency": "USD", "status": "settled", "totals": {"net_balance": 0}},
        {"id": "s2", "tenant_id": "t2", "agency_id": "other", "currency": "USD", "status": "agreed", "totals": {"net_balance": 999}},
    ]
    partners = await finance_partners(world, "t1")
    assert set(partners) == {"a1", "historic"}
    result = await extranet_directory(world, "t1", today=TODAY)
    assert {row["id"] for row in result["agencies"]} == {"a1", "historic"}
    historical = next(row for row in result["agencies"] if row["id"] == "historic")
    assert historical["has_financial_history"] is True and historical["currencies"] == []
    assert await linked_extranet_id(world, "t1", "other") is None
    assert await linked_extranet_id(world, "t1", "old-local", {"migrated_to_marketplace_agency_id": "a1"}) == "a1"
    assert await linked_extranet_id(world, "t1", "different-local", {"name": "Test Acente E2E", "contact_email": "agent@example.com"}) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("agency_id,local", [("a1", None), ("a1", {"id": "a1", "name": "Duplicated card"}),
                                           ("old-local", {"id": "old-local", "migrated_to_marketplace_agency_id": "a1"})])
async def test_legacy_payment_and_plan_cannot_create_a_second_extranet_ledger(world, monkeypatch, agency_id, local):
    world.agencies.rows = [{**local, "tenant_id": "t1"}] if local else []
    monkeypatch.setattr(arap, "db", world)
    monkeypatch.setattr(arap, "_sys_db", world)
    with pytest.raises(HTTPException) as error:
        await arap.record_payment(arap.RecordPaymentRequest(agency_id=agency_id, amount=50), USER)
    assert error.value.status_code == 409
    world.agency_transactions.insert_one.assert_not_awaited()
    with pytest.raises(HTTPException) as error:
        await arap.create_payment_plan(arap.CreatePaymentPlanRequest(agency_id=agency_id, total_amount=50, installments=2, start_date="2026-10-17"), USER)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_inactive_real_agency_can_settle_historical_debt(world, monkeypatch):
    world.agencies.rows = [{"id": "inactive-local", "tenant_id": "t1", "name": "Real partner", "status": "inactive"}]
    monkeypatch.setattr(arap, "db", world)
    monkeypatch.setattr(arap, "_sys_db", world)
    assert (await arap._writable_local_agency("t1", "inactive-local"))["id"] == "inactive-local"
    with pytest.raises(HTTPException) as error:
        await arap._writable_local_agency("t1", "other")
    assert error.value.status_code == 404


@pytest.mark.parametrize("record,archived,readonly", [
    ({"name": "=cmd|'/c calc'!A1"}, True, True),
    ({"name": "TEST_CSV"}, True, True),
    ({"name": "Test Acente E2E"}, False, False),
    ({"name": "Real", "status": "inactive"}, True, False),
    ({"name": "Real", "status": "migrated"}, True, True),
    ({"name": "Real", "is_demo": True}, True, True),
    ({"name": "Blue Horizon Travel", "contact_email": "real@example.com"}, False, False),
])
def test_archive_classification_is_not_name_only(record, archived, readonly):
    assert archived_agency(record) is archived
    assert readonly_finance(record) is readonly


def test_exact_legacy_seed_fingerprints_classified_without_deleting_history():
    for identity in LEGACY_DEMO_IDENTITIES:
        record = dict(zip(("name", "contact_email", "contact_phone", "notes"), identity, strict=True))
        assert is_test_or_demo(record)
        record["contact_email"] = "real@example.com"
        assert not is_test_or_demo(record)


@pytest.mark.asyncio
async def test_legacy_visibility_and_grouped_currency_results_not_truncated(world, monkeypatch):
    world.agencies.rows = [
        {"id": "local", "tenant_id": "t1", "name": "Real", "status": "active", "commission_rate": 15},
        {"id": "test", "tenant_id": "t1", "name": "TEST_export", "status": "active"},
        {"id": "inactive", "tenant_id": "t1", "name": "Inactive", "status": "inactive"},
        {"id": "a1", "tenant_id": "t1", "name": "Duplicated central card", "status": "active"},
        {"id": "old-local", "tenant_id": "t1", "name": "Explicit migration alias", "migrated_to_marketplace_agency_id": "a1"},
    ]

    class Aggregates:
        def aggregate(self, pipeline):
            assert pipeline[0]["$match"]["tenant_id"] == "t1"
            class Cursor:
                async def to_list(self, limit):
                    assert limit is None  # currency groups are not bounded by agency count
                    if "total_revenue" in pipeline[1]["$group"]:
                        return [{"_id": {"agency_id": "local", "currency": currency}, "total_revenue": 100, "count": 1}
                                for currency in ("TRY", "EUR", "USD", "GBP", "CAD", "AUD", "CHF", "JPY", "NOK", "SEK", "DKK", "PLN", "CZK", "HUF", "AED")]
                    return []
            return Cursor()

    world.bookings = world.agency_transactions = world.agency_payment_plans = Aggregates()
    monkeypatch.setattr(arap, "get_tenant_currency", AsyncMock(return_value=("TRY", {})))
    visible = await arap._get_agency_ledger("t1", db_handle=world)
    archive = await arap._get_agency_ledger("t1", db_handle=world, include_archived=True)
    assert [row["agency_id"] for row in visible] == ["local"]
    assert len(visible[0]["balance_by_currency"]) == 15
    assert visible[0]["balance_by_currency"]["EUR"] == 15
    assert visible[0]["balance_by_currency"]["USD"] == 15
    assert {row["agency_id"] for row in archive} == {"local", "test", "inactive", "a1", "old-local"}
    assert len(world.agencies.rows) == 5  # only filtered, never deleted
    history = next(row for row in archive if row["agency_id"] == "old-local")
    assert history["extranet_agency_id"] == "a1" and history["readonly_finance"]
    for field, value in (("marketplace_agency_id", "a1"), ("origin", "syroce_marketplace"), ("channel", "marketplace"), ("source_channel", "marketplace")):
        assert not _match({"tenant_id": "t1", "agency_id": "local", "status": "confirmed", field: value}, arap._local_booking_query("t1", ["local"]))


@pytest.mark.asyncio
async def test_statement_picker_matches_same_directory(world, monkeypatch):
    monkeypatch.setattr(statements, "get_system_db", lambda: world)
    monkeypatch.setattr(statements, "_require_hotel_admin", lambda _user: "t1")
    assert await statements.statement_agencies(USER) == {"agencies": [{"id": "a1", "name": "Test Acente E2E"}]}


@pytest.mark.asyncio
async def test_directory_endpoint_respects_hotel_role_and_current_tenant(world, monkeypatch):
    monkeypatch.setattr(arap, "_sys_db", world)
    user = SimpleNamespace(tenant_id="t1", role="admin", email=USER.email)
    assert [row["id"] for row in (await arap.get_extranet_agencies(user))["agencies"]] == ["a1"]
    user.tenant_id = "t2"
    assert [row["id"] for row in (await arap.get_extranet_agencies(user))["agencies"]] == ["other"]
    user.role = "staff"
    with pytest.raises(HTTPException) as error:
        await arap.get_extranet_agencies(user)
    assert error.value.status_code == 403
