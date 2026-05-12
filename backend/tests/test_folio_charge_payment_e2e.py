"""
Folio Charge / Payment / Refund / Void E2E v3
==============================================

Canonical FolioHardeningService coverage via /api/pms-core/folio/*.

Pattern: requests.Session over live HTTP + sync pymongo for side-channel
verification. CI-safe (mirrors test_reservation_lifecycle_e2e.py v1 +
test_reservation_noshow_e2e.py v2).

Scope (v3) — 9 tests:
    T1. charge increases balance + audit
    T2. payment decreases balance + audit
    T3. refund increases balance (negative payment) + audit
    T4. void charge recalculates balance (charge effect undone)
    T5. void payment recalculates balance (payment effect undone)
    T6. double void charge rejected (already-voided guard)
    T7. charge on closed folio blocked (status guard)
    T8. payment on closed folio blocked (status guard)
    T9. refund on closed folio blocked (status guard — gap closed May 2026)
    T10. void charge on closed folio blocked (status guard)
    T11. void payment on closed folio blocked (status guard)
    T12. refund blocked for all non-open folio statuses [closed/transferred/voided]
        Parametrize across every non-open FolioStatus value to pin guard
        symmetry across the full status set (production hardening, May 2026).

Out of scope:
    - /api/folio-ledger/* (alternative immutable ledger path)
    - /api/frontdesk/folio/* (UI helper path)
    - /api/reservations/{id}/record-payment etc. (legacy booking-id path)
    - Split folio (split, split-by-amount) — separate v4 hat
    - City ledger transfer
    - Tax breakdown (read-only)
    - Group folio / multi-window folio
    - Outbox events (FolioHardeningService does not emit outbox)
    - Idempotency-Key header (endpoint contract does not require it)
    - Negative-amount tests (Pydantic schema-level validation, not lifecycle)
    - Cross-tenant (deferred to v1.1 tenant-isolation hat)

Canonical endpoints exercised:
    POST /api/pms-core/folio/charge        (ChargePostRequest)
    POST /api/pms-core/folio/payment       (PaymentPostRequest)
    POST /api/pms-core/folio/refund        (RefundRequest)
    POST /api/pms-core/folio/void-charge   (VoidRequest)
    POST /api/pms-core/folio/void-payment  (VoidRequest)

References:
    backend/routers/pms_hardening.py                         (L341..L398)
    backend/modules/pms_core/folio_hardening_service.py      (FolioHardeningService)
    backend/routers/pms_bookings.py                          (auto-creates open folio at L860+)
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

# Float tolerance for monetary assertions
EPS = 0.01

pytestmark = pytest.mark.skipif(not BASE_URL, reason="VITE_BACKEND_URL not set")


def _sync_db():
    client = MongoClient(MONGO_URL)
    return client, client[DB_NAME]


class TestFolioChargePaymentE2E:
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
        self._cleanup()

    # ── helpers ──────────────────────────────────────────────────────────

    def _cleanup(self):
        if not self._created_bookings and not self._used_idem_keys:
            return
        try:
            client, db = _sync_db()
            tenant_filter = {"tenant_id": self.tenant_id}
            if self._created_bookings:
                ids = self._created_bookings
                # Resolve folio_ids for these bookings before deleting bookings
                folio_ids = [
                    f["id"]
                    for f in db.folios.find(
                        {**tenant_filter, "booking_id": {"$in": ids}}, {"id": 1}
                    )
                ]
                db.bookings.delete_many({**tenant_filter, "id": {"$in": ids}})
                db.folios.delete_many({**tenant_filter, "booking_id": {"$in": ids}})
                if folio_ids:
                    db.folio_charges.delete_many(
                        {**tenant_filter, "folio_id": {"$in": folio_ids}}
                    )
                    db.payments.delete_many(
                        {**tenant_filter, "folio_id": {"$in": folio_ids}}
                    )
                    # Audit rows for charges/payments/refunds use the
                    # transaction id as entity_id and link the folio via
                    # metadata.folio_id — purge both shapes to avoid
                    # long-run audit residue.
                    db.pms_audit_trail.delete_many(
                        {**tenant_filter, "entity_id": {"$in": folio_ids}}
                    )
                    db.pms_audit_trail.delete_many(
                        {**tenant_filter, "metadata.folio_id": {"$in": folio_ids}}
                    )
                # Belt-and-suspenders: also clean by booking_id
                db.folio_charges.delete_many(
                    {**tenant_filter, "booking_id": {"$in": ids}}
                )
                db.payments.delete_many(
                    {**tenant_filter, "booking_id": {"$in": ids}}
                )
                db.room_night_locks.delete_many(
                    {**tenant_filter, "booking_id": {"$in": ids}}
                )
                db.outbox_events.delete_many(
                    {**tenant_filter, "reservation_id": {"$in": ids}}
                )
                db.outbox_events.delete_many(
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

    def _count(self, collection: str, query: dict) -> int:
        client, db = _sync_db()
        try:
            return db[collection].count_documents(query)
        finally:
            client.close()

    def _set_folio_field(self, folio_id: str, fields: dict):
        client, db = _sync_db()
        try:
            db.folios.update_one(
                {"id": folio_id, "tenant_id": self.tenant_id}, {"$set": fields}
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
            "special_requests": f"folio-e2e-{uuid.uuid4().hex[:8]}",
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

    def _create_booking_with_folio(self) -> tuple[dict, dict]:
        """Create a booking and return (booking_dict, folio_dict).
        Booking creation auto-opens a folio (pms_bookings.py L860+); we read
        it back from Mongo and assert it exists open with balance 0.
        """
        guest_id, room = self._seed_entities()
        booking = self._create_booking(room, guest_id)
        folio = self._find_one(
            "folios", {"booking_id": booking["id"], "tenant_id": self.tenant_id}
        )
        assert folio is not None, "expected auto-created folio for new booking"
        assert folio.get("status") == "open", f"new folio should be open, got {folio.get('status')}"
        return booking, folio

    def _post_charge(self, folio_id: str, booking_id: str, amount: float,
                     description: str = "Minibar", category: str = "minibar") -> requests.Response:
        return self.session.post(
            f"{BASE_URL}/api/pms-core/folio/charge",
            json={
                "folio_id": folio_id,
                "booking_id": booking_id,
                "category": category,
                "description": description,
                "amount": amount,
                "quantity": 1.0,
                "tax_rate": 0.0,
            },
        )

    def _post_payment(self, folio_id: str, booking_id: str, amount: float,
                      method: str = "cash") -> requests.Response:
        return self.session.post(
            f"{BASE_URL}/api/pms-core/folio/payment",
            json={
                "folio_id": folio_id,
                "booking_id": booking_id,
                "amount": amount,
                "method": method,
                "payment_type": "final",
            },
        )

    def _post_refund(self, folio_id: str, booking_id: str, amount: float,
                     reason: str = "test refund", method: str = "cash") -> requests.Response:
        return self.session.post(
            f"{BASE_URL}/api/pms-core/folio/refund",
            json={
                "folio_id": folio_id,
                "booking_id": booking_id,
                "amount": amount,
                "reason": reason,
                "method": method,
            },
        )

    def _void_charge(self, charge_id: str, reason: str = "test void") -> requests.Response:
        return self.session.post(
            f"{BASE_URL}/api/pms-core/folio/void-charge",
            json={"charge_id": charge_id, "reason": reason},
        )

    def _void_payment(self, payment_id: str, reason: str = "test void") -> requests.Response:
        return self.session.post(
            f"{BASE_URL}/api/pms-core/folio/void-payment",
            json={"payment_id": payment_id, "reason": reason},
        )

    def _read_balance(self, folio_id: str) -> float:
        f = self._find_one("folios", {"id": folio_id, "tenant_id": self.tenant_id})
        assert f is not None, f"folio {folio_id} not found"
        return float(f.get("balance", 0) or 0)

    def _assert_audit(self, folio_id: str, action: str, min_count: int = 1):
        n = self._count(
            "pms_audit_trail",
            {"tenant_id": self.tenant_id, "entity_id": folio_id, "action": action},
        )
        # Some actions (charge_voided/payment_voided) log against the entity_id of
        # the charge/payment, not the folio. For folio-anchored actions
        # (charge_posted/payment_posted/refund_posted) the metadata.folio_id is
        # used; the audit row's entity_id is the charge/payment/refund id.
        # So the folio-scoped count may be 0 for posted actions — fall back to
        # action-only count within tenant for those cases.
        if n < min_count:
            n = self._count(
                "pms_audit_trail",
                {
                    "tenant_id": self.tenant_id,
                    "action": action,
                    "metadata.folio_id": folio_id,
                },
            )
        assert n >= min_count, (
            f"expected >={min_count} audit rows action={action} for folio={folio_id}, got {n}"
        )

    def _assert_400(self, resp: requests.Response, expected_keyword: str):
        assert resp.status_code == 400, resp.text
        body = resp.json()
        detail = body.get("detail", body)
        text = (
            detail.get("error", "") if isinstance(detail, dict) else str(detail)
        ).lower()
        assert expected_keyword.lower() in text, (
            f"expected '{expected_keyword}' in error, got: {detail}"
        )

    # ── T1: charge increases balance + audit ─────────────────────────────

    def test_charge_increases_balance_with_audit(self):
        _, folio = self._create_booking_with_folio()
        folio_id = folio["id"]
        booking_id = folio["booking_id"]

        resp = self._post_charge(folio_id, booking_id, 200.0,
                                 description="Minibar", category="minibar")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("success") is True
        assert "charge" in body
        assert abs(float(body["charge"]["total"]) - 200.0) < EPS

        # Balance reflects charge
        assert abs(self._read_balance(folio_id) - 200.0) < EPS

        # Charge persisted, not voided
        charge_id = body["charge"]["id"]
        persisted = self._find_one(
            "folio_charges",
            {"id": charge_id, "tenant_id": self.tenant_id},
        )
        assert persisted is not None
        assert persisted.get("voided") is False
        assert persisted.get("folio_id") == folio_id

        # Audit
        self._assert_audit(folio_id, "charge_posted")

    # ── T2: payment decreases balance + audit ────────────────────────────

    def test_payment_decreases_balance_with_audit(self):
        _, folio = self._create_booking_with_folio()
        folio_id = folio["id"]
        booking_id = folio["booking_id"]

        c = self._post_charge(folio_id, booking_id, 200.0)
        assert c.status_code == 200, c.text
        assert abs(self._read_balance(folio_id) - 200.0) < EPS

        p = self._post_payment(folio_id, booking_id, 150.0, method="cash")
        assert p.status_code == 200, p.text
        body = p.json()
        assert body.get("success") is True
        assert body["payment"]["status"] == "paid"

        # Balance: 200 - 150 = 50
        assert abs(self._read_balance(folio_id) - 50.0) < EPS

        self._assert_audit(folio_id, "payment_posted")

    # ── T3: refund increases balance + audit ─────────────────────────────

    def test_refund_increases_balance_with_audit(self):
        _, folio = self._create_booking_with_folio()
        folio_id = folio["id"]
        booking_id = folio["booking_id"]

        assert self._post_charge(folio_id, booking_id, 200.0).status_code == 200
        assert self._post_payment(folio_id, booking_id, 150.0).status_code == 200
        assert abs(self._read_balance(folio_id) - 50.0) < EPS

        r = self._post_refund(folio_id, booking_id, 50.0, reason="guest request")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("success") is True
        refund = body["refund"]
        assert refund["payment_type"] == "refund"
        assert refund["status"] == "refunded"
        # Refund stored as negative payment
        assert abs(float(refund["amount"]) - (-50.0)) < EPS

        # Balance: 50 + 50 (refund undoes effective payment) = 100
        # Math: charges_total(200) - payments_sum(150 + (-50)) = 200 - 100 = 100
        assert abs(self._read_balance(folio_id) - 100.0) < EPS

        # Refund persisted in payments collection with payment_type="refund"
        refund_doc = self._find_one(
            "payments",
            {"id": refund["id"], "tenant_id": self.tenant_id},
        )
        assert refund_doc is not None
        assert refund_doc.get("payment_type") == "refund"
        assert abs(float(refund_doc.get("amount", 0)) - (-50.0)) < EPS

        self._assert_audit(folio_id, "refund_posted")

    # ── T4: void charge recalculates balance ─────────────────────────────

    def test_void_charge_recalculates_balance(self):
        _, folio = self._create_booking_with_folio()
        folio_id = folio["id"]
        booking_id = folio["booking_id"]

        c = self._post_charge(folio_id, booking_id, 200.0)
        assert c.status_code == 200
        charge_id = c.json()["charge"]["id"]
        assert abs(self._read_balance(folio_id) - 200.0) < EPS

        v = self._void_charge(charge_id, reason="posted in error")
        assert v.status_code == 200, v.text
        body = v.json()
        assert body.get("success") is True
        assert body.get("charge_id") == charge_id

        # Charge marked voided
        persisted = self._find_one(
            "folio_charges",
            {"id": charge_id, "tenant_id": self.tenant_id},
        )
        assert persisted is not None
        assert persisted.get("voided") is True
        assert persisted.get("void_reason") == "posted in error"

        # Balance recalc: voided charge excluded -> 0
        assert abs(self._read_balance(folio_id) - 0.0) < EPS

    # ── T5: void payment recalculates balance ────────────────────────────

    def test_void_payment_recalculates_balance(self):
        _, folio = self._create_booking_with_folio()
        folio_id = folio["id"]
        booking_id = folio["booking_id"]

        assert self._post_charge(folio_id, booking_id, 200.0).status_code == 200
        p = self._post_payment(folio_id, booking_id, 150.0)
        assert p.status_code == 200
        payment_id = p.json()["payment"]["id"]
        assert abs(self._read_balance(folio_id) - 50.0) < EPS

        v = self._void_payment(payment_id, reason="payment captured twice")
        assert v.status_code == 200, v.text
        assert v.json().get("success") is True

        persisted = self._find_one(
            "payments",
            {"id": payment_id, "tenant_id": self.tenant_id},
        )
        assert persisted is not None
        assert persisted.get("voided") is True

        # Balance recalc: voided payment excluded -> back to 200
        assert abs(self._read_balance(folio_id) - 200.0) < EPS

    # ── T6: double void charge rejected ──────────────────────────────────

    def test_double_void_charge_rejected(self):
        _, folio = self._create_booking_with_folio()
        folio_id = folio["id"]
        booking_id = folio["booking_id"]

        c = self._post_charge(folio_id, booking_id, 200.0)
        assert c.status_code == 200
        charge_id = c.json()["charge"]["id"]

        first = self._void_charge(charge_id, reason="first void")
        assert first.status_code == 200, first.text

        second = self._void_charge(charge_id, reason="second void attempt")
        # already-voided guard
        self._assert_400(second, "already voided")

    # ── T7: charge on closed folio blocked ───────────────────────────────

    def test_charge_on_closed_folio_blocked(self):
        _, folio = self._create_booking_with_folio()
        folio_id = folio["id"]
        booking_id = folio["booking_id"]

        original_status = folio.get("status", "open")
        self._set_folio_field(
            folio_id,
            {"status": "closed", "closed_at": datetime.now(UTC).isoformat()},
        )
        try:
            resp = self._post_charge(folio_id, booking_id, 100.0)
            self._assert_400(resp, "closed")
        finally:
            self._set_folio_field(folio_id, {"status": original_status})

    # ── T8: payment on closed folio blocked ──────────────────────────────

    def test_payment_on_closed_folio_blocked(self):
        _, folio = self._create_booking_with_folio()
        folio_id = folio["id"]
        booking_id = folio["booking_id"]

        original_status = folio.get("status", "open")
        self._set_folio_field(
            folio_id,
            {"status": "closed", "closed_at": datetime.now(UTC).isoformat()},
        )
        try:
            resp = self._post_payment(folio_id, booking_id, 100.0)
            self._assert_400(resp, "closed")
        finally:
            self._set_folio_field(folio_id, {"status": original_status})

    # ── T9: refund on closed folio blocked (gap closed) ──────────────────

    def test_refund_on_closed_folio_blocked(self):
        """Closed-folio refund guard (symmetric with post_charge / post_payment).

        Previously a known gap (`test_refund_on_closed_folio_succeeds_GAP`):
            post_charge   -> rejects when folio.status != "open"  (400)
            post_payment  -> rejects when folio.status != "open"  (400)
            post_refund   -> proceeded silently on closed folios

        Production hardening (May 2026) added the closed-state guard to
        `post_refund` so balance integrity on closed folios is preserved.
        This test asserts:
          - refund call returns 400 on closed folio (detail contains "closed")
          - no refund row is persisted in payments collection
          - no `refund_posted` audit row is written
        """
        _, folio = self._create_booking_with_folio()
        folio_id = folio["id"]
        booking_id = folio["booking_id"]

        original_status = folio.get("status", "open")
        self._set_folio_field(
            folio_id,
            {"status": "closed", "closed_at": datetime.now(UTC).isoformat()},
        )
        try:
            r = self._post_refund(
                folio_id, booking_id, 50.0, reason="closed-folio refund blocked"
            )
            self._assert_400(r, "closed")

            refund_doc = self._find_one(
                "payments",
                {"folio_id": folio_id, "payment_type": "refund", "tenant_id": self.tenant_id},
            )
            assert refund_doc is None, "refund must not be persisted on closed folio"

            # No refund_posted audit row should be written on a blocked refund.
            audit_count = self._count(
                "pms_audit_trail",
                {
                    "tenant_id": self.tenant_id,
                    "action": "refund_posted",
                    "metadata.folio_id": folio_id,
                },
            )
            assert audit_count == 0, (
                f"blocked refund must not write refund_posted audit row, got {audit_count}"
            )
        finally:
            self._set_folio_field(folio_id, {"status": original_status})

    # ── T10: void charge on closed folio blocked ─────────────────────────

    def test_void_charge_on_closed_folio_blocked(self):
        """Void of an existing charge must be rejected when folio is closed."""
        _, folio = self._create_booking_with_folio()
        folio_id = folio["id"]
        booking_id = folio["booking_id"]

        # Post a charge while folio is open, then close the folio.
        post = self._post_charge(folio_id, booking_id, 75.0)
        assert post.status_code == 200, post.text
        charge_id = post.json()["charge"]["id"]

        original_status = folio.get("status", "open")
        self._set_folio_field(
            folio_id,
            {"status": "closed", "closed_at": datetime.now(UTC).isoformat()},
        )
        try:
            r = self._void_charge(charge_id, reason="void on closed folio")
            self._assert_400(r, "closed")

            doc = self._find_one(
                "folio_charges", {"id": charge_id, "tenant_id": self.tenant_id}
            )
            assert doc is not None
            assert doc.get("voided") is False, "charge must not flip to voided on closed folio"
        finally:
            self._set_folio_field(folio_id, {"status": original_status})

    # ── T11: void payment on closed folio blocked ────────────────────────

    @pytest.mark.parametrize("folio_status", ["closed", "transferred", "voided"])
    def test_refund_blocked_for_all_non_open_folio_statuses(self, folio_status):
        """Guard symmetry across every non-open FolioStatus value.

        post_refund must reject refunds when folio is `closed`, `transferred`,
        or `voided` — the guard logic is `status != "open"` so all three
        terminal states should behave identically.
        """
        _, folio = self._create_booking_with_folio()
        folio_id = folio["id"]
        booking_id = folio["booking_id"]

        original_status = folio.get("status", "open")
        self._set_folio_field(folio_id, {"status": folio_status})
        try:
            r = self._post_refund(
                folio_id, booking_id, 25.0,
                reason=f"refund on {folio_status} folio must be blocked",
            )
            self._assert_400(r, folio_status)
        finally:
            self._set_folio_field(folio_id, {"status": original_status})

    def test_void_payment_on_closed_folio_blocked(self):
        """Void of an existing payment must be rejected when folio is closed."""
        _, folio = self._create_booking_with_folio()
        folio_id = folio["id"]
        booking_id = folio["booking_id"]

        # Post a payment while folio is open, then close the folio.
        pay = self._post_payment(folio_id, booking_id, 60.0)
        assert pay.status_code == 200, pay.text
        payment_id = pay.json()["payment"]["id"]

        original_status = folio.get("status", "open")
        self._set_folio_field(
            folio_id,
            {"status": "closed", "closed_at": datetime.now(UTC).isoformat()},
        )
        try:
            r = self._void_payment(payment_id, reason="void on closed folio")
            self._assert_400(r, "closed")

            doc = self._find_one(
                "payments", {"id": payment_id, "tenant_id": self.tenant_id}
            )
            assert doc is not None
            assert doc.get("voided") is False, "payment must not flip to voided on closed folio"
        finally:
            self._set_folio_field(folio_id, {"status": original_status})


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
