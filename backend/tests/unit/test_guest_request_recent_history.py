from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.guest.messaging import guest_requests as gr
from domains.guest.messaging import guest_requests_router as routes


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, field, direction):
        self.rows.sort(key=lambda row: row[field], reverse=direction == -1)
        return self

    def limit(self, limit):
        self.rows = self.rows[:limit]
        return self

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield row
        return iterate()


@pytest.mark.asyncio
@pytest.mark.parametrize("latest,expected", [(False, [0, 1, 2]), (True, [4, 5, 6])])
async def test_room_history_window_keeps_scope_and_chronological_order(monkeypatch, latest, expected):
    rows = [{"id": str(i), "room_id": "room-201", "sender_type": "guest", "body": f"Talep {i}",
             "created_at": datetime(2026, 10, 17, tzinfo=UTC) + timedelta(minutes=i)} for i in range(7)]

    def find(query):
        assert query == {"tenant_id": "hotel-1", "room_id": "room-201", "booking_id": "booking-1"}
        return Cursor(list(rows))

    monkeypatch.setattr(gr, "raw_db", {gr.GR_COLL: SimpleNamespace(find=find)})
    messages = await gr.get_thread_messages("hotel-1", "room-201", booking_id="booking-1", limit=3, latest=latest)
    assert [message["id"] for message in messages] == [str(i) for i in expected]


@pytest.mark.asyncio
async def test_staff_endpoint_requests_the_latest_messages(monkeypatch):
    read = AsyncMock(return_value=[{"room_number": "201"}])
    monkeypatch.setattr(gr, "get_thread_messages", read)
    result = await routes.get_guest_request_thread("room-201", SimpleNamespace(id="staff-1", tenant_id="hotel-1"))
    read.assert_awaited_once_with("hotel-1", "room-201", viewer_user_id="staff-1", latest=True)
    assert result["room_number"] == "201"
