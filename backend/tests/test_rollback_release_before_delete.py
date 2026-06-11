"""Task #437 — Telafi (rollback) sırasında kilit-önce-sil-sonra invariantı.

Kök neden (f107faaf vakası): çok-odalı saga telafisi ve unmatched-hold serbest
bırakma yolları booking satırını ÖNCE silip SONRA gece kilitlerini bırakıyor ve
release başarısızlığını sessizce yutuyordu → booking yok (404) + kilit kalır
(orphan) → boş oda yanlışlıkla 'dolu' görünür, her rezervasyon 409 ile reddedilir.

Bu testler düzeltilmiş sözleşmeyi sabitler:

  * Çok-odalı _rollback_group: release patlarsa booking SİLİNMEZ ve kilit
    sahipsiz (orphan) kalmaz.
  * unmatched-hold release: release patlarsa hold booking SİLİNMEZ (delete_hold
    istense bile) → kilit sahipsiz kalmaz.

Doktrin: rastgele test tenant + tam temizlik (pilot_drift=0), gerçek Atlas DB,
fake-green YOK, assertion gevşetme YOK.
"""
from __future__ import annotations

import uuid

import pytest

import core.atomic_booking as atomic_booking
from core.database import db
from models.schemas import User

TEST_TENANT = f"test-rollback437-{uuid.uuid4().hex[:8]}"
CHECK_IN = "2031-05-10"
CHECK_OUT = "2031-05-12"  # 2 gece: 10, 11


async def _cleanup():
    await db.bookings.delete_many({"tenant_id": TEST_TENANT})
    await db.room_night_locks.delete_many({"tenant_id": TEST_TENANT})
    await db.folios.delete_many({"tenant_id": TEST_TENANT})
    await db.guests.delete_many({"tenant_id": TEST_TENANT})
    await db.rooms.delete_many({"tenant_id": TEST_TENANT})
    await db.notifications.delete_many({"tenant_id": TEST_TENANT})


@pytest.fixture(autouse=True)
async def _around():
    await _cleanup()
    yield
    await _cleanup()


class _StubRequest:
    """Route yalnızca request.headers.get(...) çağırır."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}


def _user() -> User:
    return User(
        id=str(uuid.uuid4()),
        tenant_id=TEST_TENANT,
        email="rollback437@test.example.com",
        name="Rollback Tester",
        role="admin",
    )


@pytest.mark.asyncio
async def test_multiroom_rollback_keeps_booking_when_release_fails(monkeypatch):
    """İkinci oda çakışırsa grup telafisi çalışır; release patlarsa ilk odanın
    booking'i SİLİNMEZ ve kilitleri sahipsiz (orphan) kalmaz."""
    from routers import pms_bookings

    room1 = f"room1-{uuid.uuid4().hex[:6]}"
    room2 = f"room2-{uuid.uuid4().hex[:6]}"
    await db.rooms.insert_many([
        {"id": room1, "tenant_id": TEST_TENANT, "room_number": "101"},
        {"id": room2, "tenant_id": TEST_TENANT, "room_number": "102"},
    ])

    # room2 için çakışan aktif booking → ikinci create_booking_atomic 409 verir.
    conflicting_id = str(uuid.uuid4())
    await db.bookings.insert_one({
        "id": conflicting_id,
        "tenant_id": TEST_TENANT,
        "room_id": room2,
        "check_in": f"{CHECK_IN}T00:00:00+00:00",
        "check_out": f"{CHECK_OUT}T00:00:00+00:00",
        "status": "confirmed",
    })

    # release_booking_nights telafi sırasında patlasın.
    async def _boom(*_a, **_k):
        raise RuntimeError("simulated release failure")

    monkeypatch.setattr(atomic_booking, "release_booking_nights", _boom)

    payload = pms_bookings.MultiRoomBookingCreate(
        guest=pms_bookings.GuestCreate(
            name="Test Guest", phone="5550000437", id_number="11111111111"
        ),
        arrival_date=CHECK_IN,
        departure_date=CHECK_OUT,
        rooms=[
            {"room_id": room1, "adults": 1, "total_amount": 100.0},
            {"room_id": room2, "adults": 1, "total_amount": 100.0},
        ],
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await pms_bookings.create_multi_room_booking(
            payload=payload, request=_StubRequest(), current_user=_user(), _perm=None
        )
    assert exc.value.status_code == 409

    # İlk odanın booking'i SİLİNMEMELİ (release patladı → orphan önlenir).
    room1_bookings = await db.bookings.find(
        {"tenant_id": TEST_TENANT, "room_id": room1}
    ).to_list(10)
    assert len(room1_bookings) == 1, "release patlayınca booking silinmemeli"
    surviving_id = room1_bookings[0]["id"]

    # room1 kilitleri hâlâ sahipli olmalı (sahibi = hayatta kalan booking).
    locks = await db.room_night_locks.find(
        {"tenant_id": TEST_TENANT, "room_id": room1}
    ).to_list(10)
    assert locks, "room1 kilitleri var olmalı"
    for lk in locks:
        assert lk["booking_id"] == surviving_id, "kilit sahipsiz (orphan) olmamalı"


@pytest.mark.asyncio
async def test_multiroom_rollback_deletes_booking_when_release_ok(monkeypatch):
    """Karşıt durum: release başarılıysa telafi booking'i SİLER ve kilit kalmaz."""
    from routers import pms_bookings

    room1 = f"room1-{uuid.uuid4().hex[:6]}"
    room2 = f"room2-{uuid.uuid4().hex[:6]}"
    await db.rooms.insert_many([
        {"id": room1, "tenant_id": TEST_TENANT, "room_number": "201"},
        {"id": room2, "tenant_id": TEST_TENANT, "room_number": "202"},
    ])
    conflicting_id = str(uuid.uuid4())
    await db.bookings.insert_one({
        "id": conflicting_id,
        "tenant_id": TEST_TENANT,
        "room_id": room2,
        "check_in": f"{CHECK_IN}T00:00:00+00:00",
        "check_out": f"{CHECK_OUT}T00:00:00+00:00",
        "status": "confirmed",
    })

    payload = pms_bookings.MultiRoomBookingCreate(
        guest=pms_bookings.GuestCreate(
            name="Test Guest", phone="5550000438", id_number="22222222222"
        ),
        arrival_date=CHECK_IN,
        departure_date=CHECK_OUT,
        rooms=[
            {"room_id": room1, "adults": 1, "total_amount": 100.0},
            {"room_id": room2, "adults": 1, "total_amount": 100.0},
        ],
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await pms_bookings.create_multi_room_booking(
            payload=payload, request=_StubRequest(), current_user=_user(), _perm=None
        )
    assert exc.value.status_code == 409

    # release başarılı → ilk oda booking'i temizlendi, kilit kalmadı.
    room1_bookings = await db.bookings.find(
        {"tenant_id": TEST_TENANT, "room_id": room1}
    ).to_list(10)
    assert room1_bookings == [], "release başarılıyken booking silinmeli"
    locks = await db.room_night_locks.find(
        {"tenant_id": TEST_TENANT, "room_id": room1}
    ).to_list(10)
    assert locks == [], "release başarılıyken kilit kalmamalı"


@pytest.mark.asyncio
async def test_unmatched_hold_release_keeps_booking_when_release_fails(monkeypatch):
    """unmatched-hold serbest bırakma: release patlarsa delete_hold istense bile
    hold booking SİLİNMEZ → kilit sahipsiz (orphan) kalmaz."""
    from domains.channel_manager.providers import unmatched_hold

    ext = f"EXT-{uuid.uuid4().hex[:10]}"
    res = await unmatched_hold.create_unmatched_reservation_hold(
        provider="exely",
        tenant_id=TEST_TENANT,
        external_id=ext,
        check_in=CHECK_IN,
        check_out=CHECK_OUT,
        guest_name="Hold Guest",
        room_type_code="DLX",
        rate_plan_code="BAR",
        total_amount=1000.0,
    )
    booking_id = res["booking_id"]
    assert booking_id

    async def _boom(*_a, **_k):
        raise RuntimeError("simulated release failure")

    monkeypatch.setattr(unmatched_hold, "release_booking_nights", _boom)

    out = await unmatched_hold.release_unmatched_reservation_hold(
        tenant_id=TEST_TENANT,
        external_id=ext,
        delete_hold=True,
        reason="rebind",
    )
    assert out["released"] is False

    # Hold booking SİLİNMEMELİ.
    still = await db.bookings.find_one({"id": booking_id, "tenant_id": TEST_TENANT})
    assert still is not None, "release patlayınca hold booking silinmemeli"

    # Kilitler hâlâ sahipli (orphan değil).
    locks = await db.room_night_locks.find(
        {"tenant_id": TEST_TENANT, "booking_id": booking_id}
    ).to_list(10)
    assert locks, "hold kilitleri var olmalı ve sahipli kalmalı"
