"""
Backend tests for the two AI sibling endpoints in autopilot_reco that had no
coverage: `/api/ai/solve-overbooking` (solve_overbooking) and
`/api/ai/recommend-room-moves` (recommend_room_moves).

These handlers carry non-trivial logic — overbooking conflict detection,
loyalty-tier priority scoring, OTA-channel penalty, in-memory availability
checks, VIP/Gold complimentary upgrades, and active room-block avoidance — that
could silently regress. The tests call each handler directly with a fake `db`
patched in, mirroring the pattern in `test_ai_recommend_rates_occupancy.py`.
"""
from types import SimpleNamespace
from unittest.mock import patch

from domains.ai.router.autopilot_reco import (
    recommend_room_moves,
    solve_overbooking,
)

TENANT = "t-ai"


def _match(doc: dict, query: dict) -> bool:
    """Minimal MongoDB query matcher mirroring the operators these handlers use.

    Honors scalar equality plus `$in`, `$lte`, `$gte`, and a top-level `$or`
    (list of sub-queries). String comparisons use Python's lexicographic
    ordering, identical to how Mongo compares the ISO timestamp strings the
    handlers store/query.
    """
    for key, cond in query.items():
        if key == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
            continue
        value = doc.get(key)
        if isinstance(cond, dict):
            if "$in" in cond and value not in cond["$in"]:
                return False
            if "$lte" in cond and not (value is not None and value <= cond["$lte"]):
                return False
            if "$gte" in cond and not (value is not None and value >= cond["$gte"]):
                return False
        else:
            if value != cond:
                return False
    return True


class _FakeCursor:
    """Supports both `await cursor.to_list(n)` and `async for row in cursor`."""

    def __init__(self, rows):
        self._rows = rows

    async def to_list(self, limit):
        if limit is None:
            return list(self._rows)
        return list(self._rows[:limit])

    def __aiter__(self):
        self._iter = iter(self._rows)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class _FakeCollection:
    def __init__(self, rows):
        self._rows = rows

    def find(self, query, projection=None):
        return _FakeCursor([r for r in self._rows if _match(r, query)])

    async def find_one(self, query, projection=None):
        for r in self._rows:
            if _match(r, query):
                return r
        return None


class _FakeDB:
    def __init__(self, rooms=None, bookings=None, guests=None, room_blocks=None):
        self.rooms = _FakeCollection(rooms or [])
        self.bookings = _FakeCollection(bookings or [])
        self.guests = _FakeCollection(guests or [])
        self.room_blocks = _FakeCollection(room_blocks or [])


def _room(room_id, room_number, room_type, base_price, floor=1):
    return {
        "id": room_id,
        "tenant_id": TENANT,
        "room_number": room_number,
        "room_type": room_type,
        "base_price": base_price,
        "floor": floor,
    }


def _booking(bk_id, room_id, guest_id, check_in, check_out, **extra):
    doc = {
        "id": bk_id,
        "tenant_id": TENANT,
        "room_id": room_id,
        "guest_id": guest_id,
        "status": "confirmed",
        "check_in": check_in,
        "check_out": check_out,
    }
    doc.update(extra)
    return doc


def _guest(guest_id, name, loyalty_tier):
    return {
        "id": guest_id,
        "tenant_id": TENANT,
        "name": name,
        "loyalty_tier": loyalty_tier,
    }


# ───────────────────────── solve_overbooking ─────────────────────────


async def test_solve_overbooking_conflict_detection_and_move():
    """Two confirmed bookings on the same room for the target day are a
    conflict; the second is moved to the only available same-type room, and
    the OTA penalty path is exercised on the moved booking's guest."""
    rooms = [
        _room("s1", "101", "Standard", 100),
        _room("s2", "102", "Standard", 100),
        _room("s3", "103", "Standard", 100),
        _room("d1", "201", "Deluxe", 200),
    ]
    # s1 is double-booked over 2026-07-01 -> overbooking conflict.
    # bkA is kept (first), bkB is the one moved.
    bookings = [
        _booking("bkA", "s1", "g_std", "2026-07-01T14:00:00", "2026-07-02T11:00:00",
                 guest_name="Alice Keep"),
        _booking("bkB", "s1", "g_vip", "2026-07-01T15:00:00", "2026-07-03T11:00:00",
                 guest_name="Bob Move", ota_channel="booking.com"),
        # s3 is occupied across bkB's window -> NOT an available alternative.
        _booking("bk_s3", "s3", "g_std", "2026-07-01T14:00:00", "2026-07-02T11:00:00"),
        # d1 single booking -> no conflict on the Deluxe room.
        _booking("bk_d1", "d1", "g_std", "2026-07-01T14:00:00", "2026-07-02T11:00:00"),
    ]
    guests = [
        _guest("g_std", "Alice Keep", "standard"),
        _guest("g_vip", "Bob Move", "vip"),
    ]
    fake_db = _FakeDB(rooms=rooms, bookings=bookings, guests=guests)
    user = SimpleNamespace(tenant_id=TENANT)

    with patch("domains.ai.router.autopilot_reco.db", fake_db):
        result = await solve_overbooking(date="2026-07-01", current_user=user, _perm=None)

    # Only s1 has >1 overlapping booking.
    assert result["conflicts_found"] == 1
    assert len(result["solutions"]) == 1

    sol = result["solutions"][0]
    assert sol["conflict_type"] == "overbooking"
    assert sol["severity"] == "high"
    assert sol["recommended_action"] == "move"
    # The kept booking is bkA; bkB is the one relocated.
    assert sol["booking_id"] == "bkB"
    assert sol["guest_name"] == "Bob Move"
    # s2 is the only available same-type room (s3 is occupied across the window).
    assert sol["recommended_room"] == "102"
    assert sol["recommended_room_id"] == "s2"
    assert sol["confidence"] == 0.85
    assert sol["impact"] == "minimal"
    assert sol["auto_apply"] is False
    assert "Standard" in sol["reason"]
    assert result["summary"] == "Found 1 overbooking conflicts with 1 AI-powered solutions"


async def test_solve_overbooking_no_conflict_no_solutions():
    """Distinct rooms each with a single booking produce no conflicts."""
    rooms = [
        _room("s1", "101", "Standard", 100),
        _room("s2", "102", "Standard", 100),
    ]
    bookings = [
        _booking("bk1", "s1", "g1", "2026-07-01T14:00:00", "2026-07-02T11:00:00"),
        _booking("bk2", "s2", "g2", "2026-07-01T14:00:00", "2026-07-02T11:00:00"),
    ]
    fake_db = _FakeDB(rooms=rooms, bookings=bookings)
    user = SimpleNamespace(tenant_id=TENANT)

    with patch("domains.ai.router.autopilot_reco.db", fake_db):
        result = await solve_overbooking(date="2026-07-01", current_user=user, _perm=None)

    assert result["conflicts_found"] == 0
    assert result["solutions"] == []


async def test_solve_overbooking_no_available_alternative():
    """A conflict with no available same-type alternative yields no solution
    even though the conflict is still counted."""
    rooms = [
        _room("s1", "101", "Standard", 100),
        _room("s2", "102", "Standard", 100),
    ]
    bookings = [
        # s1 double-booked -> conflict, bkB needs to move.
        _booking("bkA", "s1", "g1", "2026-07-01T14:00:00", "2026-07-02T11:00:00"),
        _booking("bkB", "s1", "g2", "2026-07-01T15:00:00", "2026-07-02T11:00:00"),
        # s2 (the only alternative) is occupied across the window.
        _booking("bk_s2", "s2", "g3", "2026-07-01T14:00:00", "2026-07-02T11:00:00"),
    ]
    fake_db = _FakeDB(rooms=rooms, bookings=bookings, guests=[_guest("g2", "G2", "standard")])
    user = SimpleNamespace(tenant_id=TENANT)

    with patch("domains.ai.router.autopilot_reco.db", fake_db):
        result = await solve_overbooking(date="2026-07-01", current_user=user, _perm=None)

    assert result["conflicts_found"] == 1
    assert result["solutions"] == []


# ───────────────────────── recommend_room_moves ─────────────────────────


async def test_recommend_room_moves_upgrades_and_block_avoidance():
    """VIP/Gold guests get complimentary upgrades to available better rooms,
    a blocked room triggers a same-type fallback, and recommendations are
    ordered urgent -> high -> medium."""
    rooms = [
        _room("s1", "201", "Standard", 100),
        _room("s2", "202", "Standard", 100),
        _room("s3", "203", "Standard", 100),
        _room("d1", "301", "Deluxe", 200),
        _room("d2", "302", "Deluxe", 200),
        _room("su1", "401", "Suite", 400),
    ]
    bookings = [
        # VIP in a Standard room -> eligible for upgrade (first better room: d1).
        _booking("bk_vip", "s1", "g_vip", "2026-08-01T14:00:00", "2026-08-02T11:00:00"),
        # Standard guest in s2 which is blocked -> block_avoidance fallback to s3.
        _booking("bk_std", "s2", "g_std", "2026-08-01T14:00:00", "2026-08-02T11:00:00"),
        # Gold guest in a Deluxe room -> upgrade to the Suite (su1).
        _booking("bk_gold", "d2", "g_gold", "2026-08-01T14:00:00", "2026-08-02T11:00:00"),
    ]
    guests = [
        _guest("g_vip", "Vera VIP", "vip"),
        _guest("g_std", "Sam Standard", "standard"),
        _guest("g_gold", "Gina Gold", "gold"),
    ]
    room_blocks = [
        {
            "id": "rb1",
            "tenant_id": TENANT,
            "room_id": "s2",
            "status": "active",
            "type": "maintenance",
            "start_date": "2026-07-30T00:00:00",
            "end_date": "2026-08-05T00:00:00",
        }
    ]
    fake_db = _FakeDB(rooms=rooms, bookings=bookings, guests=guests, room_blocks=room_blocks)
    user = SimpleNamespace(tenant_id=TENANT)

    with patch("domains.ai.router.autopilot_reco.db", fake_db):
        result = await recommend_room_moves(date="2026-08-01", current_user=user, _perm=None)

    assert result["count"] == 3
    recs = result["recommendations"]

    by_type = {}
    for r in recs:
        by_type.setdefault(r["type"], []).append(r)

    # VIP upgrade -> high priority, first available better room is d1.
    vip_up = next(r for r in by_type["upgrade"] if r["loyalty_tier"] == "vip")
    assert vip_up["priority"] == "high"
    assert vip_up["current_room"] == "201"
    assert vip_up["recommended_room"] == "301"
    assert vip_up["recommended_room_id"] == "d1"
    assert vip_up["confidence"] == 0.90
    assert vip_up["revenue_impact"] == 0
    assert vip_up["guest_name"] == "Vera VIP"

    # Gold upgrade -> medium priority, only better room is the Suite.
    gold_up = next(r for r in by_type["upgrade"] if r["loyalty_tier"] == "gold")
    assert gold_up["priority"] == "medium"
    assert gold_up["current_room"] == "302"
    assert gold_up["recommended_room"] == "401"
    assert gold_up["recommended_room_id"] == "su1"

    # Block avoidance -> urgent, s2 blocked so fall back to the free s3 (s1 is
    # occupied by the VIP booking and therefore not available).
    block = by_type["block_avoidance"][0]
    assert block["priority"] == "urgent"
    assert block["current_room"] == "202"
    assert block["recommended_room"] == "203"
    assert block["recommended_room_id"] == "s3"
    assert block["confidence"] == 0.95
    assert "maintenance" in block["reason"]

    # Sorted by priority: urgent first, then high, then medium.
    assert [r["priority"] for r in recs] == ["urgent", "high", "medium"]


async def test_recommend_room_moves_standard_guest_no_upgrade():
    """A standard-tier guest in an unblocked room yields no recommendation."""
    rooms = [
        _room("s1", "201", "Standard", 100),
        _room("d1", "301", "Deluxe", 200),
    ]
    bookings = [
        _booking("bk1", "s1", "g_std", "2026-08-01T14:00:00", "2026-08-02T11:00:00"),
    ]
    guests = [_guest("g_std", "Sam Standard", "standard")]
    fake_db = _FakeDB(rooms=rooms, bookings=bookings, guests=guests)
    user = SimpleNamespace(tenant_id=TENANT)

    with patch("domains.ai.router.autopilot_reco.db", fake_db):
        result = await recommend_room_moves(date="2026-08-01", current_user=user, _perm=None)

    assert result["count"] == 0
    assert result["recommendations"] == []


async def test_recommend_room_moves_vip_no_better_room_available():
    """A VIP whose only better room is occupied gets no upgrade recommendation."""
    rooms = [
        _room("s1", "201", "Standard", 100),
        _room("d1", "301", "Deluxe", 200),
    ]
    bookings = [
        _booking("bk_vip", "s1", "g_vip", "2026-08-01T14:00:00", "2026-08-02T11:00:00"),
        # The only better room (d1) is occupied across the VIP's stay.
        _booking("bk_d1", "d1", "g_other", "2026-08-01T14:00:00", "2026-08-02T11:00:00"),
    ]
    guests = [
        _guest("g_vip", "Vera VIP", "vip"),
        _guest("g_other", "Other", "standard"),
    ]
    fake_db = _FakeDB(rooms=rooms, bookings=bookings, guests=guests)
    user = SimpleNamespace(tenant_id=TENANT)

    with patch("domains.ai.router.autopilot_reco.db", fake_db):
        result = await recommend_room_moves(date="2026-08-01", current_user=user, _perm=None)

    assert result["count"] == 0
