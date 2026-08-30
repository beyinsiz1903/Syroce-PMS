from collections.abc import AsyncIterator

import pytest

from domains.pms.frontdesk_service import FrontdeskService


class _Cursor(AsyncIterator):
    def __init__(self, rows):
        self._rows = iter(rows)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._rows)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _Collection:
    def __init__(self, rows):
        self.rows = rows
        self.query = None

    def find(self, query, _projection):
        self.query = query
        return _Cursor(self.rows)


class _Db:
    def __init__(self):
        self.guests = _Collection([
            {"id": "guest-1", "name": "Misafir", "phone": "SYR1:ciphertext", "email": "SYR1:mail"},
        ])
        self.rooms = _Collection([
            {"id": "room-1", "room_number": "101", "room_type": "standard", "status": "occupied"},
        ])


@pytest.mark.asyncio
async def test_enrichment_decrypts_guest_pii_and_scopes_related_records_to_tenant(monkeypatch):
    monkeypatch.setattr(
        "security.encrypted_lookup.decrypt_guest_doc",
        lambda doc: {**doc, "phone": "+905551112233", "email": "guest@example.com"},
    )
    service = FrontdeskService.__new__(FrontdeskService)
    service._db = _Db()

    rows = await service._enrich_bookings(
        [{"id": "booking-1", "guest_id": "guest-1", "room_id": "room-1"}],
        "tenant-1",
    )

    assert service._db.guests.query == {"tenant_id": "tenant-1", "id": {"$in": ["guest-1"]}}
    assert service._db.rooms.query == {"tenant_id": "tenant-1", "id": {"$in": ["room-1"]}}
    assert rows[0]["guest_phone"] == "+905551112233"
    assert rows[0]["guest_email"] == "guest@example.com"
    assert rows[0]["room_number"] == "101"
