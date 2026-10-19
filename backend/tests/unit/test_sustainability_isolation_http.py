"""Sustainability over HTTP: sign-in, role and hotel isolation (report audit).

The audit found anonymous writes accepted and one hotel reading another's
records (process-memory storage). These requests go through the real
router, authentication and role checks; only the database is in memory.
"""

from datetime import date

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from models.schemas import User
from modules.pms_core.stay_night_metrics import OCCUPYING_STATUSES, calculate_stay_night_metrics
from routers import sustainability as module


def _value(doc, key):
    return doc.get(key)


def _match(doc, query):
    for key, cond in query.items():
        value = _value(doc, key)
        if isinstance(cond, dict):
            for op, arg in cond.items():
                if op == "$lte" and not (value is not None and value <= arg):
                    return False
                if op == "$gte" and not (value is not None and value >= arg):
                    return False
                if op == "$gt" and not (value is not None and value > arg):
                    return False
                if op == "$nin" and value in arg:
                    return False
        elif value != cond:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_a, **_k):
        return self

    async def to_list(self, _n=None):
        return [dict(d) for d in self.docs]

    def __aiter__(self):
        self._it = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return dict(next(self._it))
        except StopIteration:
            raise StopAsyncIteration from None


class _Coll:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    def find(self, query, _projection=None):
        return _Cursor([d for d in self.docs if _match(d, query)])


class _DB:
    def __init__(self, bookings=None, rooms=None):
        self.sustainability_records = _Coll()
        self.bookings = _Coll(bookings)
        self.rooms = _Coll(rooms)


async def _stay_metrics(database, tenant_id, start, end, *, actual_only=False):
    """The real stay-night calculation over the in-memory collections (the
    Mongo query side is covered by tests/test_sustainability_room_nights_mongo)."""
    rooms = [d for d in database.rooms.docs if d.get("tenant_id") == tenant_id]
    bookings = [d for d in database.bookings.docs if d.get("tenant_id") == tenant_id and d.get("status") in OCCUPYING_STATUSES]
    return calculate_stay_night_metrics(bookings, rooms, start, end, actual_only=actual_only)


def _user(tenant_id, role="admin"):
    return User(id=f"u-{tenant_id}-{role}", email=f"{role}.{tenant_id}@example.com", name=role, role=role, tenant_id=tenant_id)


@pytest.fixture
def setup(monkeypatch):
    fake = _DB(bookings=[
        {"tenant_id": "hotel-a", "room_id": "a1", "status": "checked_out", "check_in": "2026-10-01T14:00:00", "check_out": "2026-10-03T11:00:00"},
        {"tenant_id": "hotel-a", "room_id": "a2", "status": "cancelled", "check_in": "2026-10-01", "check_out": "2026-10-05"},
        {"tenant_id": "hotel-b", "room_id": "b1", "status": "checked_out", "check_in": "2026-10-01", "check_out": "2026-10-10"},
    ], rooms=[{"tenant_id": "hotel-a", "id": "a1"}, {"tenant_id": "hotel-a", "id": "a2"}, {"tenant_id": "hotel-b", "id": "b1"}])
    monkeypatch.setattr(module, "db", fake)
    monkeypatch.setattr(module, "load_stay_night_metrics", _stay_metrics)
    app = FastAPI()
    app.include_router(module.router)
    return app, fake


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


RECORD = {"consumption_type": "electricity", "period_start": "2026-10-01", "period_end": "2026-10-31", "amount": 310}


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/sustainability/records", RECORD),
    ("get", "/api/sustainability/records", None),
    ("get", "/api/sustainability/factors", None),
    ("get", "/api/sustainability/report?start_date=2026-10-01&end_date=2026-10-31", None),
])
async def test_anonymous_requests_are_refused(setup, method, path, body):
    app, fake = setup
    async with _client(app) as client:
        response = await (client.post(path, json=body) if method == "post" else client.get(path))
    assert response.status_code == 401
    assert fake.sustainability_records.docs == []


@pytest.mark.asyncio
async def test_a_role_without_the_permission_cannot_enter_consumption(setup):
    app, fake = setup
    app.dependency_overrides[module.get_current_user] = lambda: _user("hotel-a", role="housekeeping")
    async with _client(app) as client:
        response = await client.post("/api/sustainability/records", json=RECORD)
    assert response.status_code == 403
    assert fake.sustainability_records.docs == []


@pytest.mark.asyncio
async def test_records_and_reports_stay_with_the_hotel_that_entered_them(setup):
    app, fake = setup
    app.dependency_overrides[module.get_current_user] = lambda: _user("hotel-a")
    async with _client(app) as client:
        created = await client.post("/api/sustainability/records", json=RECORD)
        assert created.status_code == 200
        assert fake.sustainability_records.docs[0]["tenant_id"] == "hotel-a"     # stored per hotel, not in memory

        app.dependency_overrides[module.get_current_user] = lambda: _user("hotel-b")
        other = await client.get("/api/sustainability/records")
        report_b = await client.get("/api/sustainability/report", params={"start_date": "2026-10-01", "end_date": "2026-10-31"})
        app.dependency_overrides[module.get_current_user] = lambda: _user("hotel-a")
        own = await client.get("/api/sustainability/records")

    assert other.status_code == 200 and other.json() == []
    assert report_b.json()["total_emissions"] == 0 and report_b.json()["record_count"] == 0
    assert [row["id"] for row in own.json()] == [created.json()["id"]]


@pytest.mark.asyncio
async def test_room_nights_are_real_occupied_nights_never_invented(setup):
    app, _fake = setup
    app.dependency_overrides[module.get_current_user] = lambda: _user("hotel-a")
    async with _client(app) as client:
        october = await client.get("/api/sustainability/report", params={"start_date": "2026-10-01", "end_date": "2026-10-31"})
        empty = await client.get("/api/sustainability/report", params={"start_date": "2026-12-01", "end_date": "2026-12-02"})
    assert october.json()["total_room_nights"] == 2           # 1-3 Oct stay; the cancelled one does not count
    assert empty.json()["total_room_nights"] == 0              # audit: 200 invented for two empty days
    assert empty.json()["emissions_per_room_night"] is None


@pytest.mark.asyncio
async def test_a_partial_period_is_prorated_and_says_so(setup):
    """Audit: a one-day report took the whole month's 310 kWh."""
    app, _fake = setup
    app.dependency_overrides[module.get_current_user] = lambda: _user("hotel-a")
    async with _client(app) as client:
        await client.post("/api/sustainability/records", json=RECORD)
        one_day = (await client.get("/api/sustainability/report", params={"start_date": "2026-10-02", "end_date": "2026-10-02"})).json()
        month = (await client.get("/api/sustainability/report", params={"start_date": "2026-10-01", "end_date": "2026-10-31"})).json()
    assert month["total_scope_2"] == round(310 * 0.429, 2) and month["prorated_record_count"] == 0
    assert one_day["total_scope_2"] == round(310 * 0.429 / 31, 2)
    assert one_day["prorated_record_count"] == 1 and "gün oranında" in one_day["allocation"]


@pytest.mark.asyncio
async def test_invalid_periods_are_client_errors(setup):
    app, _fake = setup
    app.dependency_overrides[module.get_current_user] = lambda: _user("hotel-a")
    async with _client(app) as client:
        backwards = await client.get("/api/sustainability/report", params={"start_date": "2026-10-31", "end_date": "2026-10-01"})
        garbage = await client.get("/api/sustainability/report", params={"start_date": "bad", "end_date": "2026-10-01"})
        bad_record = await client.post("/api/sustainability/records", json={**RECORD, "period_end": "2026-09-01"})
        negative = await client.post("/api/sustainability/records", json={**RECORD, "amount": -5})
    assert backwards.status_code == 422 and garbage.status_code == 422
    assert bad_record.status_code == 422 and negative.status_code == 422


def test_month_proration_matches_calendar_days():
    assert (date(2026, 10, 31) - date(2026, 10, 1)).days + 1 == 31
