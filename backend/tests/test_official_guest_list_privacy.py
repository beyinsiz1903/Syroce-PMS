from types import SimpleNamespace

import pytest

from routers.reports_pkg import dashboard_lists


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    async def to_list(self, _length=None, **_kwargs):
        return list(self._docs)


class _Collection:
    def __init__(self, docs):
        self._docs = docs

    def find(self, *_args, **_kwargs):
        return _Cursor(self._docs)


@pytest.mark.asyncio
async def test_official_guest_list_masks_all_sensitive_fields_without_pii_grant(monkeypatch):
    database = SimpleNamespace(
        bookings=_Collection(
            [
                {
                    "id": "booking-1",
                    "tenant_id": "tenant-1",
                    "guest_id": "guest-1",
                    "room_id": "room-1",
                    "status": "checked_in",
                    "check_in": "2026-09-23",
                    "check_out": "2026-09-25",
                    "checked_in_at": "2026-09-23T14:00:00+03:00",
                    "billing_tax_number": "1234567890",
                    "billing_address": "Sensitive address",
                    "company_id": "company-secret",
                }
            ]
        ),
        rooms=_Collection([{"id": "room-1", "room_number": "201"}]),
        booking_guests=_Collection([]),
        guests=_Collection(
            [
                {
                    "id": "guest-1",
                    "name": "Test Guest",
                    "id_number": "11111111111",
                    "passport_number": "P1234567",
                    "date_of_birth": "1990-01-02",
                }
            ]
        ),
    )
    monkeypatch.setattr(dashboard_lists, "db", database)
    monkeypatch.setattr("security.encrypted_lookup.decrypt_guest_doc", lambda doc: doc)
    user = SimpleNamespace(
        tenant_id="tenant-1",
        role="front_desk",
        granted_permissions=["view_guest_list"],
    )

    result = await dashboard_lists.get_official_guest_list(
        date="2026-09-23",
        current_user=user,
        _=None,
        _permission=None,
    )

    row = result["rows"][0]
    assert row["national_id"] != "11111111111"
    assert row["passport_number"] != "P1234567"
    assert row["date_of_birth"] != "1990-01-02"
    assert row["billing_tax_number"] != "1234567890"
    assert row["billing_address"] != "Sensitive address"
    assert row["company_id"] != "company-secret"
