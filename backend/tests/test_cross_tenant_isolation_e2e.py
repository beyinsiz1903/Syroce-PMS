"""
Cross-Tenant Isolation E2E v4
==============================

SaaS tenant boundary characterization tests. Verifies that a token issued for
Tenant B cannot read or mutate Tenant A's data through the canonical PMS APIs,
and that no side effects (status changes, balance changes, ledger writes) leak
across the tenant boundary on cross-tenant write attempts.

Pattern: requests.Session over live HTTP + sync pymongo for side-channel
verification. Mirrors the v1 / v2 / v3 e2e style (lifecycle / no-show /
folio).

Tenant strategy:
    Tenant A = demo tenant (login: demo@hotel.com / demo123) — same as v1/v2/v3
    Tenant B = fabricated at class setup (Mongo seed of tenant + admin user +
               guest + room), with hybrid auth:
                 1) Try real /api/auth/login with seeded credentials
                 2) Fallback: manual JWT signed with JWT_SECRET env
                 3) Otherwise: pytest.skip

Scope (v4) — 6 tests:
    T1. booking full-detail cross-tenant denied + A can still read
    T2. cancel cross-tenant denied + A booking status unchanged
    T3. folio charge cross-tenant denied + balance/charge count unchanged
    T4. no-show cross-tenant denied + status / no_show_at unchanged
    T5. booking list no cross-tenant leak
    T6. guest read/list no cross-tenant leak

Assertion contract (per ChatGPT v4 spec):
    General: status_code in (403, 404)            # 404 preferred (silent)
    Folio charge only: status_code in (400, 403, 404)
    Every write-denied test MUST also verify zero side effect against
    the Tenant A entity using a Tenant A token re-read or Mongo side
    channel.

Out of scope (v4):
    - Audit trail leakage tests (deferred — opt T7)
    - Same-UUID cross-tenant collision (deferred — needs index audit, opt T8)
    - Feature flag / property profile isolation
    - Tenant deletion / archive flows
    - SXI bus / event router cross-tenant routing
    - Setup-endpoint based provisioning (ENABLE_SETUP_ENDPOINTS)
    - Refresh token cross-tenant tests
"""
import os
import random
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
import requests
from pymongo import MongoClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms")
DB_NAME = os.environ.get("DB_NAME", "hotel_pms")
BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")

EPS = 0.01

pytestmark = pytest.mark.skipif(not BASE_URL, reason="VITE_BACKEND_URL not set")


def _sync_db():
    client = MongoClient(MONGO_URL)
    return client, client[DB_NAME]


class TestCrossTenantIsolationE2E:
    # ── class-level Tenant B fixture ─────────────────────────────────────
    tenant_b: dict = {}
    user_b: dict = {}
    guest_b: dict = {}
    room_b: dict = {}
    token_b: str = ""
    auth_mode_b: str = ""  # "real_login" or "manual_jwt_fallback"
    _b_password = "xtenant-pw-123"

    @classmethod
    def _seed_tenant_b(cls) -> bool:
        """Insert Tenant B + admin user + minimal guest + room directly in
        Mongo. Returns True on success."""
        try:
            from core._pwd import BcryptContext
        except Exception:
            return False

        pwd = BcryptContext()
        client, db = _sync_db()
        try:
            now = datetime.now(UTC)
            tenant_id = str(uuid.uuid4())
            user_id = str(uuid.uuid4())
            guest_id = str(uuid.uuid4())
            room_id = str(uuid.uuid4())
            unique_suffix = uuid.uuid4().hex[:8]

            cls.tenant_b = {
                "id": tenant_id,
                "hotel_id": str(random.randint(800000, 899999)),
                "property_name": f"X-Tenant Test Hotel {unique_suffix}",
                "property_type": "hotel",
                "subscription_status": "active",
                "plan": "core_small_hotel",
                "modules": {
                    "pms": True, "reports": True, "invoices": True, "ai": True,
                },
                "created_at": now,
            }
            cls.user_b = {
                "id": user_id,
                "tenant_id": tenant_id,
                "email": f"xtenant-{unique_suffix}@example.com",
                "username": f"xtuser-{unique_suffix}",
                "name": "X-Tenant Admin",
                "role": "admin",
                "password": pwd.hash(cls._b_password),
                "is_active": True,
                "created_at": now,
            }
            cls.guest_b = {
                "id": guest_id,
                "tenant_id": tenant_id,
                "name": f"X-Tenant Guest {unique_suffix}",
                "email": f"xtguest-{unique_suffix}@example.com",
                "phone": "+905551112233",
                "id_number": str(random.randint(10000000000, 99999999999)),
                "vip_status": False,
                "created_at": now,
            }
            cls.room_b = {
                "id": room_id,
                "tenant_id": tenant_id,
                "room_number": f"X{random.randint(100, 999)}-{unique_suffix[:4]}",
                "room_type": "DELUXE",
                "floor": 9,
                "capacity": 2,
                "base_price": 100.0,
                "status": "available",
                "is_active": True,
                "created_at": now,
            }
            db.tenants.insert_one(cls.tenant_b)
            db.users.insert_one(cls.user_b)
            db.guests.insert_one(cls.guest_b)
            db.rooms.insert_one(cls.room_b)
            return True
        except Exception:
            return False
        finally:
            client.close()

    @classmethod
    def _login_tenant_b(cls) -> str:
        """Hybrid login: real → manual JWT fallback → empty string."""
        # 1) Real login via hotel_id + username (avoids the encrypted-email
        # lookup path which requires field-encryption pre-processing).
        try:
            r = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={
                    "hotel_id": cls.tenant_b["hotel_id"],
                    "username": cls.user_b["username"],
                    "password": cls._b_password,
                },
                timeout=10,
            )
            if r.status_code == 200:
                cls.auth_mode_b = "real_login"
                return r.json()["access_token"]
        except Exception:
            pass
        # 2) Fallback: manual JWT — only used when real login is unavailable.
        # Surfaced via cls.auth_mode_b so CI signal can distinguish a fully
        # validated end-to-end run from a token-fallback run that bypassed
        # the real /api/auth/login path.
        secret = os.environ.get("JWT_SECRET")
        if secret:
            now = datetime.now(UTC)
            payload = {
                "user_id": cls.user_b["id"],
                "tenant_id": cls.user_b["tenant_id"],
                "iat": now,
                "jti": secrets.token_urlsafe(16),
                "exp": now + timedelta(minutes=60),
                "type": "access",
            }
            cls.auth_mode_b = "manual_jwt_fallback"
            import warnings
            warnings.warn(
                "Cross-tenant E2E v4: real /api/auth/login failed; using "
                "manual JWT fallback. Auth-path realism is reduced for this "
                "run — investigate the login regression.",
                stacklevel=2,
            )
            return pyjwt.encode(payload, secret, algorithm="HS256")
        return ""

    @classmethod
    def _nuke_tenant_b(cls):
        if not cls.tenant_b:
            return
        try:
            client, db = _sync_db()
            tid = cls.tenant_b["id"]
            db.tenants.delete_many({"id": tid})
            db.users.delete_many({"tenant_id": tid})
            db.guests.delete_many({"tenant_id": tid})
            db.rooms.delete_many({"tenant_id": tid})
            # Belt-and-suspenders: any artifact accidentally written under
            # Tenant B during cross-tenant attack tests
            db.bookings.delete_many({"tenant_id": tid})
            db.folios.delete_many({"tenant_id": tid})
            db.folio_charges.delete_many({"tenant_id": tid})
            db.payments.delete_many({"tenant_id": tid})
            db.refresh_tokens.delete_many({"tenant_id": tid})
            db.pms_audit_trail.delete_many({"tenant_id": tid})
            db.idempotency_keys.delete_many({"tenant_id": tid})
            client.close()
        except Exception:
            pass

    @pytest.fixture(scope="class", autouse=True)
    def _class_setup(self, request):
        if not BASE_URL:
            pytest.skip("VITE_BACKEND_URL missing")
        cls = request.cls
        if not cls._seed_tenant_b():
            pytest.skip("Tenant B seed failed (BcryptContext or Mongo unavailable)")
        cls.token_b = cls._login_tenant_b()
        if not cls.token_b:
            cls._nuke_tenant_b()
            pytest.skip(
                "Tenant B auth fixture unavailable: real login failed and "
                "JWT_SECRET fallback unavailable"
            )
        yield
        cls._nuke_tenant_b()

    # ── per-test Tenant A session + tracking ─────────────────────────────

    @pytest.fixture(autouse=True)
    def _per_test_setup(self):
        # Tenant A session (demo)
        self.session_a = requests.Session()
        self.session_a.headers.update({"Content-Type": "application/json"})
        login = self.session_a.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
        )
        if login.status_code != 200:
            pytest.skip(f"Tenant A login failed: {login.status_code}")
        body = login.json()
        self.token_a = body["access_token"]
        self.tenant_a_id = body["user"]["tenant_id"]
        self.session_a.headers.update({"Authorization": f"Bearer {self.token_a}"})

        # Tenant B session shares the class-level token
        self.session_b = requests.Session()
        self.session_b.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token_b}",
        })

        self._a_created_bookings: list[str] = []
        self._a_created_guests: list[str] = []
        self._used_idem_keys: list[str] = []
        yield
        self._cleanup_tenant_a()

    # ── helpers ──────────────────────────────────────────────────────────

    def _cleanup_tenant_a(self):
        if not (self._a_created_bookings or self._a_created_guests
                or self._used_idem_keys):
            return
        try:
            client, db = _sync_db()
            tf = {"tenant_id": self.tenant_a_id}
            if self._a_created_bookings:
                ids = self._a_created_bookings
                folio_ids = [
                    f["id"] for f in db.folios.find(
                        {**tf, "booking_id": {"$in": ids}}, {"id": 1}
                    )
                ]
                db.bookings.delete_many({**tf, "id": {"$in": ids}})
                db.folios.delete_many({**tf, "booking_id": {"$in": ids}})
                if folio_ids:
                    db.folio_charges.delete_many({**tf, "folio_id": {"$in": folio_ids}})
                    db.payments.delete_many({**tf, "folio_id": {"$in": folio_ids}})
                    db.pms_audit_trail.delete_many(
                        {**tf, "metadata.folio_id": {"$in": folio_ids}}
                    )
                db.folio_charges.delete_many({**tf, "booking_id": {"$in": ids}})
                db.payments.delete_many({**tf, "booking_id": {"$in": ids}})
                db.room_night_locks.delete_many({**tf, "booking_id": {"$in": ids}})
                db.outbox_events.delete_many({**tf, "reservation_id": {"$in": ids}})
                db.outbox_events.delete_many({**tf, "entity_id": {"$in": ids}})
                db.pms_audit_trail.delete_many({**tf, "entity_id": {"$in": ids}})
            if self._a_created_guests:
                gids = self._a_created_guests
                db.guests.delete_many({**tf, "id": {"$in": gids}})
                db.pms_audit_trail.delete_many({**tf, "entity_id": {"$in": gids}})
            if self._used_idem_keys:
                db.idempotency_keys.delete_many(
                    {**tf, "idempotency_key": {"$in": self._used_idem_keys}}
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
            db.room_night_locks.delete_many({
                "tenant_id": self.tenant_a_id,
                "room_id": room_id,
                "night_date": {"$gte": ci_date, "$lt": co_date},
            })
            client.close()
        except Exception:
            pass

    def _seed_a_entities(self) -> tuple[str, dict]:
        guests = self.session_a.get(f"{BASE_URL}/api/pms/guests?limit=5").json()
        rooms = self.session_a.get(f"{BASE_URL}/api/pms/rooms?limit=10").json()
        if not guests or not rooms:
            pytest.skip("Tenant A demo lacks guests/rooms")
        return guests[0]["id"], rooms[0]

    def _create_a_booking(self) -> dict:
        guest_id, room = self._seed_a_entities()
        offset = 4500 + random.randint(0, 4000)
        ci = (datetime.now(UTC).date() + timedelta(days=offset)).isoformat() + "T14:00:00Z"
        co = (datetime.now(UTC).date() + timedelta(days=offset + 2)).isoformat() + "T12:00:00Z"
        payload = {
            "guest_id": guest_id,
            "room_id": room["id"],
            "check_in": ci,
            "check_out": co,
            "adults": 2,
            "children": 0,
            "children_ages": [],
            "guests_count": 2,
            "total_amount": 800.0,
            "special_requests": f"xtenant-e2e-{uuid.uuid4().hex[:8]}",
        }
        self._clean_locks(room["id"], ci, co)
        r = self.session_a.post(
            f"{BASE_URL}/api/pms/bookings",
            json=payload,
            headers={"Idempotency-Key": self._idem_key()},
        )
        assert r.status_code == 200, f"A create failed: {r.status_code} {r.text}"
        booking = r.json()
        self._a_created_bookings.append(booking["id"])
        return booking

    def _create_a_guest(self) -> dict:
        suffix = uuid.uuid4().hex[:8]
        payload = {
            "name": f"X-Test Guest {suffix}",
            "email": f"xtest-guest-{suffix}@example.com",
            "phone": "+905559998877",
            "id_number": str(random.randint(10000000000, 99999999999)),
        }
        r = self.session_a.post(f"{BASE_URL}/api/pms/guests", json=payload)
        assert r.status_code in (200, 201), f"A guest create failed: {r.status_code} {r.text}"
        guest = r.json()
        self._a_created_guests.append(guest["id"])
        return guest

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

    def _read_balance(self, folio_id: str) -> float:
        f = self._find_one("folios", {"id": folio_id, "tenant_id": self.tenant_a_id})
        assert f is not None
        return float(f.get("balance", 0) or 0)

    def _force_past_check_in(self, booking_id: str) -> None:
        """Force a booking's check_in to yesterday so the no-show eligibility
        check (in case it runs before the tenant guard) cannot succeed for
        unrelated reasons."""
        try:
            client, db = _sync_db()
            past = datetime.now(UTC) - timedelta(days=1)
            db.bookings.update_one(
                {"id": booking_id, "tenant_id": self.tenant_a_id},
                {"$set": {
                    "check_in": past.isoformat(),
                    "check_in_date": past.date().isoformat(),
                }},
            )
            client.close()
        except Exception:
            pass

    @staticmethod
    def _assert_denied(resp: requests.Response, *, allow_400: bool = False):
        """General cross-tenant deny assertion.

        Preferred: 404 (silent — does not leak whether the entity exists in
        another tenant). Accepted: 403 (explicit deny). For service-layer
        endpoints whose 'not found' shape is wrapped in a 400 response
        (e.g. /api/pms-core/folio/charge → {success: False, error:'Folio not
        found'}), pass allow_400=True.
        """
        accepted = {403, 404}
        if allow_400:
            accepted.add(400)
        assert resp.status_code in accepted, (
            f"Cross-tenant boundary leak: expected one of {sorted(accepted)}, "
            f"got {resp.status_code} body={resp.text[:200]}"
        )

    # ── T1: booking read isolation ───────────────────────────────────────

    def test_booking_read_cross_tenant_denied(self):
        booking = self._create_a_booking()

        # Tenant B attempts to read Tenant A booking
        denied = self.session_b.get(
            f"{BASE_URL}/api/pms/reservations/{booking['id']}/full-detail"
        )
        self._assert_denied(denied)

        # Tenant A can still read its own booking
        ok = self.session_a.get(
            f"{BASE_URL}/api/pms/reservations/{booking['id']}/full-detail"
        )
        assert ok.status_code == 200, f"A re-read failed: {ok.status_code} {ok.text}"
        # Booking record unchanged in Mongo
        persisted = self._find_one(
            "bookings", {"id": booking["id"], "tenant_id": self.tenant_a_id}
        )
        assert persisted is not None
        assert persisted.get("tenant_id") == self.tenant_a_id

    # ── T2: cancel denied + status unchanged ─────────────────────────────

    def test_cancel_cross_tenant_denied_no_status_change(self):
        booking = self._create_a_booking()
        original_status = booking["status"]
        assert original_status in ("confirmed", "pending"), (
            f"Unexpected initial status {original_status}"
        )
        tid_b = self.tenant_b["id"]
        # B-side baseline: bookings count under Tenant B before the attack.
        b_bookings_before = self._count("bookings", {"tenant_id": tid_b})
        b_audit_before = self._count("pms_audit_trail", {"tenant_id": tid_b})

        denied = self.session_b.post(
            f"{BASE_URL}/api/pms-core/cancel",
            json={"booking_id": booking["id"], "reason": "cross-tenant attack"},
            headers={"Idempotency-Key": self._idem_key()},
        )
        self._assert_denied(denied)

        # Side-effect guard: status unchanged
        after = self._find_one(
            "bookings", {"id": booking["id"], "tenant_id": self.tenant_a_id}
        )
        assert after is not None
        assert after.get("status") == original_status, (
            f"Status drifted: {original_status} → {after.get('status')}"
        )
        assert after.get("cancelled_at") is None
        assert after.get("cancellation_reason") is None
        # B-side leak guards: no new artifacts written under Tenant B.
        assert self._count("bookings", {"tenant_id": tid_b}) == b_bookings_before
        assert self._count("pms_audit_trail", {"tenant_id": tid_b}) == b_audit_before
        assert self._count("bookings", {"id": booking["id"], "tenant_id": tid_b}) == 0

    # ── T3: folio charge denied + balance/charges unchanged ──────────────

    def test_folio_charge_cross_tenant_denied_no_balance_change(self):
        booking = self._create_a_booking()
        folio = self._find_one(
            "folios", {"booking_id": booking["id"], "tenant_id": self.tenant_a_id}
        )
        assert folio is not None, "Auto-created folio missing on Tenant A booking"
        folio_id = folio["id"]
        original_balance = self._read_balance(folio_id)
        original_charge_count = self._count(
            "folio_charges",
            {"folio_id": folio_id, "tenant_id": self.tenant_a_id},
        )

        denied = self.session_b.post(
            f"{BASE_URL}/api/pms-core/folio/charge",
            json={
                "folio_id": folio_id,
                "booking_id": booking["id"],
                "category": "minibar",
                "description": "cross-tenant charge attempt",
                "amount": 999.0,
                "quantity": 1.0,
                "tax_rate": 0.0,
            },
        )
        # Service-layer not-found may surface as 400 — explicitly allowed.
        self._assert_denied(denied, allow_400=True)

        # Side-effect guards: balance + charge count unchanged
        assert abs(self._read_balance(folio_id) - original_balance) < EPS, (
            f"Balance drifted: {original_balance} → {self._read_balance(folio_id)}"
        )
        new_charge_count = self._count(
            "folio_charges",
            {"folio_id": folio_id, "tenant_id": self.tenant_a_id},
        )
        assert new_charge_count == original_charge_count
        # Belt-and-suspenders: no charge written under Tenant B for this folio
        leak_count = self._count(
            "folio_charges",
            {"folio_id": folio_id, "tenant_id": self.tenant_b["id"]},
        )
        assert leak_count == 0

    # ── T4: no-show denied + status unchanged ────────────────────────────

    def test_no_show_cross_tenant_denied_no_status_change(self):
        booking = self._create_a_booking()
        # Force eligibility window so we can be confident the deny is from
        # the tenant guard and not from a no-show eligibility precondition.
        self._force_past_check_in(booking["id"])
        before = self._find_one(
            "bookings", {"id": booking["id"], "tenant_id": self.tenant_a_id}
        )
        original_status = before.get("status")
        tid_b = self.tenant_b["id"]
        b_bookings_before = self._count("bookings", {"tenant_id": tid_b})
        b_audit_before = self._count("pms_audit_trail", {"tenant_id": tid_b})

        denied = self.session_b.post(
            f"{BASE_URL}/api/pms-core/no-show",
            json={"booking_id": booking["id"], "reason": "cross-tenant attack"},
            headers={"Idempotency-Key": self._idem_key()},
        )
        self._assert_denied(denied)

        after = self._find_one(
            "bookings", {"id": booking["id"], "tenant_id": self.tenant_a_id}
        )
        assert after is not None
        assert after.get("status") == original_status, (
            f"Status drifted: {original_status} → {after.get('status')}"
        )
        assert after.get("no_show_at") is None
        assert after.get("no_show_marked_at") is None
        # B-side leak guards: no new artifacts written under Tenant B.
        assert self._count("bookings", {"tenant_id": tid_b}) == b_bookings_before
        assert self._count("pms_audit_trail", {"tenant_id": tid_b}) == b_audit_before
        assert self._count("bookings", {"id": booking["id"], "tenant_id": tid_b}) == 0

    # ── T5: booking list no leak ─────────────────────────────────────────

    def test_booking_list_no_cross_tenant_leak(self):
        booking = self._create_a_booking()

        # Tenant B list MUST NOT contain Tenant A booking
        b_list = self.session_b.get(f"{BASE_URL}/api/pms/bookings?limit=100")
        assert b_list.status_code == 200, b_list.text
        b_ids = {row.get("id") for row in (b_list.json() or [])}
        assert booking["id"] not in b_ids, (
            f"Cross-tenant leak: Tenant A booking {booking['id']} visible in "
            f"Tenant B list"
        )

        # Side-channel positive control: A booking exists in Mongo for tenant A.
        # API-level positive control (a_list) is best-effort because list
        # filters may exclude far-future bookings depending on default range.
        persisted = self._find_one(
            "bookings", {"id": booking["id"], "tenant_id": self.tenant_a_id}
        )
        assert persisted is not None, "A booking missing from Mongo (sanity)"

    # ── T6: guest read + list no leak ────────────────────────────────────

    def test_guest_read_and_list_no_cross_tenant_leak(self):
        guest = self._create_a_guest()

        # T6a: read by id denied
        denied_read = self.session_b.get(f"{BASE_URL}/api/pms/guests/{guest['id']}")
        self._assert_denied(denied_read)

        # T6b: list does not contain Tenant A guest
        b_list = self.session_b.get(f"{BASE_URL}/api/pms/guests?limit=100")
        assert b_list.status_code == 200, b_list.text
        b_ids = {row.get("id") for row in (b_list.json() or [])}
        assert guest["id"] not in b_ids, (
            f"Cross-tenant leak: Tenant A guest {guest['id']} visible in "
            f"Tenant B guest list"
        )

        # Tenant A positive control
        a_read = self.session_a.get(f"{BASE_URL}/api/pms/guests/{guest['id']}")
        assert a_read.status_code == 200, a_read.text


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
