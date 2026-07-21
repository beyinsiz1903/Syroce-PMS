from unittest.mock import patch, AsyncMock
"""
Test: Overbooking Alert Emission (CM-Hardening Turu #1a, May 2026)
==================================================================

Pinned regression for `core.atomic_booking._emit_overbooking_alert`.

Background:
  CM Sandbox Discovery raporu (P0) — `lock_conflict` event'leri sadece
  `event_timeline`'a yazılıyordu, hiçbir downstream consumer tüketmiyordu.
  OTA-driven overbooking attempt'ler `pending_assignment` kuyruğuna sessizce
  düşüyor, front-desk haberdar olamıyordu. Bu hardening, conflict raise
  edildiği anda `db.notifications` kanalına `overbooking_risk` row'u + best
  effort `AlertDeliveryService.deliver_alert(...)` dispatch ekledi.

Pin'lenen davranış:
  T1: conflict tetiklendiğinde `db.notifications` 'overbooking_risk' row yazıldı
  T2: notification metadata conflict bağlamını taşıyor (oda, gece, conflict_type)
  T3: notification insert hatası booking flow'u BLOCKLAMAZ
       (BookingConflictError yine fırlatılır, fail-safe paterni)
  T4: AlertDeliveryService dispatch hatası booking flow'u BLOCKLAMAZ
       (best-effort çağrı; channel config yoksa skip log)
"""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from core.atomic_booking import (
    BookingConflictError,
    create_booking_atomic,
)
from core.database import db


pytestmark = pytest.mark.asyncio


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


async def _seed_room(tenant_id: str) -> str:
    room_id = f"alert-test-room-{uuid.uuid4().hex[:8]}"
    from core.tenant_db import tenant_context
    with tenant_context(tenant_id):
        await db.rooms.insert_one({
            "id": room_id,
            "tenant_id": tenant_id,
            "room_number": f"AT{uuid.uuid4().hex[:4].upper()}",
            "room_type": "standard",
            "status": "available",
            "created_at": datetime.now(UTC).isoformat(),
        })
    return room_id


async def _cleanup(tenant_id: str, room_id: str, booking_ids: list[str]):
    from core.tenant_db import tenant_context
    with tenant_context(tenant_id):
        await db.rooms.delete_one({"id": room_id, "tenant_id": tenant_id})
        if booking_ids:
            await db.bookings.delete_many({"id": {"$in": booking_ids}, "tenant_id": tenant_id})
            await db.room_night_locks.delete_many({
                "tenant_id": tenant_id,
                "booking_id": {"$in": booking_ids},
            })
        await db.notifications.delete_many({
            "tenant_id": tenant_id,
            "type": "overbooking_risk",
            "metadata.rejected_room_id": room_id,
        })


def _make_booking_doc(*, tenant_id: str, room_id: str, ci: datetime, co: datetime, name: str) -> dict:
    return {
        "id": f"alert-test-booking-{uuid.uuid4().hex[:10]}",
        "tenant_id": tenant_id,
        "room_id": room_id,
        "guest_id": f"alert-test-guest-{uuid.uuid4().hex[:6]}",
        "guest_name": name,
        "check_in": _iso(ci),
        "check_out": _iso(co),
        "status": "confirmed",
        "total_amount": 100,
        "created_at": datetime.now(UTC).isoformat(),
    }


async def test_overbooking_blocked_emits_notification():
    """T1+T2: conflict → notifications.overbooking_risk row + correct metadata."""
    tenant_id = f"alert-test-tenant-{uuid.uuid4().hex[:8]}"
    room_id = await _seed_room(tenant_id)
    booking_ids: list[str] = []

    try:
        ci = datetime.now(UTC) + timedelta(days=400)  # avoid colliding with seed bookings
        co = ci + timedelta(days=2)

        first = _make_booking_doc(tenant_id=tenant_id, room_id=room_id, ci=ci, co=co, name="First")
        await create_booking_atomic(first)
        booking_ids.append(first["id"])

        second = _make_booking_doc(tenant_id=tenant_id, room_id=room_id, ci=ci, co=co, name="Second")
        with pytest.raises(BookingConflictError) as exc_info:
            await create_booking_atomic(second)
        booking_ids.append(second["id"])  # cleanup even though insert was blocked
        assert exc_info.value.conflict_type == "booking"

        # T1: notification row exists for the rejected attempt
        await asyncio.sleep(0.1)  # tiny grace for any pending awaits
        from core.tenant_db import tenant_context
        with tenant_context(tenant_id):
            notif = await db.notifications.find_one({
                "tenant_id": tenant_id,
                "type": "overbooking_risk",
                "metadata.rejected_booking_id": second["id"],
            })
        assert notif is not None, "Expected overbooking_risk notification not written"

        # T2: metadata carries conflict context
        assert notif["severity"] == "warning"
        assert notif["read"] is False
        meta = notif.get("metadata", {})
        assert meta.get("conflict_type") == "booking"
        assert meta.get("rejected_room_id") == room_id
        assert meta.get("conflicting_booking_id") == first["id"]
        assert meta.get("conflict_night")  # truthy ISO date string
    finally:
        await _cleanup(tenant_id, room_id, booking_ids)


async def test_notification_failure_does_not_block_conflict_raise():
    """T3: notifications.insert_one boom → BookingConflictError still raised."""
    tenant_id = f"alert-test-tenant-{uuid.uuid4().hex[:8]}"
    room_id = await _seed_room(tenant_id)
    booking_ids: list[str] = []

    try:
        ci = datetime.now(UTC) + timedelta(days=410)
        co = ci + timedelta(days=2)

        first = _make_booking_doc(tenant_id=tenant_id, room_id=room_id, ci=ci, co=co, name="First")
        await create_booking_atomic(first)
        booking_ids.append(first["id"])

        boom = AsyncMock(side_effect=RuntimeError("simulated mongo down"))
        from core.tenant_db import get_system_db
        sys_db = get_system_db()
        with patch.object(sys_db.notifications, "insert_one", boom):
            second = _make_booking_doc(tenant_id=tenant_id, room_id=room_id, ci=ci, co=co, name="Second")
            with pytest.raises(BookingConflictError):
                await create_booking_atomic(second)
            booking_ids.append(second["id"])
    finally:
        await _cleanup(tenant_id, room_id, booking_ids)


async def test_multi_night_conflict_reports_actual_failed_night():
    """T5 (architect follow-up): for a multi-night attempt that fails on the
    LAST night, `conflict_night` in the notification metadata must be the
    actual failing night — not the first night of the requested range.

    Pattern: pre-book just night N+1, then try to claim nights N..N+2.
    Atomic loop succeeds on N, fails on N+1 → conflict_night must be N+1.
    """
    tenant_id = f"alert-test-tenant-{uuid.uuid4().hex[:8]}"
    room_id = await _seed_room(tenant_id)
    booking_ids: list[str] = []

    try:
        # Anchor far in the future so we don't collide with seed data.
        anchor = datetime.now(UTC).replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=430)
        # Pre-existing booking occupies night N+1 only (1-night stay)
        pre_ci = anchor + timedelta(days=1)
        pre_co = anchor + timedelta(days=2)
        pre = _make_booking_doc(tenant_id=tenant_id, room_id=room_id, ci=pre_ci, co=pre_co, name="Pre")
        await create_booking_atomic(pre)
        booking_ids.append(pre["id"])

        # Conflicting attempt spans nights N, N+1, N+2 → first claims N OK, then N+1 conflicts
        att_ci = anchor
        att_co = anchor + timedelta(days=3)
        attempt = _make_booking_doc(tenant_id=tenant_id, room_id=room_id, ci=att_ci, co=att_co, name="Attempt")
        with patch(
            "core.atomic_booking._find_overlapping_active_booking",
            new=AsyncMock(return_value=None),
        ), pytest.raises(BookingConflictError) as exc_info:
            await create_booking_atomic(attempt)
        booking_ids.append(attempt["id"])

        expected_night = (anchor + timedelta(days=1)).date().isoformat()
        assert exc_info.value.conflicting_nights == [expected_night]

        await asyncio.sleep(0.1)
        from core.tenant_db import tenant_context
        with tenant_context(tenant_id):
            notif = await db.notifications.find_one({
                "tenant_id": tenant_id,
                "type": "overbooking_risk",
                "metadata.rejected_booking_id": attempt["id"],
            })
        assert notif is not None, "Notification missing for multi-night conflict"
        assert notif["metadata"]["conflict_night"] == expected_night, (
            f"conflict_night should be the actual failing night ({expected_night}), "
            f"got {notif['metadata']['conflict_night']}"
        )
    finally:
        await _cleanup(tenant_id, room_id, booking_ids)


async def test_ooo_block_conflict_emits_notification_with_ooo_type():
    """T6 (architect follow-up): OOO blocks share the same lock table.
    A booking attempt over an OOO night must emit a notification with
    `conflict_type='ooo'` so front-desk knows the block source is a
    maintenance/OOO marker, not another guest's booking.
    """
    from core.atomic_booking import OOO_PREFIX

    tenant_id = f"alert-test-tenant-{uuid.uuid4().hex[:8]}"
    room_id = await _seed_room(tenant_id)
    booking_ids: list[str] = []

    anchor = datetime.now(UTC).replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=440)
    night_iso = anchor.date().isoformat()
    ooo_booking_id = f"{OOO_PREFIX}alert-test-{uuid.uuid4().hex[:8]}"

    # Manually plant an OOO lock for one night (mirrors apply_room_block path)
    from core.tenant_db import tenant_context
    with tenant_context(tenant_id):
        await db.room_night_locks.insert_one({
            "tenant_id": tenant_id,
            "room_id": room_id,
            "night_date": night_iso,
            "booking_id": ooo_booking_id,
            "lock_type": "ooo",
            "created_at": datetime.now(UTC).isoformat(),
        })

    try:
        attempt = _make_booking_doc(
            tenant_id=tenant_id, room_id=room_id,
            ci=anchor, co=anchor + timedelta(days=1),
            name="OverlapsOOO",
        )
        with patch(
            "core.atomic_booking._find_overlapping_active_booking",
            new=AsyncMock(return_value=None),
        ), pytest.raises(BookingConflictError) as exc_info:
            await create_booking_atomic(attempt)
        booking_ids.append(attempt["id"])
        assert exc_info.value.conflict_type == "ooo"

        await asyncio.sleep(0.1)
        from core.tenant_db import tenant_context
        with tenant_context(tenant_id):
            notif = await db.notifications.find_one({
                "tenant_id": tenant_id,
                "type": "overbooking_risk",
                "metadata.rejected_booking_id": attempt["id"],
            })
        assert notif is not None
        assert notif["metadata"]["conflict_type"] == "ooo"
        assert notif["metadata"]["conflicting_booking_id"] == ooo_booking_id
        assert "Arıza Bloğu" in notif["message"] or "OOO" in notif["message"]
    finally:
        await db.room_night_locks.delete_many({
            "tenant_id": tenant_id,
            "room_id": room_id,
            "booking_id": ooo_booking_id,
        })
        await _cleanup(tenant_id, room_id, booking_ids)


async def test_alert_delivery_failure_does_not_block_conflict_raise():
    """T4: AlertDeliveryService.deliver_alert boom → BookingConflictError still raised."""
    tenant_id = f"alert-test-tenant-{uuid.uuid4().hex[:8]}"
    room_id = await _seed_room(tenant_id)
    booking_ids: list[str] = []

    try:
        ci = datetime.now(UTC) + timedelta(days=420)
        co = ci + timedelta(days=2)

        first = _make_booking_doc(tenant_id=tenant_id, room_id=room_id, ci=ci, co=co, name="First")
        await create_booking_atomic(first)
        booking_ids.append(first["id"])

        boom = AsyncMock(side_effect=RuntimeError("simulated provider 5xx"))
        with patch(
            "channel_manager.application.alert_delivery_service.AlertDeliveryService.deliver_alert",
            boom,
        ):
            second = _make_booking_doc(tenant_id=tenant_id, room_id=room_id, ci=ci, co=co, name="Second")
            with pytest.raises(BookingConflictError):
                await create_booking_atomic(second)
            booking_ids.append(second["id"])

        # The notification row should still have been written (delivery is the
        # second of the two best-effort writes, not the first).
        from core.tenant_db import tenant_context
        with tenant_context(tenant_id):
            notif = await db.notifications.find_one({
                "tenant_id": tenant_id,
                "type": "overbooking_risk",
                "metadata.rejected_booking_id": second["id"],
            })
        assert notif is not None, "Notification persistence is independent of delivery channel"
    finally:
        await _cleanup(tenant_id, room_id, booking_ids)
