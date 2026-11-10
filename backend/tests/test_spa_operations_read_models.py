from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from domains.spa import router as spa
from tests.test_pos_final_consistency_replica import db  # noqa: F401


class Rows:
    def __init__(self, rows):
        self.rows = rows

    async def __aiter__(self):
        for row in self.rows:
            yield row

    def sort(self, *_):
        return self

    def limit(self, count):
        return Rows(self.rows[:count])


@pytest.mark.parametrize(("busy_resource", "error"), [
    ("therapist", "Uygun terapist bulunamadı"),
    ("room", "Uygun oda bulunamadı"),
])
async def test_automatic_assignment_refuses_to_save_when_a_resource_is_busy(monkeypatch, busy_resource, error):
    service = {"name": "Test hizmeti", "category": "massage", "duration_minutes": 60, "tax_rate": 20, "price": 1500}
    insert = AsyncMock()
    database = SimpleNamespace(
        client=None,
        spa_services=SimpleNamespace(find_one=AsyncMock(return_value=service)),
        spa_therapists=SimpleNamespace(find=Mock(return_value=Rows([{"id": "t"}]))),
        spa_rooms=SimpleNamespace(find=Mock(return_value=Rows([{"id": "r"}]))),
        spa_appointments=SimpleNamespace(insert_one=insert),
    )

    async def conflict(_tenant_id, *, therapist_id, room_id, **_):
        return "Çakışma" if (therapist_id and busy_resource == "therapist") or (room_id and busy_resource == "room") else None

    async def locked(**kwargs):
        return await kwargs["callback"](None)

    monkeypatch.setattr(spa, "require_spa_ops", lambda _: None)
    monkeypatch.setattr(spa, "_ensure_indexes", AsyncMock())
    monkeypatch.setattr(spa, "get_system_db", lambda: database)
    monkeypatch.setattr(spa, "_check_conflict", conflict)
    monkeypatch.setattr(spa, "with_resource_locks", locked)
    appointment = spa.AppointmentIn(service_id="massage", starts_at="2026-11-10T08:05:00Z", guest_name="Sentetik Misafir")
    user = SimpleNamespace(tenant_id="hotel", username="operator")

    with pytest.raises(HTTPException, match=error) as caught:
        await spa.create_appointment(appointment, user)

    assert caught.value.status_code == 409
    insert.assert_not_awaited()


async def test_availability_requires_room_and_therapist_for_the_full_local_shift(monkeypatch):
    service = {"category": "hydro", "duration_minutes": 60, "requires_room_type": "wet_room"}
    therapists = [
        {"id": "t", "name": "Ayşe", "specialties": ["hydro"], "working_days": [7],
         "work_start": "09:30", "work_end": "12:00"},
        {"id": "off", "name": "Deniz", "working_days": [1]},
        {"id": "other", "name": "Ada", "specialties": ["facial"]},
    ]
    appointments = [
        # A room-only record straddling the shift start, stored as BSON.
        {"room_id": "r", "starts_at": datetime(2026, 11, 8, 5, 50, tzinfo=UTC),
         "ends_at": datetime(2026, 11, 8, 7, 0, tzinfo=UTC)},
        # Different offset, same instant as 07:00 UTC. Both resources are free
        # exactly at 10:30 hotel time, before the noon shift boundary.
        {"therapist_id": "t", "starts_at": "2026-11-08T08:00:00+01:00",
         "ends_at": "2026-11-08T08:30:00+01:00"},
    ]
    database = SimpleNamespace(
        tenant_settings=SimpleNamespace(find_one=AsyncMock(return_value={"timezone": "Europe/Istanbul"})),
        spa_services=SimpleNamespace(find_one=AsyncMock(return_value=service)),
        spa_therapists=SimpleNamespace(find=Mock(return_value=Rows(therapists))),
        spa_rooms=SimpleNamespace(find=Mock(return_value=Rows([{"id": "r", "name": "Islak Oda"}]))),
        spa_appointments=SimpleNamespace(find=Mock(return_value=Rows(appointments))),
    )
    monkeypatch.setattr(spa, "get_system_db", lambda: database)
    result = await spa.availability_grid(
        "2026-11-08", "hydro", 30, current_user=SimpleNamespace(tenant_id="hotel"), _feat=None,
    )

    assert result["timezone"] == "Europe/Istanbul"
    assert [row["id"] for row in result["therapists"]] == ["t", "off"]
    assert [slot["starts_at"] for slot in result["slots"] if slot["any_available"]] == [
        "2026-11-08T07:30:00+00:00", "2026-11-08T08:00:00+00:00",
    ]
    assert result["slots"][0]["rooms"] == []
    assert result["slots"][-1]["any_available"] is False
    assert database.spa_rooms.find.call_args.args[0] == {"tenant_id": "hotel", "active": True, "room_type": "wet_room"}
    appointment_scope = database.spa_appointments.find.call_args.args[0]
    assert appointment_scope["tenant_id"] == "hotel"
    assert "cancelled" not in appointment_scope["status"]["$in"]


async def test_guest_history_keeps_same_name_appointments_separate_and_preserves_currency(monkeypatch):
    completed = {"guest_name": "Selin Kaya", "status": "completed", "price": 100}
    rows = [
        {**completed, "id": "try", "guest_id": "selin", "currency": "TRY"},
        {**completed, "id": "eur", "guest_id": "selin", "currency": "EUR"},
        {**completed, "id": "walkin", "guest_id": None, "currency": "TRY"},
    ]
    find = Mock(side_effect=[Rows(rows), Rows(rows[:2])])
    monkeypatch.setattr(spa, "get_system_db", lambda: SimpleNamespace(spa_appointments=SimpleNamespace(find=find)))
    user = SimpleNamespace(tenant_id="hotel", role="front_desk")

    search = await spa.search_guest_history("Selin Kaya", current_user=user, _feat=None)
    assert [row["id"] for row in search["appointments"]] == ["try", "eur", "walkin"]
    query, projection = find.call_args.args
    assert query["tenant_id"] == "hotel"
    assert query["guest_name"]["$regex"].startswith("^Selin")
    assert "guest_phone" not in projection

    profile = await spa.guest_history("selin", current_user=user, _feat=None)
    assert find.call_args.args[0] == {"tenant_id": "hotel", "guest_id": "selin"}
    assert profile["total_visits"] == 2
    assert profile["total_spend"] is None
    assert profile["service_value_by_currency"] == {"EUR": 100, "TRY": 100}


async def test_conflict_guard_matches_real_bson_and_iso_offset_timestamps(db, monkeypatch):  # noqa: F811
    await db.spa_appointments.insert_many([
        {"tenant_id": "hotel", "status": "scheduled", "therapist_id": "t",
         "starts_at": "2026-11-08T10:30:00+03:00", "ends_at": "2026-11-08T11:30:00+03:00"},
        {"tenant_id": "hotel", "status": "in_progress", "room_id": "r",
         "starts_at": datetime(2026, 11, 8, 7, tzinfo=UTC), "ends_at": datetime(2026, 11, 8, 8, tzinfo=UTC)},
    ])
    monkeypatch.setattr(spa, "get_system_db", lambda: db)
    start = datetime(2026, 11, 8, 7, 30, tzinfo=UTC)
    end = datetime(2026, 11, 8, 8, 30, tzinfo=UTC)

    assert (await spa._check_conflict("hotel", therapist_id="t", room_id=None, start=start, end=end)).startswith("Terapist")
    assert (await spa._check_conflict("hotel", therapist_id=None, room_id="r", start=start, end=end)).startswith("Oda")
    assert await spa._check_conflict("hotel", therapist_id="t", room_id="r", start=end,
                                     end=datetime(2026, 11, 8, 9, tzinfo=UTC)) is None
    assert await spa._check_conflict("other", therapist_id="t", room_id="r", start=start, end=end) is None
