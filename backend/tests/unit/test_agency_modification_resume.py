"""An interrupted modification acceptance can be finished through the public
endpoint, with exactly the recorded changes, without unsafe lock release."""

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from routers import agency_contracts
from routers import marketplace_b2b as m


class _Store:
    """Tiny stateful collection: equality, $in/$nin and $or filters."""

    def __init__(self, rows=None):
        self.rows = [copy.deepcopy(r) for r in rows or []]
        self.fail_updates = 0

    @classmethod
    def _match(cls, row, query):
        for key, cond in query.items():
            if key == "$or":
                if not any(cls._match(row, sub) for sub in cond):
                    return False
            elif isinstance(cond, dict):
                if "$in" in cond and row.get(key) not in cond["$in"]:
                    return False
                if "$nin" in cond and row.get(key) in cond["$nin"]:
                    return False
            elif row.get(key) != cond:
                return False
        return True

    async def find_one(self, query, *_a, **_k):
        return next((copy.deepcopy(r) for r in self.rows if self._match(r, query)), None)

    async def update_one(self, query, update, **_k):
        if self.fail_updates:
            self.fail_updates -= 1
            return SimpleNamespace(matched_count=0)
        for row in self.rows:
            if self._match(row, query):
                row.update(copy.deepcopy(update.get("$set", {})))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    async def find_one_and_update(self, query, update, **_k):
        for row in self.rows:
            if self._match(row, query):
                row.update(update.get("$set", {}))
                return copy.deepcopy(row)
        return None

    async def insert_one(self, doc):
        if any(r.get("_id") == doc.get("_id") for r in self.rows):
            raise DuplicateKeyError("busy")
        self.rows.append(copy.deepcopy(doc))

    async def delete_one(self, query):
        before = len(self.rows)
        self.rows = [r for r in self.rows if not self._match(r, query)]
        return SimpleNamespace(deleted_count=before - len(self.rows))

    def find(self, query, *_a, **_k):
        return SimpleNamespace(to_list=AsyncMock(return_value=[copy.deepcopy(r) for r in self.rows if self._match(r, query)]))


@pytest.fixture
def world(monkeypatch):
    proposal = {"id": "p", "tenant_id": "t", "agency_id": "a", "reservation_id": "b", "type": "agency_modification",
                "status": "awaiting_hotel",
                "requested": {"check_in": "2027-01-01", "check_out": "2027-01-02", "room_type": "standard", "rate_plan_code": "BB"}}
    booking = {"id": "b", "tenant_id": "t", "agency_id": "a", "status": "confirmed", "adults": 2, "children": 0,
               "child_ages": [], "syroce_b2b_fee_pct": 2, "rate_plan_code": "RO", "net_to_hotel": 80, "total_amount": 100}
    database = SimpleNamespace(
        rooms=_Store([{"id": "r", "tenant_id": "t", "room_type": "standard", "capacity": 3, "base_price": 100}]),
        bookings=_Store([booking]),
        marketplace_negotiations=_Store([proposal]),
        marketplace_bookings=_Store([{"id": "b", "tenant_id": "t", "agency_id": "a", "net_to_hotel": 80, "rate_plan_code": "RO"}]),
        agency_sale_mutexes=_Store(),
    )
    monkeypatch.setattr(m, "db", database)
    monkeypatch.setattr(m, "get_system_db", lambda: database)
    monkeypatch.setattr(m, "_require_hotel_admin", lambda _user: "t")
    monkeypatch.setattr(agency_contracts, "has_active_contract", AsyncMock(return_value={"status": "approved", "commission_pct": 10}))
    monkeypatch.setattr(m, "_get_listing_or_404", AsyncMock(return_value={}))
    monkeypatch.setattr(m, "_validated_agency_quote", AsyncMock(return_value={
        "total_price": 130, "nightly_rates": [{"date": "2027-01-01", "rate": 130}], "meal_plan": "BB"}))
    monkeypatch.setattr(m, "_check_agency_credit", AsyncMock())
    monkeypatch.setattr(m, "assign_room_atomic", AsyncMock())
    return database


ACCEPT = m.CancellationProposalDecision(accept=True)


@pytest.mark.asyncio
async def test_failed_ledger_write_keeps_fence_and_complete_button_finishes(world):
    world.marketplace_bookings.fail_updates = 1
    with pytest.raises(RuntimeError):
        await m.hotel_decide_marketplace_modification("p", ACCEPT, object())
    assert world.marketplace_negotiations.rows[0]["status"] == "applying"
    assert len(world.agency_sale_mutexes.rows) == 1  # fence retained, not released

    # Any other agency operation is still blocked by the retained fence.
    from core.agency_sales_guard import agency_sale_guard

    with pytest.raises(HTTPException) as busy:
        async with agency_sale_guard(world, "t", "a", operation="reservation", reference_id="other", resume=True):
            pass
    assert busy.value.status_code == 409

    quotes_before = m._validated_agency_quote.await_count
    result = await m.hotel_decide_marketplace_modification("p", ACCEPT, object())  # "Uygulamayı tamamla"
    assert result["status"] == "accepted"
    assert m._validated_agency_quote.await_count == quotes_before  # recorded changes, not re-priced
    assert world.marketplace_bookings.rows[0]["net_to_hotel"] == 117
    assert world.marketplace_negotiations.rows[0]["status"] == "accepted"
    assert world.agency_sale_mutexes.rows == []  # released after a verified finish


@pytest.mark.asyncio
async def test_partial_pms_state_with_same_dates_is_still_written(world):
    world.marketplace_bookings.fail_updates = 1
    with pytest.raises(RuntimeError):
        await m.hotel_decide_marketplace_modification("p", ACCEPT, object())
    recorded = world.marketplace_negotiations.rows[0]["pending_changes"]
    # Simulate a PMS row that has the dates, room and total but older plan/financials.
    pms = world.bookings.rows[0]
    pms.update(check_in=recorded["check_in"], check_out=recorded["check_out"], room_id=recorded["room_id"],
               total_amount=recorded["total_amount"], rate_plan_code="RO", net_to_hotel=104)

    await m.hotel_decide_marketplace_modification("p", ACCEPT, object())
    pms = world.bookings.rows[0]
    ledger = world.marketplace_bookings.rows[0]
    assert (pms["rate_plan_code"], pms["net_to_hotel"]) == ("BB", 117)
    assert (ledger["rate_plan_code"], ledger["net_to_hotel"]) == ("BB", 117)
    assert pms["commission_pct"] == ledger["commission_pct"] == 10


@pytest.mark.asyncio
async def test_resume_cannot_decline_or_take_over_another_operation(world):
    world.marketplace_bookings.fail_updates = 1
    with pytest.raises(RuntimeError):
        await m.hotel_decide_marketplace_modification("p", ACCEPT, object())
    with pytest.raises(HTTPException) as declined:
        await m.hotel_decide_marketplace_modification("p", m.CancellationProposalDecision(accept=False), object())
    assert declined.value.status_code == 409  # fence not taken over for a decline
    assert world.marketplace_negotiations.rows[0]["status"] == "applying"


@pytest.mark.asyncio
async def test_finish_compares_every_recorded_field_not_only_dates(world):
    recorded = {"check_in": "2027-01-01T14:00:00", "check_out": "2027-01-02T11:00:00", "room_id": "r", "total_amount": 130,
                "rate_plan_code": "BB", "commission_pct": 10, "net_to_hotel": 117, "credit_exposure_amount": 117,
                "room_type": "standard", "credit_exposure_currency": "TRY", "nightly_rates": [], "meal_plan": "BB",
                "cancellation_policy": {}, "updated_at": "now"}
    world.bookings.rows[0].update(check_in=recorded["check_in"], check_out=recorded["check_out"], room_id="r",
                                  total_amount=130, rate_plan_code="RO", net_to_hotel=104)
    world.marketplace_negotiations.rows[0].update(status="applying", pending_changes=recorded)
    proposal = await world.marketplace_negotiations.find_one({"id": "p"})
    await m._finish_marketplace_proposal(world, "t", proposal, ACCEPT)
    assert (world.bookings.rows[0]["rate_plan_code"], world.bookings.rows[0]["net_to_hotel"]) == ("BB", 117)


@pytest.mark.asyncio
async def test_resume_cannot_take_over_while_the_first_writer_is_still_running(world):
    import asyncio

    from core.agency_sales_guard import agency_sale_guard

    gate, entered = asyncio.Event(), asyncio.Event()
    real_update = world.marketplace_bookings.update_one

    async def slow_ledger(query, update, **kw):
        entered.set()
        await gate.wait()  # first writer paused mid-write
        return await real_update(query, update, **kw)

    world.marketplace_bookings.update_one = slow_ledger
    first = asyncio.create_task(m.hotel_decide_marketplace_modification("p", ACCEPT, object()))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert world.marketplace_negotiations.rows[0]["status"] == "applying"

        with pytest.raises(HTTPException) as busy:  # "Uygulamayı tamamla" while the first is alive
            # A wrongly granted takeover would block on the same paused write.
            await asyncio.wait_for(m.hotel_decide_marketplace_modification("p", ACCEPT, object()), 2)
        assert busy.value.status_code == 409
        with pytest.raises(HTTPException):  # and no other sale can slip in
            async with agency_sale_guard(world, "t", "a", operation="reservation", reference_id="other"):
                pass
        assert world.agency_sale_mutexes.rows[0]["recovery_state"] == "active"
    finally:
        gate.set()
    assert (await asyncio.wait_for(first, 5))["status"] == "accepted"
    assert world.agency_sale_mutexes.rows == []


@pytest.mark.asyncio
async def test_only_one_resumer_wins_a_retained_fence(world):
    world.marketplace_bookings.fail_updates = 1
    with pytest.raises(RuntimeError):
        await m.hotel_decide_marketplace_modification("p", ACCEPT, object())
    fence = world.agency_sale_mutexes.rows[0]
    assert fence["recovery_state"] == "retained"

    from core.agency_sales_guard import agency_sale_guard

    async with agency_sale_guard(world, "t", "a", operation="marketplace_modification", reference_id="p", resume=True):
        assert world.agency_sale_mutexes.rows[0]["recovery_state"] == "active"
        with pytest.raises(HTTPException):  # a second resumer loses the compare-and-set
            async with agency_sale_guard(world, "t", "a", operation="marketplace_modification", reference_id="p", resume=True):
                pass


def _crashed(world):
    """Writer killed mid-acceptance: changes recorded, fence left 'active'."""
    recorded = {"check_in": "2027-01-01T14:00:00", "check_out": "2027-01-02T11:00:00", "room_id": "r", "total_amount": 130,
                "rate_plan_code": "BB", "commission_pct": 10, "net_to_hotel": 117, "credit_exposure_amount": 117,
                "room_type": "standard", "credit_exposure_currency": "TRY", "nightly_rates": [], "meal_plan": "BB",
                "cancellation_policy": {}, "updated_at": "now"}
    world.marketplace_negotiations.rows[0].update(status="applying", pending_changes=recorded)
    import hashlib
    import json

    key = hashlib.sha256(json.dumps(["t", "a"]).encode()).hexdigest()
    world.agency_sale_mutexes.rows.append({"_id": key, "owner": "dead-writer-1", "tenant_id": "t", "agency_id": "a",
                                           "operation": "marketplace_modification", "reference_id": "p",
                                           "idempotency_key": None, "recovery_state": "active"})
    world.agency_sales_lock_recoveries = _Store()
    world.idempotency_keys = _Store()
    return key


@pytest.mark.asyncio
async def test_operator_releases_a_crashed_writers_fence_for_resume(world, monkeypatch):
    key = _crashed(world)
    audit = AsyncMock()
    monkeypatch.setattr(m, "_record_marketplace_audit", audit)

    with pytest.raises(HTTPException) as busy:  # hotel "complete": fence not retained
        await m.hotel_decide_marketplace_modification("p", ACCEPT, object())
    assert busy.value.status_code == 409
    reconcile = m.AgencySalesLockReconcile(owner="dead-writer-1", resolution="booking_committed",
                                           reason="Süreç çöktü, inceleme yapıldı", writer_stopped_confirmed=True)
    with pytest.raises(HTTPException) as refused:  # plain release: change not verified
        await m.admin_reconcile_agency_sales_lock(key, reconcile, True)
    assert refused.value.status_code == 409

    listed = await m._sales_lock_evidence(world, world.agency_sale_mutexes.rows[0])
    assert listed["resumable"] is True and "pending_changes" not in listed["proposal"]

    resume = m.AgencySalesLockResume(owner="dead-writer-1", reason="Süreç çöktü, inceleme yapıldı")
    with pytest.raises(HTTPException) as unconfirmed:
        await m.admin_release_sales_lock_for_resume(key, resume, True)
    assert unconfirmed.value.status_code == 422
    resume.writer_stopped_confirmed = True
    with pytest.raises(HTTPException):  # wrong owner: never touch another holder's fence
        await m.admin_release_sales_lock_for_resume(key, m.AgencySalesLockResume(
            owner="someone-else", reason="Süreç çöktü, inceleme yapıldı", writer_stopped_confirmed=True), True)

    released = await m.admin_release_sales_lock_for_resume(key, resume, True)
    assert released["proposal_id"] == "p"
    assert world.agency_sale_mutexes.rows[0]["recovery_state"] == "retained"  # kept, not deleted
    assert world.agency_sales_lock_recoveries.rows[0]["resolution"] == "released_for_resume"
    assert audit.await_args.kwargs["action"] == "agency_sales_lock_released_for_resume"
    assert (await m.admin_release_sales_lock_for_resume(key, resume, True))["idempotent_replay"] is True

    result = await m.hotel_decide_marketplace_modification("p", ACCEPT, object())  # "Uygulamayı tamamla"
    assert result["status"] == "accepted"
    assert (world.bookings.rows[0]["net_to_hotel"], world.marketplace_bookings.rows[0]["net_to_hotel"]) == (117, 117)
    assert world.agency_sale_mutexes.rows == []


@pytest.mark.asyncio
async def test_release_for_resume_refuses_other_operations(world, monkeypatch):
    key = _crashed(world)
    world.agency_sale_mutexes.rows[0]["operation"] = "reservation"
    monkeypatch.setattr(m, "_record_marketplace_audit", AsyncMock())
    with pytest.raises(HTTPException) as exc:
        await m.admin_release_sales_lock_for_resume(key, m.AgencySalesLockResume(
            owner="dead-writer-1", reason="Süreç çöktü, inceleme yapıldı", writer_stopped_confirmed=True), True)
    assert exc.value.status_code == 409
    assert world.agency_sale_mutexes.rows[0]["recovery_state"] == "active"


@pytest.fixture
def hotel_cancellation(monkeypatch):
    database = SimpleNamespace(
        bookings=_Store([{"id": "b", "tenant_id": "t", "agency_id": "a", "status": "confirmed"}]),
        marketplace_bookings=_Store([{"id": "b", "agency_id": "a", "tenant_id": "t", "status": "confirmed"}]),
        marketplace_negotiations=_Store([{"id": "p", "type": "hotel_cancellation", "tenant_id": "t", "agency_id": "a",
                                          "reservation_id": "b", "status": "awaiting_agency", "reason": "Otel hizmet veremiyor"}]),
    )
    monkeypatch.setattr(m, "db", database)
    monkeypatch.setattr(m, "get_system_db", lambda: database)
    monkeypatch.setattr("core.atomic_booking.release_booking_nights", AsyncMock())
    return database


@pytest.mark.asyncio
async def test_interrupted_hotel_cancellation_is_finished_by_accepting_again(hotel_cancellation):
    database = hotel_cancellation
    database.marketplace_bookings.fail_updates = 1  # ledger outage after the PMS cancel
    with pytest.raises(RuntimeError):
        await m.agency_decide_negotiation("p", ACCEPT, {"agency_id": "a"})
    assert database.bookings.rows[0]["status"] == "cancelled"
    assert database.marketplace_negotiations.rows[0]["status"] == "applying"
    with pytest.raises(HTTPException):  # cannot flip to "declined" after the PMS cancel
        await m.agency_decide_negotiation("p", m.CancellationProposalDecision(accept=False), {"agency_id": "a"})

    result = await m.agency_decide_negotiation("p", ACCEPT, {"agency_id": "a"})
    assert result["status"] == "accepted" and result["reservation_cancelled"] is True
    assert database.marketplace_bookings.rows[0]["status"] == "cancelled"
    assert database.marketplace_negotiations.rows[0]["status"] == "accepted"


@pytest.mark.asyncio
async def test_hotel_cancellation_never_cancels_a_guest_who_checked_in_meanwhile(hotel_cancellation):
    database = hotel_cancellation
    real_find = database.bookings.find_one

    async def checked_in_after_read(query, *a, **k):
        row = await real_find(query, *a, **k)
        database.bookings.rows[0]["status"] = "checked_in"  # front desk checks the guest in
        return row

    database.bookings.find_one = checked_in_after_read
    with pytest.raises(HTTPException) as exc:
        await m.agency_decide_negotiation("p", ACCEPT, {"agency_id": "a"})
    assert exc.value.status_code == 409 and "giriş yaptı" in exc.value.detail
    assert database.bookings.rows[0]["status"] == "checked_in"
    assert database.marketplace_bookings.rows[0]["status"] == "confirmed"
    assert database.marketplace_negotiations.rows[0]["status"] == "superseded"  # closed, not stuck


@pytest.mark.asyncio
async def test_agency_endpoint_cannot_finish_an_agency_modification_without_the_fence(world):
    world.marketplace_bookings.fail_updates = 1
    with pytest.raises(RuntimeError):
        await m.hotel_decide_marketplace_modification("p", ACCEPT, object())
    assert world.marketplace_negotiations.rows[0]["status"] == "applying"
    with pytest.raises(HTTPException) as exc:  # agency-side "complete" on an agency_modification
        await m.agency_decide_negotiation("p", ACCEPT, {"agency_id": "a"})
    assert exc.value.status_code == 404
    assert world.marketplace_negotiations.rows[0]["status"] == "applying"
    assert world.marketplace_bookings.rows[0]["net_to_hotel"] == 80  # untouched
