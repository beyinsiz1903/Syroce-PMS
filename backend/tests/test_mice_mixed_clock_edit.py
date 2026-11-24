"""Single-endpoint browser edits retain the property clock and availability guards."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers import mice


@pytest.fixture
def clock(monkeypatch):
    settings = AsyncMock(return_value={"timezone": "Europe/Istanbul"})
    monkeypatch.setattr(mice, "get_system_db", lambda: SimpleNamespace(
        tenant_settings=SimpleNamespace(find_one=settings)))
    return settings


def event(start, end, *, agenda=False, **extra):
    row = {"starts_at": start, "ends_at": end}
    row.update({"title": "Session"} if agenda else {"space_id": "hall"})
    return mice.EventIn(name="Synthetic", client_name="Synthetic", start_date="2026-11-12",
                        end_date="2026-11-12", **{"agenda" if agenda else "space_bookings": [row]}, **extra)


@pytest.mark.asyncio
@pytest.mark.parametrize("agenda", [False, True])
@pytest.mark.parametrize("start,end", [
    ("2026-11-12T10:00:00+03:00", "2026-11-12T13:00"),
    ("2026-11-12T09:00", "2026-11-12T12:00:00+03:00"),
    ("2026-11-12T07:00:00Z", "2026-11-12T13:00"),
])
async def test_one_changed_endpoint_uses_property_zone(clock, agenda, start, end):
    normalized = await mice._property_clock(event(start, end, agenda=agenda), "A")
    row = (normalized.agenda if agenda else normalized.space_bookings)[0]
    assert row.starts_at.isoformat().endswith("+03:00")
    assert row.ends_at.isoformat().endswith("+03:00")
    assert row.ends_at > row.starts_at
    if start.endswith("Z"):
        assert row.starts_at.hour == 10  # absolute instant survives, no browser/OS zone


@pytest.mark.asyncio
@pytest.mark.parametrize("agenda", [False, True])
@pytest.mark.parametrize("end", ["2026-11-12T09:00", "2026-11-12T10:00"])
async def test_mixed_pair_still_rejects_nonpositive_duration(clock, agenda, end):
    with pytest.raises(HTTPException) as error:
        await mice._property_clock(event("2026-11-12T10:00:00+03:00", end, agenda=agenda), "A")
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_mixed_pair_collision_checked_after_normalization(clock):
    body = event("2026-11-12T10:00:00+03:00", "2026-11-12T13:00")
    body.space_bookings.append(mice.SpaceBookingIn(space_id="hall",
        starts_at="2026-11-12T12:00", ends_at="2026-11-12T14:00"))
    with pytest.raises(HTTPException, match="çakışıyor"):
        await mice._property_clock(body, "A")
    body.space_bookings[1].starts_at = mice.instant("2026-11-12T13:00")
    assert len((await mice._property_clock(body, "A")).space_bookings) == 2


@pytest.mark.asyncio
async def test_mixed_pair_still_checks_property_calendar(clock):
    with pytest.raises(HTTPException, match="tarih aralığında"):
        await mice._property_clock(event("2026-11-12T10:00:00+03:00", "2026-11-13T01:00"), "A")


@pytest.mark.asyncio
@pytest.mark.parametrize("day,wall", [("2026-03-29", "02:30"), ("2026-10-25", "02:30")])
async def test_mixed_pair_does_not_bypass_dst_guard(clock, day, wall):
    clock.return_value = {"timezone": "Europe/Berlin"}
    body = mice.EventIn(name="Synthetic", client_name="Synthetic", start_date=day, end_date=day,
        space_bookings=[{"space_id": "hall", "starts_at": f"{day}T00:00:00Z", "ends_at": f"{day}T{wall}"}])
    with pytest.raises(HTTPException, match="Yaz/kış"):
        await mice._property_clock(body, "A")
