from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.context import OperationContext
from domains.pms.night_audit import financial_service as financial_module


class AsyncCursor:
    def __init__(self, documents=None, *, error=None):
        self.documents = list(documents or [])
        self.error = error

    def sort(self, *_args, **_kwargs):
        return self

    def skip(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def max_time_ms(self, *_args, **_kwargs):
        return self

    async def to_list(self, _length=None, **_kwargs):
        if self.error:
            raise self.error
        return list(self.documents)

    def __aiter__(self):
        async def generate():
            if self.error:
                raise self.error
            for document in self.documents:
                yield dict(document)

        return generate()


def _ctx():
    return OperationContext(tenant_id="tenant-1", actor_id="user-1", actor_role="admin")


def _service(database):
    service = financial_module.FinancialService()
    service._db = database
    return service


def _aggregate_collection(*cursors):
    return SimpleNamespace(aggregate=MagicMock(side_effect=list(cursors)))


def _find_collection(*cursors, count=0):
    return SimpleNamespace(
        find=MagicMock(side_effect=list(cursors)),
        count_documents=AsyncMock(return_value=count),
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("9000", 9000), ("999", 8000), ("invalid", 8000), (None, 8000)],
)
def test_env_int_accepts_only_safe_time_budgets(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("TEST_FIN_TIMEOUT", raising=False)
    else:
        monkeypatch.setenv("TEST_FIN_TIMEOUT", raw)

    assert financial_module._env_int("TEST_FIN_TIMEOUT", 8000) == expected


@pytest.mark.asyncio
async def test_daily_summary_combines_revenue_payments_tax_balances_and_audit_status():
    charges = _aggregate_collection(
        AsyncCursor(
            [
                {"_id": "room", "total_amount": 1000.125, "total_tax": 100.012, "total_with_tax": 1100.137, "count": 2},
                {"_id": None, "total_amount": 50.0, "total_tax": 5.0, "total_with_tax": 55.0, "count": 1},
            ]
        ),
        AsyncCursor([{"total_vat": 82.345, "total_accommodation_tax": 22.667}]),
    )
    payments = _aggregate_collection(
        AsyncCursor([{"_id": "card", "total_amount": 400.0, "count": 1}])
    )
    folios = _aggregate_collection(
        AsyncCursor(
            [
                {"_id": "card", "total_amount": 100.0, "count": 1},
                {"_id": None, "total_amount": 50.0, "count": 1},
            ]
        ),
        AsyncCursor([{"total_balance": 300.0, "positive_balance": 350.0, "negative_balance": -50.0, "count": 3}]),
    )
    database = SimpleNamespace(
        folio_charges=charges,
        payments=payments,
        folios=folios,
        night_audit_runs=SimpleNamespace(find_one=AsyncMock(return_value={"status": "completed"})),
    )

    result = await _service(database).get_daily_financial_summary(_ctx(), "2026-08-25")

    assert result.ok is True
    assert result.data["revenue"] == {
        "total": 1050.12,
        "total_with_tax": 1155.14,
        "by_category": {
            "room": {"amount": 1000.12, "tax": 100.01, "total": 1100.14, "count": 2},
            "other": {"amount": 50.0, "tax": 5.0, "total": 55.0, "count": 1},
        },
        "charges_count": 3,
    }
    assert result.data["payments"] == {
        "total": 550.0,
        "by_method": {
            "card": {"amount": 500.0, "count": 2},
            "other": {"amount": 50.0, "count": 1},
        },
        "payments_count": 3,
    }
    assert result.data["tax"]["breakdown"] == {"vat": 82.34, "accommodation_tax": 22.67}
    assert result.data["open_folios"] == {
        "count": 3,
        "balance": {"total": 300.0, "receivable": 350.0, "overpayment": 50.0},
    }
    assert result.data["net_position"] == 605.14
    assert result.data["audit_status"] == "completed"
    assert charges.aggregate.call_args_list[0].kwargs["maxTimeMS"] == financial_module._FIN_AGG_MAX_MS


@pytest.mark.asyncio
async def test_daily_summary_degrades_each_failed_subquery_to_safe_defaults():
    failure = RuntimeError("database timeout")
    database = SimpleNamespace(
        folio_charges=_aggregate_collection(AsyncCursor(error=failure), AsyncCursor(error=failure)),
        payments=_aggregate_collection(AsyncCursor(error=failure)),
        folios=_aggregate_collection(AsyncCursor(error=failure), AsyncCursor(error=failure)),
        night_audit_runs=SimpleNamespace(find_one=AsyncMock(side_effect=failure)),
    )

    result = await _service(database).get_daily_financial_summary(_ctx(), "2026-08-25")

    assert result.ok is True
    assert result.data["revenue"]["total"] == 0.0
    assert result.data["payments"]["total"] == 0.0
    assert result.data["open_folios"]["count"] == 0
    assert result.data["audit_status"] == "not_run"


@pytest.mark.asyncio
async def test_payment_reconciliation_detects_duplicate_orphan_rate_and_high_balance_issues():
    charges = [
        {"id": "charge-1", "booking_id": "booking-1", "charge_category": "room", "amount": 100.0, "total": 110.0, "description": "Room"},
        {"id": "charge-2", "booking_id": "booking-1", "charge_category": "room", "amount": 100.0, "total": 110.0, "description": "Room"},
        {"id": "charge-3", "booking_id": "booking-missing", "charge_category": "minibar", "amount": 50.0, "total": 50.0},
    ]
    folio_charges = _find_collection(AsyncCursor(charges))
    payments = _find_collection(AsyncCursor([{"id": "payment-1", "amount": 200.0}]))
    folios = _find_collection(
        AsyncCursor([{"id": "folio-1", "folio_number": "F-1", "balance": 1500.0}])
    )
    bookings = _find_collection(
        AsyncCursor([{"id": "booking-1", "room_rate": 120.0, "status": "checked_in"}])
    )
    database = SimpleNamespace(
        folio_charges=folio_charges,
        payments=payments,
        folios=folios,
        bookings=bookings,
    )

    result = await _service(database).get_payment_reconciliation(_ctx(), "2026-08-25")

    assert result.ok is True
    assert result.data["charges_total"] == 270.0
    assert result.data["payments_total"] == 200.0
    assert result.data["variance"] == 70.0
    assert result.data["is_balanced"] is False
    issue_types = {item["type"] for item in result.data["discrepancies"]}
    assert issue_types == {"duplicate_charge", "orphan_charge", "rate_discrepancy", "high_balance"}
    assert result.data["degraded"] is False
    booking_query = bookings.find.call_args.args[0]
    assert set(booking_query["id"]["$in"]) == {"booking-1", "booking-missing"}


@pytest.mark.asyncio
async def test_payment_reconciliation_reports_initial_query_degradation():
    failure = RuntimeError("query timeout")
    database = SimpleNamespace(
        folio_charges=_find_collection(AsyncCursor(error=failure)),
        payments=_find_collection(AsyncCursor(error=failure)),
        folios=_find_collection(AsyncCursor(error=failure)),
        bookings=_find_collection(AsyncCursor()),
    )

    result = await _service(database).get_payment_reconciliation(_ctx(), "2026-08-25")

    assert result.ok is True
    assert result.data["degraded"] is True
    assert result.data["degraded_subqueries"] == ["charges", "payments", "high_balance_folios"]
    assert result.data["charges_total"] == 0
    assert result.data["payments_total"] == 0


@pytest.mark.asyncio
async def test_payment_reconciliation_reports_booking_enrichment_failure():
    database = SimpleNamespace(
        folio_charges=_find_collection(
            AsyncCursor([{"id": "charge-1", "booking_id": "booking-1", "charge_category": "room", "amount": 100.0, "total": 110.0}])
        ),
        payments=_find_collection(AsyncCursor()),
        folios=_find_collection(AsyncCursor()),
        bookings=_find_collection(AsyncCursor(error=RuntimeError("booking lookup failed"))),
    )

    result = await _service(database).get_payment_reconciliation(_ctx(), "2026-08-25")

    assert result.data["degraded"] is True
    assert result.data["degraded_subqueries"] == ["bookings_enrich"]
    assert result.data["discrepancies"][0]["type"] == "orphan_charge"


@pytest.mark.asyncio
async def test_financial_report_aggregates_revenue_payments_audits_and_occupancy():
    database = SimpleNamespace(
        folio_charges=_aggregate_collection(
            AsyncCursor(
                [
                    {"_id": {"date": "2026-08-24", "category": "room"}, "amount": 100.0, "tax": 10.0, "total": 110.0, "count": 1},
                    {"_id": {"date": "2026-08-25", "category": None}, "amount": 50.0, "tax": 5.0, "total": 55.0, "count": 2},
                ]
            )
        ),
        payments=_aggregate_collection(
            AsyncCursor([{"_id": "cash", "total": 80.0, "count": 1}])
        ),
        night_audit_runs=SimpleNamespace(
            find=MagicMock(return_value=AsyncCursor([{"audit_id": "audit-1", "status": "completed"}]))
        ),
        bookings=_aggregate_collection(AsyncCursor([{"total_bookings": 4}])),
        rooms=SimpleNamespace(count_documents=AsyncMock(return_value=10)),
    )

    result = await _service(database).get_financial_report(
        _ctx(), "2026-08-24", "2026-08-25"
    )

    assert result.ok is True
    assert result.data["summary"] == {
        "total_revenue": 150.0,
        "total_tax": 15.0,
        "total_with_tax": 165.0,
        "total_payments": 80.0,
        "net_position": 85.0,
        "total_bookings": 4,
        "total_rooms": 10,
    }
    assert result.data["revenue_by_category"]["room"] == {"amount": 100.0, "tax": 10.0, "count": 1}
    assert result.data["revenue_by_category"]["other"] == {"amount": 50.0, "tax": 5.0, "count": 2}
    assert len(result.data["revenue_by_date"]) == 2
    assert result.data["payments_by_method"] == {"cash": {"amount": 80.0, "count": 1}}
    assert result.data["degraded"] is False


@pytest.mark.asyncio
async def test_financial_report_isolates_all_database_failures():
    failure = RuntimeError("database unavailable")
    database = SimpleNamespace(
        folio_charges=_aggregate_collection(AsyncCursor(error=failure)),
        payments=_aggregate_collection(AsyncCursor(error=failure)),
        night_audit_runs=SimpleNamespace(find=MagicMock(return_value=AsyncCursor(error=failure))),
        bookings=_aggregate_collection(AsyncCursor(error=failure)),
        rooms=SimpleNamespace(count_documents=AsyncMock(side_effect=failure)),
    )

    result = await _service(database).get_financial_report(
        _ctx(), "2026-08-24", "2026-08-25"
    )

    assert result.ok is True
    assert result.data["degraded"] is True
    assert result.data["degraded_subqueries"] == [
        "revenue",
        "payments",
        "audit_runs",
        "occupancy",
        "rooms",
    ]
    assert result.data["summary"]["total_revenue"] == 0.0
    assert result.data["summary"]["total_rooms"] == 0


@pytest.mark.asyncio
async def test_enrichment_prefers_authoritative_guest_and_room_records():
    database = SimpleNamespace(
        bookings=_find_collection(
            AsyncCursor(
                [
                    {
                        "id": "booking-1",
                        "guest_id": "guest-1234",
                        "guest_name": "C4",
                        "room_id": "room-1",
                        "room_no": "old-room",
                        "confirmation_code": "CONF-1",
                    }
                ]
            )
        ),
        guests=_find_collection(AsyncCursor([{"id": "guest-1234", "first_name": "Ada", "last_name": "Lovelace"}])),
        rooms=_find_collection(AsyncCursor([{"id": "room-1", "room_number": "204"}])),
    )
    service = _service(database)
    items = [{"booking_id": "booking-1"}]

    result = await service._enrich_with_guest_room("tenant-1", items)

    assert result == [
        {
            "booking_id": "booking-1",
            "guest_name": "Ada Lovelace",
            "room_no": "204",
            "confirmation_code": "CONF-1",
        }
    ]


@pytest.mark.asyncio
async def test_enrichment_replaces_placeholder_guest_name_with_readable_fallback():
    database = SimpleNamespace(
        bookings=_find_collection(
            AsyncCursor([{"id": "booking-1", "guest_id": "guest-abcd", "guest_name": "V4 Refund", "room_id": "room-1", "room_no": "205"}])
        ),
        guests=_find_collection(AsyncCursor([{"id": "guest-abcd", "name": "C4"}])),
        rooms=_find_collection(AsyncCursor()),
    )
    service = _service(database)

    result = await service._enrich_with_guest_room(
        "tenant-1", [{"booking_id": "booking-1"}]
    )

    assert result[0]["guest_name"] == "Walk-in Misafir #ABCD"
    assert result[0]["room_no"] == "205"
    assert await service._enrich_with_guest_room("tenant-1", []) == []


@pytest.mark.asyncio
async def test_integrity_check_reports_clean_empty_day():
    database = SimpleNamespace(
        bookings=_find_collection(AsyncCursor(), AsyncCursor(), count=0),
        folios=_find_collection(AsyncCursor(), AsyncCursor(), count=0),
        folio_charges=_find_collection(AsyncCursor(), count=0),
        night_audit_runs=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        guests=_find_collection(AsyncCursor()),
        rooms=_find_collection(AsyncCursor()),
    )

    result = await _service(database).get_integrity_check(_ctx(), "2026-08-25")

    assert result.ok is True
    assert result.data["summary"] == {
        "total": 5,
        "passed": 5,
        "warnings": 0,
        "failures": 0,
        "overall_status": "pass",
    }


@pytest.mark.asyncio
async def test_integrity_check_surfaces_each_operational_issue_and_audit_mismatch():
    bookings = _find_collection(
        AsyncCursor(
            [
                {"id": "booking-missing-folio", "guest_id": "guest-1", "room_id": "room-1"},
                {"id": "booking-with-folio", "folio_id": "folio-open"},
            ]
        ),
        AsyncCursor([{"id": "booking-zero-rate", "room_rate": 0}]),
        count=1,
    )
    folios = _find_collection(
        AsyncCursor(),
        AsyncCursor([{"id": "folio-negative", "booking_id": "booking-1", "balance": -50.0}]),
        AsyncCursor([{"id": "folio-closed"}]),
        count=1,
    )
    folio_charges = _find_collection(
        AsyncCursor([{"id": "charge-voided", "booking_id": "booking-1", "amount": 100.0, "voided_reason": "mistake"}]),
        AsyncCursor([{"folio_id": "folio-closed", "booking_id": "booking-1", "amount": 100.0}]),
        count=1,
    )
    folio_charges.count_documents = AsyncMock(side_effect=[1, 1, 1])
    database = SimpleNamespace(
        bookings=bookings,
        folios=folios,
        folio_charges=folio_charges,
        night_audit_runs=SimpleNamespace(
            find_one=AsyncMock(return_value={"audit_id": "audit-1", "charges_posted": 2})
        ),
        guests=_find_collection(AsyncCursor()),
        rooms=_find_collection(AsyncCursor()),
    )
    service = _service(database)
    service._enrich_with_guest_room = AsyncMock()

    result = await service.get_integrity_check(_ctx(), "2026-08-25")

    assert result.ok is True
    checks = {check["check"]: check for check in result.data["checks"]}
    assert checks["bookings_with_folios"]["status"] == "fail"
    assert checks["voided_charges"]["status"] == "warning"
    assert checks["negative_balance_folios"]["status"] == "warning"
    assert checks["room_rate_consistency"]["status"] == "warning"
    assert checks["closed_folio_charges"]["status"] == "error"
    assert checks["audit_charge_count"]["status"] == "error"
    assert result.data["summary"]["overall_status"] == "fail"
    service._enrich_with_guest_room.assert_awaited_once()
