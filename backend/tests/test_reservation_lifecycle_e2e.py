"""
Reservation Lifecycle E2E v1
============================

Core PMS lifecycle coverage: create -> modify -> cancel, plus negative paths.

Pattern: requests.Session over live HTTP + sync pymongo for side-channel
verification. CI-safe (no Motor / asyncio loop bindings; mirrors
test_create_reservation_bridge.py which is the reference live-bridge pattern).

Scope (v1):
    T1. create -> modify dates + room -> reread verify
    T2. create -> cancel -> reread verify + audit/outbox existence
    T3. double cancel rejected (terminal state guard)
    T4. checked_in cancel blocked (state machine guard)
    T5. modify idempotency: same-key/same-body replay + same-key/different-body 409
    T6. cross-tenant isolation -> SKIPPED with TODO (v1.1 will add second-tenant fixture)

Out of scope (future hats):
    no-show conversion, folio refund/void, rate recalculation on date change,
    room-change alternative path, multi-room/group cascade cancels.

References:
    backend/routers/pms_bookings.py             (POST/PUT /api/pms/bookings)
    backend/routers/pms_hardening.py            (POST /api/pms-core/cancel)
    backend/modules/pms_core/reservation_state_machine.py
    backend/modules/reservations/services/{create,update}_reservation_service.py
"""
import os
import random
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import requests
from pymongo import MongoClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms")
DB_NAME = os.environ.get("DB_NAME", "hotel_pms")
BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE_URL, reason="VITE_BACKEND_URL not set")


def _sync_db():
    client = MongoClient(MONGO_URL)
    return client, client[DB_NAME]


class TestReservationLifecycleE2E:
    @pytest.fixture(autouse=True)
    def setup(self):
        if not BASE_URL:
            pytest.skip("VITE_BACKEND_URL missing")

        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
        )
        if login.status_code != 200:
            pytest.skip(f"Login failed: {login.status_code}")
        body = login.json()
        self.token = body["access_token"]
        self.tenant_id = body["user"]["tenant_id"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        self._created_bookings: list[str] = []
        self._used_idem_keys: list[str] = []
        yield
        # Best-effort cleanup; test failures must not be hidden by cleanup errors
        self._cleanup_bookings()

    # ── helpers ──────────────────────────────────────────────────────────

    def _cleanup_bookings(self):
        if not self._created_bookings and not self._used_idem_keys:
            return
        try:
            client, db = _sync_db()
            tenant_filter = {"tenant_id": self.tenant_id}
            if self._created_bookings:
                ids = self._created_bookings
                db.bookings.delete_many({**tenant_filter, "id": {"$in": ids}})
                db.room_night_locks.delete_many(
                    {**tenant_filter, "booking_id": {"$in": ids}}
                )
                db.outbox_events.delete_many(
                    {**tenant_filter, "reservation_id": {"$in": ids}}
                )
                db.outbox_events.delete_many(
                    {**tenant_filter, "entity_id": {"$in": ids}}
                )
                db.audit_logs.delete_many(
                    {**tenant_filter, "entity_id": {"$in": ids}}
                )
                db.pms_audit_trail.delete_many(
                    {**tenant_filter, "entity_id": {"$in": ids}}
                )
            if self._used_idem_keys:
                # Idempotency lock docs carry tenant_id + idempotency_key fields
                # (see modules/reservations/repository.py acquire_idempotency_lock)
                db.idempotency_keys.delete_many(
                    {**tenant_filter, "idempotency_key": {"$in": self._used_idem_keys}}
                )
            client.close()
        except Exception:
            pass  # cleanup best-effort

    def _idem_key(self) -> str:
        """Generate a unique Idempotency-Key and track it for teardown cleanup."""
        key = f"idem-{uuid.uuid4()}"
        self._used_idem_keys.append(key)
        return key

    def _clean_locks(self, room_id: str, check_in: str, check_out: str):
        try:
            client, db = _sync_db()
            ci_date = check_in.split("T")[0]
            co_date = check_out.split("T")[0]
            # Room-night locks are stored on the half-open interval
            # [check_in_date, check_out_date); checkout day must NOT be deleted.
            # Tenant-scoped to avoid clobbering parallel-tenant locks if
            # room IDs ever collide across tenants in shared CI fixtures.
            db.room_night_locks.delete_many(
                {
                    "tenant_id": self.tenant_id,
                    "room_id": room_id,
                    "night_date": {"$gte": ci_date, "$lt": co_date},
                }
            )
            client.close()
        except Exception:
            pass

    def _find_one(self, collection: str, query: dict) -> dict | None:
        client, db = _sync_db()
        try:
            return db[collection].find_one(query, {"_id": 0})
        finally:
            client.close()

    def _count(self, collection: str, query: dict) -> int:
        client, db = _sync_db()
        try:
            return db[collection].count_documents(query)
        finally:
            client.close()

    def _set_booking_field(self, booking_id: str, fields: dict):
        client, db = _sync_db()
        try:
            db.bookings.update_one(
                {"id": booking_id, "tenant_id": self.tenant_id},
                {"$set": fields},
            )
        finally:
            client.close()

    def _seed_entities(self) -> tuple[str, dict, dict]:
        guests = self.session.get(f"{BASE_URL}/api/pms/guests?limit=5").json()
        rooms = self.session.get(f"{BASE_URL}/api/pms/rooms?limit=20").json()
        if not guests or len(rooms) < 2:
            pytest.skip("Need at least one guest and two rooms in demo tenant")
        return guests[0]["id"], rooms[0], rooms[1]

    def _build_payload(self, guest_id: str, room_id: str) -> dict:
        # Offset 3000-6000 days into the future to avoid rate_calendar / lock
        # collisions with realistic fixture data; mirrors the bridge test pattern.
        offset = 3000 + random.randint(0, 3000)
        check_in = (
            datetime.now(UTC).date() + timedelta(days=offset)
        ).isoformat() + "T14:00:00Z"
        check_out = (
            datetime.now(UTC).date() + timedelta(days=offset + 2)
        ).isoformat() + "T12:00:00Z"
        return {
            "guest_id": guest_id,
            "room_id": room_id,
            "check_in": check_in,
            "check_out": check_out,
            "adults": 2,
            "children": 0,
            "children_ages": [],
            "guests_count": 2,
            "total_amount": 1200.0,
            "special_requests": f"lifecycle-e2e-{uuid.uuid4().hex[:8]}",
        }

    def _create_booking(self, room: dict, guest_id: str) -> dict:
        payload = self._build_payload(guest_id, room["id"])
        self._clean_locks(room["id"], payload["check_in"], payload["check_out"])
        resp = self.session.post(
            f"{BASE_URL}/api/pms/bookings",
            json=payload,
            headers={"Idempotency-Key": self._idem_key()},
        )
        assert resp.status_code == 200, f"create failed: {resp.status_code} {resp.text}"
        booking = resp.json()
        self._created_bookings.append(booking["id"])
        return booking

    def _cancel(self, booking_id: str, reason: str = "lifecycle-e2e cancel"):
        return self.session.post(
            f"{BASE_URL}/api/pms-core/cancel",
            json={"booking_id": booking_id, "reason": reason},
        )

    # ── T1: create -> modify dates + room -> reread verify ───────────────

    def test_create_then_modify_dates_and_room(self):
        guest_id, original_room, updated_room = self._seed_entities()
        booking = self._create_booking(original_room, guest_id)

        # Build new dates (shifted +1 day) on a different room
        original_offset_ci = booking["check_in"][:10]
        new_ci_date = (
            datetime.fromisoformat(original_offset_ci).date() + timedelta(days=1)
        )
        new_check_in = new_ci_date.isoformat() + "T14:00:00Z"
        new_check_out = (new_ci_date + timedelta(days=2)).isoformat() + "T12:00:00Z"
        self._clean_locks(updated_room["id"], new_check_in, new_check_out)

        new_special = f"lifecycle-modified-{uuid.uuid4().hex[:8]}"
        modify_resp = self.session.put(
            f"{BASE_URL}/api/pms/bookings/{booking['id']}",
            json={
                "room_id": updated_room["id"],
                "check_in": new_check_in,
                "check_out": new_check_out,
                "special_requests": new_special,
            },
            headers={"Idempotency-Key": self._idem_key()},
        )
        assert modify_resp.status_code == 200, modify_resp.text
        updated = modify_resp.json()

        assert updated["id"] == booking["id"]
        assert updated["room_id"] == updated_room["id"]
        assert updated["special_requests"] == new_special
        # Date round-trip — backend may normalise format; compare date prefix only
        assert updated["check_in"][:10] == new_check_in[:10]
        assert updated["check_out"][:10] == new_check_out[:10]

        # Re-read via Mongo side-channel (canonical state); GET list is paginated
        # and may not return future-dated bookings in the default window.
        persisted = self._find_one(
            "bookings", {"id": booking["id"], "tenant_id": self.tenant_id}
        )
        assert persisted is not None
        assert persisted["room_id"] == updated_room["id"]
        assert persisted["special_requests"] == new_special
        assert persisted.get("status") in ("confirmed", "pending", "guaranteed")

    # ── T2: create -> cancel -> reread + audit + outbox ──────────────────

    def test_cancel_active_reservation_emits_audit_and_outbox(self):
        guest_id, original_room, _ = self._seed_entities()
        booking = self._create_booking(original_room, guest_id)

        cancel_reason = f"lifecycle-e2e-cancel-{uuid.uuid4().hex[:6]}"
        resp = self._cancel(booking["id"], reason=cancel_reason)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("success") is True
        assert body.get("booking_id") == booking["id"]

        # Re-read: cancelled status persisted
        persisted = self._find_one(
            "bookings", {"id": booking["id"], "tenant_id": self.tenant_id}
        )
        assert persisted is not None
        assert persisted["status"] == "cancelled"
        assert persisted.get("cancellation_reason") == cancel_reason

        # Audit trail: state machine writes to pms_audit_trail with action='cancellation'
        audit = self._find_one(
            "pms_audit_trail",
            {
                "tenant_id": self.tenant_id,
                "entity_id": booking["id"],
                "action": "cancellation",
            },
        )
        assert audit is not None, "cancellation audit trail entry missing"
        assert audit.get("new_status") == "cancelled"
        assert audit.get("previous_status") in (
            "pending",
            "confirmed",
            "guaranteed",
        )

        # Outbox: BOOKING_CANCELLED = "booking.cancelled.v1" enqueued
        outbox = self._find_one(
            "outbox_events",
            {
                "tenant_id": self.tenant_id,
                "entity_id": booking["id"],
                "event_type": "booking.cancelled.v1",
            },
        )
        assert outbox is not None, "booking.cancelled.v1 outbox event missing"

    # ── T3: double-cancel rejected ───────────────────────────────────────

    def test_double_cancel_is_rejected(self):
        guest_id, original_room, _ = self._seed_entities()
        booking = self._create_booking(original_room, guest_id)

        first = self._cancel(booking["id"], reason="first cancel")
        assert first.status_code == 200, first.text

        second = self._cancel(booking["id"], reason="second cancel")
        # NON_CANCELLABLE_STATES includes 'cancelled' -> handler returns
        # success=False which is mapped to HTTP 400 by the route
        assert second.status_code == 400, second.text
        body = second.json()
        # Detail may be a dict ({"success": false, "error": "..."}) or a plain string
        detail = body.get("detail", body)
        if isinstance(detail, dict):
            assert detail.get("success") is False
            assert "cancelled" in str(detail.get("error", "")).lower()
        else:
            assert "cancelled" in str(detail).lower()

    # ── T4: checked_in cancel blocked ────────────────────────────────────

    def test_cancel_blocked_when_checked_in(self):
        guest_id, original_room, _ = self._seed_entities()
        booking = self._create_booking(original_room, guest_id)

        # Force booking into checked_in via Mongo side-channel; the production
        # check-in path triggers room/folio side effects we don't want to drag
        # into a cancel-guard test. We're only validating the state machine
        # rejects cancel from a non-cancellable state.
        original = self._find_one(
            "bookings", {"id": booking["id"], "tenant_id": self.tenant_id}
        )
        original_status = (original or {}).get("status", "confirmed")

        self._set_booking_field(booking["id"], {"status": "checked_in"})
        try:
            resp = self._cancel(booking["id"], reason="should be blocked")
            assert resp.status_code == 400, resp.text
            body = resp.json()
            detail = body.get("detail", body)
            if isinstance(detail, dict):
                assert detail.get("success") is False
                assert "checked_in" in str(detail.get("error", "")).lower()
            else:
                assert "checked_in" in str(detail).lower()
        finally:
            # Restore the captured pre-mutation status so subsequent teardown
            # operates on a realistic state (avoids brittle hardcoded default).
            self._set_booking_field(booking["id"], {"status": original_status})

    # ── T5: modify idempotency replay + drift 409 ────────────────────────

    def test_modify_idempotency_same_key_same_body_replays(self):
        guest_id, original_room, updated_room = self._seed_entities()
        booking = self._create_booking(original_room, guest_id)

        idem_key = self._idem_key()
        special = f"lifecycle-idem-{uuid.uuid4().hex[:8]}"
        payload = {
            "room_id": updated_room["id"],
            "special_requests": special,
        }
        # Pre-clean updated_room locks for the existing booking dates
        self._clean_locks(updated_room["id"], booking["check_in"], booking["check_out"])

        first = self.session.put(
            f"{BASE_URL}/api/pms/bookings/{booking['id']}",
            json=payload,
            headers={"Idempotency-Key": idem_key},
        )
        assert first.status_code == 200, first.text

        second = self.session.put(
            f"{BASE_URL}/api/pms/bookings/{booking['id']}",
            json=payload,
            headers={"Idempotency-Key": idem_key},
        )
        assert second.status_code == 200, second.text
        # Replay should return the same response (idempotency cache hit)
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["room_id"] == first.json()["room_id"]

        # Outbox: only ONE reservation.modified.v1 event for this booking
        modified_count = self._count(
            "outbox_events",
            {
                "reservation_id": booking["id"],
                "event_type": "reservation.modified.v1",
            },
        )
        assert modified_count == 1, (
            f"expected exactly 1 reservation.modified.v1 event, got {modified_count}"
        )

    def test_modify_idempotency_same_key_different_body_returns_409(self):
        guest_id, original_room, updated_room = self._seed_entities()
        booking = self._create_booking(original_room, guest_id)

        idem_key = self._idem_key()
        self._clean_locks(updated_room["id"], booking["check_in"], booking["check_out"])

        first = self.session.put(
            f"{BASE_URL}/api/pms/bookings/{booking['id']}",
            json={
                "room_id": updated_room["id"],
                "special_requests": f"lifecycle-drift-A-{uuid.uuid4().hex[:6]}",
            },
            headers={"Idempotency-Key": idem_key},
        )
        assert first.status_code == 200, first.text

        # Same key, different payload -> 409 Conflict
        second = self.session.put(
            f"{BASE_URL}/api/pms/bookings/{booking['id']}",
            json={
                "room_id": updated_room["id"],
                "special_requests": f"lifecycle-drift-B-{uuid.uuid4().hex[:6]}",
            },
            headers={"Idempotency-Key": idem_key},
        )
        assert second.status_code == 409, second.text
        assert "idempotency" in second.text.lower()

    # ── T6: cross-tenant isolation (deferred to v1.1) ────────────────────

    def test_cross_tenant_modify_and_cancel_denied(self):
        pytest.skip(
            "Second tenant fixture not available yet; "
            "add in v1.1 tenant-isolation E2E"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
