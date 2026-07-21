"""
Task #394 — Unmatched OTA Reservation Hold (shared helper) test suite.
=====================================================================

Eslestirilemeyen OTA rezervasyonlari icin tutma (hold) + envanter kilidi +
ACIL alarm + rebind/iptal serbest birakma davranisini dogrular.

Doktrin: pilot_drift=0 (rastgele test tenant + tam temizlik), fake-green YOK,
assertion gevsetme YOK, gercek DB uzerinde (Atlas) calisir.
"""
import uuid

import pytest

from core.database import db
from core.tenant_db import tenant_context
from domains.channel_manager.providers.unmatched_hold import (
    ALARM_TITLE,
    UNMATCHED_HOLD_LOCK_TYPE,
    UNMATCHED_HOLD_SOURCE,
    create_unmatched_reservation_hold,
    release_unmatched_reservation_hold,
)

TEST_TENANT = f"test-unmatched-{uuid.uuid4().hex[:8]}"
CHECK_IN = "2031-03-10"
CHECK_OUT = "2031-03-13"  # 3 gece: 10, 11, 12
EXPECTED_NIGHTS = 3


async def _cleanup():
    with tenant_context(TEST_TENANT):
                await db.bookings.delete_many({"tenant_id": TEST_TENANT})
    with tenant_context(TEST_TENANT):
                await db.room_night_locks.delete_many({"tenant_id": TEST_TENANT})
    with tenant_context(TEST_TENANT):
                await db.notifications.delete_many({"tenant_id": TEST_TENANT})
    with tenant_context(TEST_TENANT):
                await db.rooms.delete_many({"tenant_id": TEST_TENANT})


@pytest.fixture(autouse=True)
async def _around():
    await _cleanup()
    yield
    await _cleanup()


def _ext_id() -> str:
    return f"EXT-{uuid.uuid4().hex[:10]}"


async def test_create_hold_creates_booking_locks_and_alarm():
    ext = _ext_id()
    res = await create_unmatched_reservation_hold(
        provider="exely",
        tenant_id=TEST_TENANT,
        external_id=ext,
        check_in=CHECK_IN,
        check_out=CHECK_OUT,
        guest_name="Ahmet Yilmaz",
        room_type_code="DLX",
        rate_plan_code="BAR",
        total_amount=4500.0,
    )
    assert res["created"] is True
    assert res["idempotent"] is False
    booking_id = res["booking_id"]
    assert booking_id

    with tenant_context(TEST_TENANT):
                booking = await db.bookings.find_one({"id": booking_id, "tenant_id": TEST_TENANT})
    assert booking is not None
    # Hold dogru sekilde isaretli: oda atanmamis, action-needed, otomatik kabul YOK
    assert booking["room_id"] is None
    assert booking["status"] == "pending_mapping"
    assert booking["booking_source"] == UNMATCHED_HOLD_SOURCE
    assert booking["action_needed"] is True
    assert booking["external_reservation_id"] == ext
    # Gercek oda tipi mislabel edilmemis ("Standard" YOK)
    assert booking["room_type"] is None
    # check_booking_source_exists duplicate kisa-devresini tetiklememeli:
    # source.external_reservation_id BILEREK yok.
    assert "external_reservation_id" not in booking.get("source", {})

    # Sentinel kilitler: gece sayisi kadar, sentinel oda kimligiyle
    with tenant_context(TEST_TENANT):
                locks = await db.room_night_locks.find(
                {"tenant_id": TEST_TENANT, "booking_id": booking_id}
                ).to_list(50)
    assert len(locks) == EXPECTED_NIGHTS
    assert all(lk["lock_type"] == UNMATCHED_HOLD_LOCK_TYPE for lk in locks)
    assert all(lk["room_id"] == f"ota-unmatched::exely::{ext}" for lk in locks)

    # ACIL alarm: kalici in-app bildirim, baslik TAM eslesme + dedup_key
    with tenant_context(TEST_TENANT):
                notif = await db.notifications.find_one(
                {"tenant_id": TEST_TENANT, "dedup_key": f"unmatched_mapping_{ext}"}
                )
    assert notif is not None
    assert notif["title"] == ALARM_TITLE
    assert notif["title"] == "ACİL: EŞLEŞMEYEN REZERVASYON - AKSİYON BEKLİYOR"
    assert notif["priority"] == "high"


async def test_create_hold_is_idempotent():
    ext = _ext_id()
    first = await create_unmatched_reservation_hold(
        provider="hotelrunner", tenant_id=TEST_TENANT, external_id=ext,
        check_in=CHECK_IN, check_out=CHECK_OUT, guest_name="A B",
    )
    second = await create_unmatched_reservation_hold(
        provider="hotelrunner", tenant_id=TEST_TENANT, external_id=ext,
        check_in=CHECK_IN, check_out=CHECK_OUT, guest_name="A B",
    )
    assert first["created"] is True
    assert second["created"] is False
    assert second["idempotent"] is True
    assert second["booking_id"] == first["booking_id"]

    # Tek booking, tek bildirim (alarm tekrarsiz)
    with tenant_context(TEST_TENANT):
                bookings = await db.bookings.find(
                {"tenant_id": TEST_TENANT, "external_reservation_id": ext,
                "booking_source": UNMATCHED_HOLD_SOURCE}
                ).to_list(10)
    assert len(bookings) == 1
    with tenant_context(TEST_TENANT):
                notifs = await db.notifications.find(
                {"tenant_id": TEST_TENANT, "dedup_key": f"unmatched_mapping_{ext}"}
                ).to_list(10)
    assert len(notifs) == 1


async def test_release_rebind_deletes_hold_and_locks():
    ext = _ext_id()
    created = await create_unmatched_reservation_hold(
        provider="exely", tenant_id=TEST_TENANT, external_id=ext,
        check_in=CHECK_IN, check_out=CHECK_OUT, guest_name="C D",
    )
    booking_id = created["booking_id"]

    rel = await release_unmatched_reservation_hold(
        tenant_id=TEST_TENANT, external_id=ext,
        reason="mapping_resolved", delete_hold=True,
    )
    assert rel["released"] is True
    assert rel["deleted"] is True
    assert rel["nights_released"] == EXPECTED_NIGHTS

    # Rebind: tutma kaydi + sentinel kilitler tamamen silinmeli (cift sayim yok)
    with tenant_context(TEST_TENANT):
        assert await db.bookings.find_one({"id": booking_id, "tenant_id": TEST_TENANT}) is None
    with tenant_context(TEST_TENANT):
                remaining = await db.room_night_locks.count_documents(
                {"tenant_id": TEST_TENANT, "booking_id": booking_id}
                )
    assert remaining == 0


async def test_release_cancel_marks_cancelled_and_frees_locks():
    ext = _ext_id()
    created = await create_unmatched_reservation_hold(
        provider="exely", tenant_id=TEST_TENANT, external_id=ext,
        check_in=CHECK_IN, check_out=CHECK_OUT, guest_name="E F",
    )
    booking_id = created["booking_id"]

    rel = await release_unmatched_reservation_hold(
        tenant_id=TEST_TENANT, external_id=ext,
        reason="ota_cancelled", delete_hold=False,
    )
    assert rel["released"] is True
    assert rel["deleted"] is False

    # Iptal: tutma cancelled isaretlenir (audit izi kalir), kilitler serbest
    with tenant_context(TEST_TENANT):
                booking = await db.bookings.find_one({"id": booking_id, "tenant_id": TEST_TENANT})
    assert booking is not None
    assert booking["status"] == "cancelled"
    assert booking["action_needed"] is False
    with tenant_context(TEST_TENANT):
                remaining = await db.room_night_locks.count_documents(
                {"tenant_id": TEST_TENANT, "booking_id": booking_id}
                )
    assert remaining == 0


async def test_release_noop_when_no_hold():
    rel = await release_unmatched_reservation_hold(
        tenant_id=TEST_TENANT, external_id=_ext_id(), delete_hold=False,
    )
    assert rel["released"] is False
    assert rel["booking_id"] is None


async def test_hold_not_seen_as_duplicate_booking_source():
    """Hold, check_booking_source_exists duplicate kisa-devresini tetiklememeli;
    aksi halde import bridge rebind'i atlayip gercek booking olusturmaz."""
    from core.import_decision import check_booking_source_exists

    ext = _ext_id()
    await create_unmatched_reservation_hold(
        provider="exely", tenant_id=TEST_TENANT, external_id=ext,
        check_in=CHECK_IN, check_out=CHECK_OUT, guest_name="G H",
    )
    found = await check_booking_source_exists(TEST_TENANT, "exely", ext)
    assert found is None


async def test_sentinel_locks_do_not_reduce_real_room_type_availability():
    """En kritik invariant: sentinel kilitler gercek bir oda tipinin sellable
    sayisini AZALTMAMALI (room_id gercek odalar arasinda degil)."""
    from core.room_type_inventory_service import compute_room_type_inventory

    # 2 gercek "DELUXE" odasi seed et
    for _ in range(2):
        with tenant_context(TEST_TENANT):
                    await db.rooms.insert_one({
                    "id": str(uuid.uuid4()),
                    "tenant_id": TEST_TENANT,
                    "room_type": "DELUXE",
                    "is_active": True,
                    })

    night = "2031-03-11"  # hold penceresi icinde
    before = await compute_room_type_inventory(TEST_TENANT, night)
    deluxe_before = next((r for r in before if r["room_type"] == "DELUXE"), None)
    assert deluxe_before is not None
    assert deluxe_before["sellable"] == 2

    # Hold olustur (sentinel kilitler bu gecede aktif)
    await create_unmatched_reservation_hold(
        provider="exely", tenant_id=TEST_TENANT, external_id=_ext_id(),
        check_in=CHECK_IN, check_out=CHECK_OUT, guest_name="I J",
        room_type_code="DELUXE",
    )

    after = await compute_room_type_inventory(TEST_TENANT, night)
    deluxe_after = next((r for r in after if r["room_type"] == "DELUXE"), None)
    assert deluxe_after is not None
    # Sentinel kilit gercek oda tipine bagli olmadigi icin sellable degismez.
    assert deluxe_after["sellable"] == 2
    assert deluxe_after["locked_booking"] == 0
    assert deluxe_after["locked_hold"] == 0

@pytest.mark.asyncio
async def test_check_booking_source_exists_tenant_isolation():
    """Ayni ext_id ile olusturulmus kayit diger tenant'tan bulunamamali."""
    from core.import_decision import check_booking_source_exists
    ext = f"EXT-ISO-{uuid.uuid4().hex[:6]}"
    
    # 1) Tenant A'da booking olustur
    with tenant_context("TENANT_A"):
        await db.bookings.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": "TENANT_A",
            "source": {
                "provider": "exely",
                "external_reservation_id": ext
            },
            "status": "confirmed"
        })
    
    # 2) Tenant A'da bulundugunu dogrula
    found_a = await check_booking_source_exists("TENANT_A", "exely", ext)
    assert found_a is not None
    
    # 3) Tenant B'de (farkli tenant) ayni ext_id bulunmamali
    found_b = await check_booking_source_exists("TENANT_B", "exely", ext)
    assert found_b is None
    
    # Cleanup
    with tenant_context("TENANT_A"):
        await db.bookings.delete_many({"tenant_id": "TENANT_A", "external_reservation_id": ext})


@pytest.mark.asyncio
async def test_compute_room_type_inventory_tenant_isolation():
    """Tenant A'daki kilitler/odalar Tenant B envanterini etkilememeli."""
    from core.room_type_inventory_service import compute_room_type_inventory
    night = "2031-05-15"
    
    # 0) Cleanup
    with tenant_context("TENANT_A"):
        await db.rooms.delete_many({"tenant_id": "TENANT_A"})
        await db.room_night_locks.delete_many({"tenant_id": "TENANT_A"})
    with tenant_context("TENANT_B"):
        await db.rooms.delete_many({"tenant_id": "TENANT_B"})
        
    # 1) Tenant A ve Tenant B'ye oda ekle
    with tenant_context("TENANT_A"):
        await db.rooms.insert_one({
            "id": "room-a1", "tenant_id": "TENANT_A", "room_type": "STD", "is_active": True
        })
        # Tenant A'daki odanin uzerinde kilit
        await db.room_night_locks.insert_one({
            "tenant_id": "TENANT_A",
            "room_id": "room-a1",
            "night_date": night,
            "booking_id": "booking-a",
            "lock_type": "booking"
        })
        
    with tenant_context("TENANT_B"):
        await db.rooms.insert_one({
            "id": "room-b1", "tenant_id": "TENANT_B", "room_type": "STD", "is_active": True
        })
        # Tenant B'deki odanin uzerinde kilit YOK

    # 2) Hesaplamalari kontrol et
    inv_a = await compute_room_type_inventory("TENANT_A", night)
    inv_b = await compute_room_type_inventory("TENANT_B", night)
    
    # Tenant A'daki oda kilitli, available 0
    a_std = next((x for x in inv_a if x["room_type"] == "STD"), None)
    assert a_std is not None
    assert a_std["sellable"] == 0
    
    # Tenant B'deki oda kilitli degil, available 1 (Tenant A'dan etkilenmedi)
    b_std = next((x for x in inv_b if x["room_type"] == "STD"), None)
    assert b_std is not None
    assert b_std["sellable"] == 1
    
    # Cleanup
    with tenant_context("TENANT_A"):
        await db.rooms.delete_many({"tenant_id": "TENANT_A"})
        await db.room_night_locks.delete_many({"tenant_id": "TENANT_A"})
    with tenant_context("TENANT_B"):
        await db.rooms.delete_many({"tenant_id": "TENANT_B"})
