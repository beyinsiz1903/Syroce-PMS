"""Offline regressions for the operator dashboard's durable folio balances."""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers import pms_dashboard


def _matches(row, query):
    for key, value in query.items():
        if key == "$or":
            if not any(_matches(row, clause) for clause in value):
                return False
        elif key == "$expr":
            # The old snapshot pre-filter hides paid stays with unpaid extras.
            if float(row.get("total_amount") or 0) - float(row.get("paid_amount") or 0) <= 0.01:
                return False
        elif isinstance(value, dict):
            actual = row.get(key)
            for operator, expected in value.items():
                if operator == "$in" and actual not in expected:
                    return False
                if operator == "$gte" and (actual is None or actual < expected):
                    return False
                if operator == "$lt" and (actual is None or actual >= expected):
                    return False
                if operator == "$lte" and (actual is None or actual > expected):
                    return False
                if operator == "$gt" and (actual is None or actual <= expected):
                    return False
        elif row.get(key) != value:
            return False
    return True


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, length):
        return self.rows if length is None else self.rows[:length]

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield row
        return iterate()


class Collection:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.queries = []

    def find(self, query, projection=None):
        self.queries.append(query)
        rows = [row.copy() for row in self.rows if _matches(row, query)]
        included = {key for key, value in (projection or {}).items() if value}
        if included:
            rows = [{key: value for key, value in row.items() if key in included} for row in rows]
        return Cursor(rows)

    async def count_documents(self, query):
        return sum(_matches(row, query) for row in self.rows)


def booking(id="b1", **overrides):
    return {"id": id, "tenant_id": "hotel-a", "status": "checked_in", "guest_name": "Emre Kurt",
            "room_number": "104", "check_in": "2026-10-20", "check_out": "2026-10-26",
            "total_amount": 560, "paid_amount": 0, "currency": "USD", **overrides}


@pytest.fixture
def dashboard(monkeypatch):
    def prepare(bookings, *, charges=(), payments=(), extras=(), folios=()):
        database = SimpleNamespace(
            bookings=Collection(bookings), rooms=Collection(), guests=Collection(),
            folios=Collection(folios), folio_charges=Collection(charges),
            payments=Collection(payments), extra_charges=Collection(extras),
        )
        monkeypatch.setattr(pms_dashboard, "db", database)
        monkeypatch.setattr(pms_dashboard, "_open_business_date", AsyncMock(return_value="2026-10-26"))
        monkeypatch.setattr(pms_dashboard, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
        monkeypatch.setitem(sys.modules, "redis_cache", SimpleNamespace(redis_cache=None))
        return database
    return prepare


async def alerts():
    return await pms_dashboard.get_operational_alerts(SimpleNamespace(tenant_id="hotel-a"))


def alert(result, kind):
    return next(item for item in result["alerts"] if item["type"] == kind)


@pytest.mark.asyncio
async def test_alert_includes_unposted_stay_and_all_folio_extras_in_original_currency(dashboard):
    dashboard([booking()], charges=[
        {"tenant_id": "hotel-a", "booking_id": "b1", "total": 78.8},
        {"tenant_id": "hotel-a", "booking_id": "b1", "total": 3.75},
        {"tenant_id": "hotel-a", "booking_id": "b1", "total": 999, "voided": True},
    ])
    result = await alerts()
    for kind in ["pending_payments", "departures_with_balance"]:
        assert alert(result, kind)["items"][0]["balance"] == 642.55
        assert alert(result, kind)["items"][0]["currency"] == "USD"
    assert result["summary"]["outstanding_by_currency"] == {"USD": 642.55}


@pytest.mark.asyncio
async def test_paid_booking_snapshot_does_not_hide_unpaid_extras_or_folio_only_rows(dashboard):
    dashboard([booking(total_amount=100, paid_amount=100)],
        folios=[{"tenant_id": "hotel-a", "id": "f1", "booking_id": "b1"}],
        charges=[{"tenant_id": "hotel-a", "folio_id": "f1", "total": 100, "charge_type": "room_charge"},
                 {"tenant_id": "hotel-a", "folio_id": "f1", "total": 25}],
        payments=[{"tenant_id": "hotel-a", "folio_id": "f1", "amount": 100, "status": "paid"}],
        extras=[{"tenant_id": "hotel-a", "booking_id": "b1", "charge_amount": 5}])
    result = await alerts()
    assert alert(result, "pending_payments")["items"][0]["balance"] == 30
    assert alert(result, "departures_with_balance")["count"] == 1


@pytest.mark.asyncio
async def test_ledger_payments_comp_refund_and_retries_override_stale_paid_amount(dashboard):
    dashboard([booking(total_amount=100, paid_amount=0)],
        charges=[{"tenant_id": "hotel-a", "booking_id": "b1", "total": 40, "charge_type": "room_charge"}],
        payments=[
            {"tenant_id": "hotel-a", "booking_id": "b1", "amount": 70, "idempotency_key": "receipt"},
            {"tenant_id": "hotel-a", "booking_id": "b1", "amount": 70, "idempotency_key": "receipt"},
            {"tenant_id": "hotel-a", "booking_id": "b1", "amount": 10, "method": "complimentary"},
            {"tenant_id": "hotel-a", "booking_id": "b1", "amount": 20, "payment_type": "refund"},
            {"tenant_id": "hotel-a", "booking_id": "b1", "amount": 999, "status": "pending"},
        ])
    assert alert(await alerts(), "pending_payments")["items"][0]["balance"] == 40


@pytest.mark.asyncio
async def test_upgrade_is_additive_and_settled_guests_are_not_alerted(dashboard):
    dashboard([booking(total_amount=6600), booking("settled", total_amount=100)],
        charges=[{"tenant_id": "hotel-a", "booking_id": "b1", "total": 2400,
                  "charge_type": "room_upgrade", "charge_category": "room"}],
        payments=[{"tenant_id": "hotel-a", "booking_id": "settled", "amount": 100}])
    result = await alerts()
    assert alert(result, "pending_payments")["count"] == 1
    assert alert(result, "departures_with_balance")["items"][0]["balance"] == 9000


@pytest.mark.asyncio
async def test_currencies_never_form_an_unconverted_scalar_and_departures_use_business_date(dashboard):
    dashboard([booking(), booking("b2", currency="TRY", total_amount=200, check_out="2026-10-27")])
    result = await alerts()
    assert result["summary"]["total_outstanding"] is None
    assert alert(result, "pending_payments")["total_amount"] is None
    assert result["summary"]["outstanding_by_currency"] == {"USD": 560, "TRY": 200}
    assert alert(result, "departures_with_balance")["count"] == 1
    assert alert(result, "departures_with_balance")["items"][0]["booking_id"] == "b1"


@pytest.mark.asyncio
async def test_tenant_scoped_batch_reads_do_not_truncate_or_issue_per_guest_queries(dashboard):
    database = dashboard([booking(f"b{i}", total_amount=1) for i in range(205)] + [
        booking("foreign", tenant_id="hotel-b", total_amount=999)],
        charges=[{"tenant_id": "hotel-b", "booking_id": "b0", "total": 999}],
        folios=[{"tenant_id": "hotel-b", "id": "foreign-folio", "booking_id": "b0"}])
    result = await alerts()
    assert alert(result, "pending_payments")["count"] == 205
    assert result["summary"]["outstanding_by_currency"] == {"USD": 205}
    for name in ["folios", "folio_charges", "payments", "extra_charges"]:
        queries = getattr(database, name).queries
        assert len(queries) == 1
        assert queries[0]["tenant_id"] == "hotel-a"
    assert all("$expr" not in query for query in database.bookings.queries)


@pytest.mark.asyncio
async def test_financial_read_failure_is_not_returned_as_all_clear(dashboard):
    database = dashboard([booking()])
    database.payments.find = lambda *_args: (_ for _ in ()).throw(RuntimeError("ledger unavailable"))
    with pytest.raises(RuntimeError, match="ledger unavailable"):
        await alerts()


@pytest.mark.asyncio
async def test_conflicting_ledger_ownership_requires_reconciliation_instead_of_double_counting(dashboard):
    dashboard([booking(), booking("b2")],
        folios=[{"tenant_id": "hotel-a", "id": "f1", "booking_id": "b1"}],
        charges=[{"tenant_id": "hotel-a", "booking_id": "b2", "folio_id": "f1", "total": 10}])
    with pytest.raises(ValueError, match="ownership disagree"):
        await alerts()


@pytest.mark.asyncio
async def test_foreign_ledger_amount_is_not_silently_relabeled_as_booking_currency(dashboard):
    dashboard([booking(currency="USD")],
        charges=[{"tenant_id": "hotel-a", "booking_id": "b1", "currency": "TRY", "total": 150}])
    with pytest.raises(ValueError, match="currency requires reconciliation"):
        await alerts()


@pytest.mark.asyncio
async def test_empty_inhouse_has_zero_totals_and_does_not_query_unscoped_ledgers(dashboard):
    database = dashboard([])
    result = await alerts()
    assert result["alerts"] == []
    assert result["summary"]["total_outstanding"] == 0
    assert result["summary"]["outstanding_by_currency"] == {}
    assert all(not getattr(database, name).queries for name in ["folios", "folio_charges", "payments", "extra_charges"])


@pytest.mark.asyncio
async def test_old_snapshot_cache_cannot_mask_new_balances_and_key_includes_business_date(dashboard, monkeypatch):
    dashboard([])
    from unittest.mock import Mock
    cache = SimpleNamespace(get=Mock(return_value=None), set=Mock())
    monkeypatch.setitem(sys.modules, "redis_cache", SimpleNamespace(redis_cache=cache))
    await alerts()
    cache.get.assert_called_once_with("operational_alerts:v2:hotel-a:2026-10-26")
    assert cache.set.call_args.args[0] == "operational_alerts:v2:hotel-a:2026-10-26"
