"""
Reservation No-show E2E v2
==========================

State-machine-driven no-show lifecycle coverage.

Pattern: requests.Session over live HTTP + sync pymongo for side-channel
verification. CI-safe (mirrors test_reservation_lifecycle_e2e.py v1).

Scope (v2):
    T1. confirmed booking -> no_show succeeds + audit
    T2. guaranteed booking -> no_show succeeds
    T3. double no-show rejected (terminal state guard)
    T4. checked_in -> no-show blocked (transition guard)
    T5. cancelled -> no-show blocked (terminal state guard)
    T6. pending -> no-show blocked (transition guard: pending lacks no_show target)
    T7. cross-tenant no-show denied -> SKIPPED with TODO (v1.1 fixture)

Out of scope:
    - Legacy /api/reservations/{id}/mark-noshow path (direct DB write, BYPASS state machine)
    - Outbox event existence (handle_no_show does not emit outbox; tracked separately)
    - Idempotency-Key header (endpoint contract does not require it)
    - No-show fee charging (folio refund hat, v3)

Canonical path: POST /api/pms-core/no-show body={booking_id}
References:
    backend/routers/pms_hardening.py            (POST /no-show at L268)
    backend/modules/pms_core/reservation_state_machine.py
        VALID_TRANSITIONS, handle_no_show
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


class TestReservationNoShowE2E:
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
                db.idempotency_keys.delete_many(
                    {**tenant_filter, "idempotency_key": {"$in": self._used_idem_keys}}
                )
            client.close()
        except Exception:
            pass

    def _idem_key(self) -> str:
        key = f"idem-{uuid.uuid4()}"
        self._used_idem_keys.append(key)
        return key

    def _clean_locks(self, room_id: str, check_in: str, check_out: str):
        try:
            client, db = _sync_db()
            ci_date = check_in.split("T")[0]
            co_date = check_out.split("T")[0]
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

    def _set_booking_field(self, booking_id: str, fields: dict):
        client, db = _sync_db()
        try:
            db.bookings.update_one(
                {"id": booking_id, "tenant_id": self.tenant_id},
                {"$set": fields},
            )
        finally:
            client.close()

    def _seed_entities(self) -> tuple[str, dict]:
        guests = self.session.get(f"{BASE_URL}/api/pms/guests?limit=5").json()
        rooms = self.session.get(f"{BASE_URL}/api/pms/rooms?limit=10").json()
        if not guests or not rooms:
            pytest.skip("Need at least one guest and one room in demo tenant")
        return guests[0]["id"], rooms[0]

    def _build_payload(self, guest_id: str, room_id: str) -> dict:
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
            "special_requests": f"noshow-e2e-{uuid.uuid4().hex[:8]}",
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

    def _no_show(self, booking_id: str):
        # NoShowRequest schema: {booking_id} only — no reason field, no Idempotency-Key
        return self.session.post(
            f"{BASE_URL}/api/pms-core/no-show",
            json={"booking_id": booking_id},
        )

    def _cancel(self, booking_id: str, reason: str = "noshow-e2e setup cancel"):
        return self.session.post(
            f"{BASE_URL}/api/pms-core/cancel",
            json={"booking_id": booking_id, "reason": reason},
        )

    def _assert_state_machine_400(self, resp, expected_keyword: str):
        """Assert a state-machine rejection (400) carrying expected keyword."""
        assert resp.status_code == 400, resp.text
        body = resp.json()
        detail = body.get("detail", body)
        if isinstance(detail, dict):
            assert detail.get("success") is False
            assert expected_keyword.lower() in str(detail.get("error", "")).lower(), (
                f"expected '{expected_keyword}' in error, got: {detail}"
            )
        else:
            assert expected_keyword.lower() in str(detail).lower(), (
                f"expected '{expected_keyword}' in detail, got: {detail}"
            )

    # ── T1: confirmed -> no_show succeeds + audit ────────────────────────

    def test_mark_confirmed_as_noshow_succeeds_with_audit(self):
        guest_id, room = self._seed_entities()
        booking = self._create_booking(room, guest_id)
        # Sanity: created bookings default to confirmed/pending; force confirmed
        # to make this test deterministic regardless of any future default drift.
        self._set_booking_field(booking["id"], {"status": "confirmed"})

        resp = self._no_show(booking["id"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("success") is True
        assert body.get("booking_id") == booking["id"]

        # Persisted state
        persisted = self._find_one(
            "bookings", {"id": booking["id"], "tenant_id": self.tenant_id}
        )
        assert persisted is not None
        assert persisted["status"] == "no_show"
        assert persisted.get("no_show_at"), "no_show_at timestamp not populated"
        assert persisted.get("no_show_marked_by"), "no_show_marked_by not populated"

        # Audit trail entry
        audit = self._find_one(
            "pms_audit_trail",
            {
                "tenant_id": self.tenant_id,
                "entity_id": booking["id"],
                "action": "no_show",
            },
        )
        assert audit is not None, "no_show audit trail entry missing"
        assert audit.get("previous_status") == "confirmed"
        assert audit.get("new_status") == "no_show"
        assert audit.get("entity_type") == "reservation"

    # ── T2: guaranteed -> no_show succeeds ───────────────────────────────

    def test_mark_guaranteed_as_noshow_succeeds(self):
        guest_id, room = self._seed_entities()
        booking = self._create_booking(room, guest_id)

        original = self._find_one(
            "bookings", {"id": booking["id"], "tenant_id": self.tenant_id}
        )
        original_status = (original or {}).get("status", "confirmed")

        self._set_booking_field(booking["id"], {"status": "guaranteed"})
        try:
            resp = self._no_show(booking["id"])
            assert resp.status_code == 200, resp.text
            assert resp.json().get("success") is True

            persisted = self._find_one(
                "bookings", {"id": booking["id"], "tenant_id": self.tenant_id}
            )
            assert persisted["status"] == "no_show"

            audit = self._find_one(
                "pms_audit_trail",
                {
                    "tenant_id": self.tenant_id,
                    "entity_id": booking["id"],
                    "action": "no_show",
                },
            )
            assert audit is not None
            assert audit.get("previous_status") == "guaranteed"
            assert audit.get("new_status") == "no_show"
        finally:
            # Booking is now no_show (terminal); cleanup will delete it.
            # Restore only if transition didn't take effect.
            current = self._find_one(
                "bookings", {"id": booking["id"], "tenant_id": self.tenant_id}
            )
            if current and current.get("status") != "no_show":
                self._set_booking_field(booking["id"], {"status": original_status})

    # ── T3: double no-show rejected ──────────────────────────────────────

    def test_double_noshow_is_rejected(self):
        guest_id, room = self._seed_entities()
        booking = self._create_booking(room, guest_id)
        self._set_booking_field(booking["id"], {"status": "confirmed"})

        first = self._no_show(booking["id"])
        assert first.status_code == 200, first.text

        second = self._no_show(booking["id"])
        # no_show is terminal; transition no_show -> no_show is invalid
        # (validate_transition treats current==new as no_change, but
        # VALID_TRANSITIONS[no_show] == [], so any non-equal target fails.
        # The implementation routes through validate_transition; same-state
        # returns "no_change" which still proceeds, so the actual invariant
        # tested here is the state-machine consistency for terminal states.)
        # Empirically the handler returns success=False for terminal states
        # because the underlying transition guard catches the second call.
        self._assert_state_machine_400(second, "no_show")

    # ── T4: checked_in -> no-show blocked ────────────────────────────────

    def test_noshow_blocked_when_checked_in(self):
        guest_id, room = self._seed_entities()
        booking = self._create_booking(room, guest_id)

        original = self._find_one(
            "bookings", {"id": booking["id"], "tenant_id": self.tenant_id}
        )
        original_status = (original or {}).get("status", "confirmed")

        self._set_booking_field(booking["id"], {"status": "checked_in"})
        try:
            resp = self._no_show(booking["id"])
            self._assert_state_machine_400(resp, "checked_in")
        finally:
            self._set_booking_field(booking["id"], {"status": original_status})

    # ── T5: cancelled -> no-show blocked ─────────────────────────────────

    def test_noshow_blocked_when_cancelled(self):
        guest_id, room = self._seed_entities()
        booking = self._create_booking(room, guest_id)

        # Use the canonical cancel path so the booking arrives at 'cancelled'
        # via real production flow (state machine), not via a forced mutation.
        cancel_resp = self._cancel(booking["id"], reason="noshow-e2e T5 setup")
        assert cancel_resp.status_code == 200, cancel_resp.text

        resp = self._no_show(booking["id"])
        self._assert_state_machine_400(resp, "cancelled")

    # ── T6: pending -> no-show blocked ───────────────────────────────────

    def test_noshow_blocked_when_pending(self):
        guest_id, room = self._seed_entities()
        booking = self._create_booking(room, guest_id)

        original = self._find_one(
            "bookings", {"id": booking["id"], "tenant_id": self.tenant_id}
        )
        original_status = (original or {}).get("status", "confirmed")

        # State machine: VALID_TRANSITIONS["pending"] = ["confirmed", "guaranteed", "cancelled"]
        # — no_show is NOT in pending's allowed targets.
        self._set_booking_field(booking["id"], {"status": "pending"})
        try:
            resp = self._no_show(booking["id"])
            self._assert_state_machine_400(resp, "pending")
        finally:
            self._set_booking_field(booking["id"], {"status": original_status})

    # ── T7: cross-tenant isolation (deferred to v1.1) ────────────────────

    def test_cross_tenant_noshow_denied(self):
        pytest.skip(
            "Second tenant fixture not available yet; "
            "add in v1.1 tenant-isolation E2E"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
