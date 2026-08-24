"""
P2 Regression Fix — Open-folio guard ledger source
====================================================
Verifies that ``check_out_booking_atomic`` reads the folio balance from
``db.folio_ledger`` (canonical source, same as ``FolioLedgerService.compute_balance``)
and NOT from the legacy ``folio_charges`` / ``payments`` collections.

Scenarios
---------
1. force=False + positive ledger balance  → CheckOutError; booking untouched.
2. force=False + zero balance (no ledger) → checkout succeeds.
3. charge + payment = zero net balance   → checkout succeeds.
4. void/reversal cancels balance          → checkout succeeds.
5. force=True  + positive balance        → checkout succeeds (guard bypassed).
6. side-effect isolation: booking & room unchanged after CheckOutError.
"""
from __future__ import annotations

# ── Stub required env vars BEFORE any core.* import ──────────────────────────
# core/__init__.py eagerly imports core.security which raises RuntimeError if
# JWT_SECRET or MONGO_URL are missing. We inject minimal stubs here so the
# unit tests can run without a real server environment.
import os
import sys

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("TESTING", "1")

# Make sure the backend root is on the path
_backend_root = os.path.join(os.path.dirname(__file__), "..")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — build minimal in-memory document stubs
# ---------------------------------------------------------------------------

def _make_booking(
    booking_id: str,
    tenant_id: str,
    folio_id: str,
    status: str = "checked_in",
) -> dict:
    today = datetime.now(UTC).date().isoformat()
    return {
        "id": booking_id,
        "tenant_id": tenant_id,
        "status": status,
        "room_id": str(uuid.uuid4()),
        "guest_id": str(uuid.uuid4()),
        "check_in": today,
        "check_out": today,
    }


def _make_folio(folio_id: str, booking_id: str, tenant_id: str) -> dict:
    return {
        "id": folio_id,
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "status": "open",
        "folio_number": f"FOL-{folio_id[:6].upper()}",
    }


def _ledger_entry(amount: float, folio_id: str, tenant_id: str) -> dict:
    """A single folio_ledger document with the given amount."""
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "folio_id": folio_id,
        "amount": amount,
    }


# ---------------------------------------------------------------------------
# Async cursor / aggregate mock factory
# ---------------------------------------------------------------------------

def _async_cursor(docs: list) -> MagicMock:
    """Return a mock that behaves like Motor's AsyncIOMotorCursor."""
    mock = MagicMock()
    mock.to_list = AsyncMock(return_value=docs)
    return mock


class _FakeDb:
    """
    Minimal fake ``db`` object.  Each attribute is a collection mock.
    ``configure()`` lets individual tests wire up return values.
    """

    def __init__(
        self,
        booking_doc: dict,
        folio_docs: list[dict],
        ledger_docs: list[dict],
    ):
        now_iso = datetime.now(UTC).isoformat()

        # ── bookings ──────────────────────────────────────────────────
        self.bookings = MagicMock()
        self.bookings.find_one = AsyncMock(return_value=booking_doc)
        self.bookings.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        self.bookings.find = MagicMock(return_value=_async_cursor([booking_doc]))

        # ── folios ────────────────────────────────────────────────────
        self.folios = MagicMock()
        self.folios.find = MagicMock(return_value=_async_cursor(folio_docs))
        self.folios.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        self.folios.update_many = AsyncMock(return_value=MagicMock(modified_count=len(folio_docs)))

        # ── folio_ledger (canonical balance source) ───────────────────
        self.folio_ledger = MagicMock()
        agg_result = (
            [{"_id": None, "total": sum(e["amount"] for e in ledger_docs)}]
            if ledger_docs
            else []
        )
        self.folio_ledger.aggregate = MagicMock(
            return_value=_async_cursor(agg_result)
        )

        # ── rooms ─────────────────────────────────────────────────────
        self.rooms = MagicMock()
        self.rooms.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        # ── room_night_locks (released inline in txn, step 5b) ────────
        self.room_night_locks = MagicMock()
        _locks_result = MagicMock()
        _locks_result.deleted_count = 0
        self.room_night_locks.delete_many = AsyncMock(return_value=_locks_result)

        # ── housekeeping_tasks ────────────────────────────────────────
        self.housekeeping_tasks = MagicMock()
        self.housekeeping_tasks.find_one = AsyncMock(return_value=None)
        self.housekeeping_tasks.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id="hk-id")
        )

        # ── pms_audit_trail (step 7) ──────────────────────────────────
        self.pms_audit_trail = MagicMock()
        self.pms_audit_trail.insert_one = AsyncMock(return_value=MagicMock(inserted_id="at"))

        # ── outbox_events (step 8) ────────────────────────────────────
        self.outbox_events = MagicMock()
        self.outbox_events.insert_one = AsyncMock(return_value=MagicMock(inserted_id="ob"))

        # ── legacy aliases kept for attribute access checks ───────────
        self.audit_logs = MagicMock()
        self.audit_logs.insert_one = AsyncMock(return_value=MagicMock(inserted_id="al"))

        self.outbox = MagicMock()
        self.outbox.insert_one = AsyncMock(return_value=MagicMock(inserted_id="ob2"))

        # ── night_audit (lock check — not used in checkout) ───────────
        self.night_audit = MagicMock()
        self.night_audit.find_one = AsyncMock(return_value=None)

        # ── tenant_settings (business-date transition guard) ─────────
        self.tenant_settings = MagicMock()
        self.tenant_settings.find_one = AsyncMock(
            return_value={"business_date": booking_doc["check_out"]}
        )

        # ── folio_charges / payments (legacy — must NOT be queried) ───
        self.folio_charges = MagicMock()
        self.folio_charges.find = MagicMock(return_value=_async_cursor([]))
        self.payments = MagicMock()
        self.payments.find = MagicMock(return_value=_async_cursor([]))


# ---------------------------------------------------------------------------
# Session mock (MongoDB transaction session)
# ---------------------------------------------------------------------------

def _make_session() -> MagicMock:
    session = MagicMock()
    # with_transaction is used by atomic functions
    return session


# ---------------------------------------------------------------------------
# Patch helper — replaces ``db`` and transaction machinery
# ---------------------------------------------------------------------------

def _make_patches(fake_db: _FakeDb):
    """Return a list of context-manager patches to apply in each test."""
    async def _with_transaction(fn, *_, **__):
        """Execute the callback directly (no real Mongo transaction)."""
        return await fn(MagicMock())

    client_mock = MagicMock()
    client_mock.start_session = AsyncMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=MagicMock(
            with_transaction=AsyncMock(side_effect=_with_transaction)
        )),
        __aexit__=AsyncMock(return_value=False),
    ))

    # afsadakat_outbound and kbs_auto_enqueue are imported at call-time inside
    # try/except blocks, so we stub at the module level to prevent ImportError
    # in test environments that don't have all integrations installed.
    fake_afsadakat = MagicMock()
    fake_afsadakat.EV_GUEST_CHECKED_OUT = "guest.checked_out"
    fake_afsadakat.emit_event = AsyncMock()

    fake_kbs = MagicMock()
    fake_kbs.auto_enqueue_kbs = AsyncMock()

    patches = [
        patch("core.atomic_checkin_checkout.db", fake_db),
        patch("core.atomic_checkin_checkout.client", client_mock),
        # Force the function to take the MONGO_DISABLE_TRANSACTIONS=1 path
        # so the session is a plain MagicMock (simpler than mocking the full
        # async context-manager protocol of start_session).
        patch.dict("os.environ", {"MONGO_DISABLE_TRANSACTIONS": "1"}),
        patch.dict(
            "sys.modules",
            {
                "core.afsadakat_outbound": fake_afsadakat,
                "core.kbs_auto_enqueue": fake_kbs,
            },
        ),
        # tenant_context is a context-manager imported at top of the module.
        patch(
            "core.atomic_checkin_checkout.tenant_context",
            return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock(return_value=False)),
        ),
    ]
    return patches


def _apply_patches(patches):
    """Context-manager that applies a list of patches in sequence."""
    import contextlib

    @contextlib.asynccontextmanager
    async def _cm():
        with patches[0]:
            with patches[1]:
                with patches[2]:
                    with patches[3]:
                        with patches[4]:
                            yield

    return _cm()





# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.unit


@pytest.fixture()
def ids():
    return {
        "tenant_id": str(uuid.uuid4()),
        "booking_id": str(uuid.uuid4()),
        "folio_id": str(uuid.uuid4()),
        "actor_id": str(uuid.uuid4()),
    }


# ── 1. force=False + positive ledger balance → CheckOutError ─────────────

@pytest.mark.asyncio
async def test_positive_balance_blocks_checkout(ids):
    """
    SCENARIO 1 — force=False, ledger shows balance=150.00.
    Expected: CheckOutError raised; booking status NOT changed to checked_out.
    """
    booking = _make_booking(ids["booking_id"], ids["tenant_id"], ids["folio_id"])
    folio = _make_folio(ids["folio_id"], ids["booking_id"], ids["tenant_id"])
    ledger = [
        _ledger_entry(200.0, ids["folio_id"], ids["tenant_id"]),  # charge
        _ledger_entry(-50.0, ids["folio_id"], ids["tenant_id"]),  # partial payment
    ]  # net = 150.00

    fake_db = _FakeDb(booking, [folio], ledger)
    patches = _make_patches(fake_db)

    from core.atomic_checkin_checkout import CheckOutError, check_out_booking_atomic

    with patches[0], patches[1], patches[2]:
        with pytest.raises(CheckOutError, match="unpaid balance"):
            await check_out_booking_atomic(
                booking_id=ids["booking_id"],
                tenant_id=ids["tenant_id"],
                actor_id=ids["actor_id"],
                force=False,
            )

    # Booking must NOT have been updated to checked_out
    fake_db.bookings.update_one.assert_not_called()


# ── 2. force=False + no ledger entries (zero balance) → success ──────────

@pytest.mark.asyncio
async def test_zero_balance_no_ledger_allows_checkout(ids):
    """
    SCENARIO 2 — force=False, no folio_ledger entries → balance=0.00.
    Expected: checkout completes successfully.
    """
    booking = _make_booking(ids["booking_id"], ids["tenant_id"], ids["folio_id"])
    folio = _make_folio(ids["folio_id"], ids["booking_id"], ids["tenant_id"])
    ledger = []  # no entries → balance 0.0

    fake_db = _FakeDb(booking, [folio], ledger)
    patches = _make_patches(fake_db)

    from core.atomic_checkin_checkout import check_out_booking_atomic

    with patches[0], patches[1], patches[2]:
        result = await check_out_booking_atomic(
            booking_id=ids["booking_id"],
            tenant_id=ids["tenant_id"],
            actor_id=ids["actor_id"],
            force=False,
        )

    assert result.get("success") is True


# ── 3. charge + payment = zero net balance → success ─────────────────────

@pytest.mark.asyncio
async def test_charge_and_full_payment_zero_net_allows_checkout(ids):
    """
    SCENARIO 3 — charge 300, payment -300 → net=0.00.
    Expected: checkout completes successfully.
    """
    booking = _make_booking(ids["booking_id"], ids["tenant_id"], ids["folio_id"])
    folio = _make_folio(ids["folio_id"], ids["booking_id"], ids["tenant_id"])
    ledger = [
        _ledger_entry(300.0, ids["folio_id"], ids["tenant_id"]),   # charge
        _ledger_entry(-300.0, ids["folio_id"], ids["tenant_id"]),  # payment
    ]  # net = 0.0

    fake_db = _FakeDb(booking, [folio], ledger)
    patches = _make_patches(fake_db)

    from core.atomic_checkin_checkout import check_out_booking_atomic

    with patches[0], patches[1], patches[2]:
        result = await check_out_booking_atomic(
            booking_id=ids["booking_id"],
            tenant_id=ids["tenant_id"],
            actor_id=ids["actor_id"],
            force=False,
        )

    assert result.get("success") is True


# ── 4. void/reversal cancels positive charge → success ───────────────────

@pytest.mark.asyncio
async def test_void_reversal_reduces_balance_to_zero_allows_checkout(ids):
    """
    SCENARIO 4 — charge 500, then reversed via negative adjustment → net=0.00.
    Expected: checkout completes successfully.
    """
    booking = _make_booking(ids["booking_id"], ids["tenant_id"], ids["folio_id"])
    folio = _make_folio(ids["folio_id"], ids["booking_id"], ids["tenant_id"])
    ledger = [
        _ledger_entry(500.0, ids["folio_id"], ids["tenant_id"]),   # original charge
        _ledger_entry(-500.0, ids["folio_id"], ids["tenant_id"]),  # void/reversal
    ]  # net = 0.0

    fake_db = _FakeDb(booking, [folio], ledger)
    patches = _make_patches(fake_db)

    from core.atomic_checkin_checkout import check_out_booking_atomic

    with patches[0], patches[1], patches[2]:
        result = await check_out_booking_atomic(
            booking_id=ids["booking_id"],
            tenant_id=ids["tenant_id"],
            actor_id=ids["actor_id"],
            force=False,
        )

    assert result.get("success") is True


# ── 5. force=True + positive balance → guard bypassed, success ───────────

@pytest.mark.asyncio
async def test_force_true_bypasses_guard_with_positive_balance(ids):
    """
    SCENARIO 5 — force=True despite ledger balance=999.00.
    Expected: checkout completes; folio_ledger NOT queried for balance.
    """
    booking = _make_booking(ids["booking_id"], ids["tenant_id"], ids["folio_id"])
    folio = _make_folio(ids["folio_id"], ids["booking_id"], ids["tenant_id"])
    ledger = [
        _ledger_entry(999.0, ids["folio_id"], ids["tenant_id"]),
    ]  # would block if force=False

    fake_db = _FakeDb(booking, [folio], ledger)
    patches = _make_patches(fake_db)

    from core.atomic_checkin_checkout import check_out_booking_atomic

    with patches[0], patches[1], patches[2]:
        result = await check_out_booking_atomic(
            booking_id=ids["booking_id"],
            tenant_id=ids["tenant_id"],
            actor_id=ids["actor_id"],
            force=True,
        )

    assert result.get("success") is True
    # folio_ledger.aggregate must NOT have been called (guard is skipped)
    fake_db.folio_ledger.aggregate.assert_not_called()


# ── 6. side-effect isolation: booking & room unchanged after error ────────

@pytest.mark.asyncio
async def test_no_side_effects_on_checkout_error(ids):
    """
    SCENARIO 6 — CheckOutError on positive balance must not mutate booking
    or room state (atomicity guarantee).
    """
    booking = _make_booking(ids["booking_id"], ids["tenant_id"], ids["folio_id"])
    folio = _make_folio(ids["folio_id"], ids["booking_id"], ids["tenant_id"])
    ledger = [_ledger_entry(75.0, ids["folio_id"], ids["tenant_id"])]

    fake_db = _FakeDb(booking, [folio], ledger)
    patches = _make_patches(fake_db)

    from core.atomic_checkin_checkout import CheckOutError, check_out_booking_atomic

    with patches[0], patches[1], patches[2]:
        with pytest.raises(CheckOutError):
            await check_out_booking_atomic(
                booking_id=ids["booking_id"],
                tenant_id=ids["tenant_id"],
                actor_id=ids["actor_id"],
                force=False,
            )

    # Neither booking nor room should have been written
    fake_db.bookings.update_one.assert_not_called()
    fake_db.rooms.update_one.assert_not_called()
    # folio_ledger was queried (that's expected — it's the balance source)
    fake_db.folio_ledger.aggregate.assert_called_once()
    # Legacy collections must NOT have been touched
    fake_db.folio_charges.find.assert_not_called()
    fake_db.payments.find.assert_not_called()
