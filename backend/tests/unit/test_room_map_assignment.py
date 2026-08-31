import pytest
from fastapi import HTTPException

from routers.room_map import _resolve_room_map_guest_name, _validate_quick_assignment


def test_room_map_guest_name_prefers_authoritative_guest_record():
    assert _resolve_room_map_guest_name(
        {"guest_id": "guest-1", "guest_name": "Eski Rezervasyon Adi"},
        {"name": "Guncel Misafir"},
    ) == "Guncel Misafir"


def test_room_map_guest_name_falls_back_to_booking_snapshot():
    assert _resolve_room_map_guest_name(
        {"guest_id": "guest-2", "guest_name": "Suleyman Cakiroglu"},
        {},
    ) == "Suleyman Cakiroglu"


def test_room_map_guest_name_never_exposes_generic_placeholder():
    name = _resolve_room_map_guest_name(
        {"guest_id": "7e5ad2a0-a123-4567-8901-0cde1234abcd", "guest_name": "C4"},
        {},
    )
    assert name == "Walk-in Misafir #ABCD"


def test_quick_assignment_rejects_dirty_or_blocked_target_rooms():
    for status in ("dirty", "cleaning", "maintenance", "out_of_order", "blocked"):
        with pytest.raises(HTTPException) as exc:
            _validate_quick_assignment(
                {"room_type": "standard"},
                {"room_number": "202", "room_type": "standard", "status": status},
            )
        assert exc.value.status_code == 409


def test_quick_assignment_rejects_room_type_change_that_needs_price_decision():
    with pytest.raises(HTTPException) as exc:
        _validate_quick_assignment(
            {"room_type": "standard"},
            {"room_number": "301", "room_type": "suite", "status": "clean"},
        )

    assert exc.value.status_code == 409
    assert "Farkli oda tipine" in str(exc.value.detail)


def test_quick_assignment_accepts_clean_same_type_room():
    assert _validate_quick_assignment(
        {"room_type": "Standard"},
        {"room_number": "203", "room_type": "standard", "status": "clean"},
    ) is None
