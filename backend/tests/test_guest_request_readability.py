import pytest

from domains.guest.messaging import guest_requests
from domains.guest.messaging.guest_requests import (
    _is_generic_request_body,
    _service_label_from_request,
)
from domains.guest.qr_constants import map_legacy_routing
from domains.guest.qr_request_description import generate_deterministic_description


def test_one_tap_description_uses_readable_service_label():
    description = generate_deterministic_description(
        "one_tap",
        {},
        None,
        {"tr": "Oda temizliği", "en": "Room cleaning"},
        {},
        "tr",
        "en",
    )

    assert description == "Oda temizliği"
    assert "Talep alındı" not in description


def test_description_keeps_service_label_with_request_details():
    description = generate_deterministic_description(
        "quantity",
        {"quantity": 2},
        "Lütfen saat 14.00'ten sonra",
        {"tr": "Ekstra banyo havlusu"},
        {},
        "tr",
        "tr",
    )

    assert description.splitlines() == [
        "Ekstra banyo havlusu",
        "Miktar: 2",
        "Not: Lütfen saat 14.00'ten sonra",
    ]


@pytest.mark.parametrize(
    ("service_code", "department_code", "expected"),
    [
        ("housekeeping.room_cleaning", "housekeeping", ("cleaning", "rooms")),
        ("housekeeping.extra_bath_towel", "housekeeping", ("towels", "rooms")),
        ("technical.wifi_problem", "technical", ("wifi", "technical")),
        ("reception.wake_up_call", "reception", ("reception", "other")),
        ("custom.housekeeping", "housekeeping", ("cleaning", "rooms")),
    ],
)
def test_catalogue_requests_get_meaningful_staff_categories(
    service_code, department_code, expected
):
    assert map_legacy_routing(service_code, department_code) == expected


def test_service_label_prefers_turkish_catalogue_snapshot():
    request_doc = {
        "language": "en",
        "title": "Room cleaning — Oda 202",
        "catalogue_snapshot": {
            "labels": {"en": "Room cleaning", "tr": "Oda temizliği"}
        },
    }

    assert _service_label_from_request(request_doc) == "Oda temizliği"


def test_service_label_falls_back_to_clean_title():
    request_doc = {
        "title": "Bagaj yardımı — Oda 202",
        "catalogue_snapshot": {"labels": {}},
    }

    assert _service_label_from_request(request_doc) == "Bagaj yardımı"


def test_only_legacy_placeholder_is_treated_as_generic():
    assert _is_generic_request_body("Talep alındı.") is True
    assert _is_generic_request_body("Oda temizliği") is False


class _AsyncCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def __aiter__(self):
        async def iterate():
            for doc in self._docs:
                yield doc

        return iterate()


class _Collection:
    def __init__(self, docs):
        self._docs = docs

    def find(self, *_args, **_kwargs):
        return _AsyncCursor(self._docs)


@pytest.mark.asyncio
async def test_existing_generic_message_is_enriched_for_staff(monkeypatch):
    fake_db = {
        "guest_room_messages": _Collection(
            [
                {
                    "id": "message-1",
                    "tenant_id": "tenant-1",
                    "room_id": "room-202",
                    "sender_type": "guest",
                    "body": "Talep alındı.",
                    "request_id": "request-1",
                    "read_by": [],
                }
            ]
        ),
        "qr_requests": _Collection(
            [
                {
                    "_id": "request-1",
                    "tenant_id": "tenant-1",
                    "language": "tr",
                    "catalogue_snapshot": {
                        "labels": {"tr": "Oda temizliği", "en": "Room cleaning"}
                    },
                }
            ]
        ),
    }
    monkeypatch.setattr(guest_requests, "raw_db", fake_db)

    messages = await guest_requests.get_thread_messages(
        "tenant-1",
        "room-202",
        viewer_user_id="staff-1",
    )

    assert messages[0]["body"] == "Oda temizliği"
