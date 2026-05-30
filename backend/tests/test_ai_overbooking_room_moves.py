"""
Backend tests for the two AI sibling endpoints in autopilot_reco that had no
coverage: `/api/ai/solve-overbooking` (solve_overbooking) and
`/api/ai/recommend-room-moves` (recommend_room_moves).

These handlers carry non-trivial logic — overbooking conflict detection,
loyalty-tier priority scoring, OTA-channel penalty, in-memory availability
checks, VIP/Gold complimentary upgrades, and active room-block avoidance — that
could silently regress. The tests call each handler directly with a fake `db`
patched in, mirroring the pattern in `test_ai_recommend_rates_occupancy.py`.

End-to-end contract tests (bottom of file) additionally assert that the
`recommended_room_id` a `/api/ai/solve-overbooking` suggestion returns is a
valid `new_room_id` input to the `/api/frontdesk/v2/room-move` endpoint, and
that the move actually relocates the booking with tenant scoping enforced. A
drift on either side (e.g. solve-overbooking dropping `recommended_room_id`, or
room-move renaming/removing the `new_room_id` field) would silently break the
one-click apply in production, so these tie the two contracts together.
"""
from types import SimpleNamespace
from unittest.mock import patch

from common.context import OperationContext
from domains.ai.router.autopilot_reco import (
    recommend_room_moves,
    solve_overbooking,
)
from domains.pms.frontdesk_router_v2 import RoomMoveRequest, room_move
from domains.pms.frontdesk_service_v2 import FrontdeskServiceV2

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
    # The moved guest is a VIP (base 100) booked via an OTA channel (-20),
    # so the surfaced priority score and rationale must reflect both inputs.
    assert sol["loyalty_tier"] == "vip"
    assert sol["priority_score"] == 80
    assert "VIP" in sol["priority_rationale"]
    assert "OTA" in sol["priority_rationale"]
    assert result["summary"] == "Found 1 overbooking conflicts with 1 AI-powered solutions"


async def test_solve_overbooking_ota_penalty_changes_priority_score():
    """The OTA-channel penalty has an observable effect: the same guest/booking
    yields a 20-point-lower priority score (and an OTA rationale) when booked
    through an OTA channel versus a direct booking."""

    def _scenario(ota_channel):
        rooms = [
            _room("s1", "101", "Standard", 100),
            _room("s2", "102", "Standard", 100),
        ]
        extra = {"guest_name": "Bob Move"}
        if ota_channel:
            extra["ota_channel"] = ota_channel
        bookings = [
            _booking("bkA", "s1", "g_std", "2026-07-01T14:00:00", "2026-07-02T11:00:00",
                     guest_name="Alice Keep"),
            _booking("bkB", "s1", "g_vip", "2026-07-01T15:00:00", "2026-07-03T11:00:00",
                     **extra),
        ]
        guests = [
            _guest("g_std", "Alice Keep", "standard"),
            _guest("g_vip", "Bob Move", "vip"),
        ]
        return _FakeDB(rooms=rooms, bookings=bookings, guests=guests)

    user = SimpleNamespace(tenant_id=TENANT)

    with patch("domains.ai.router.autopilot_reco.db", _scenario("booking.com")):
        ota_result = await solve_overbooking(date="2026-07-01", current_user=user, _perm=None)
    with patch("domains.ai.router.autopilot_reco.db", _scenario(None)):
        direct_result = await solve_overbooking(date="2026-07-01", current_user=user, _perm=None)

    ota_sol = ota_result["solutions"][0]
    direct_sol = direct_result["solutions"][0]

    # Same VIP guest: direct booking scores 100, OTA booking scores 80.
    assert direct_sol["priority_score"] == 100
    assert ota_sol["priority_score"] == 80
    assert direct_sol["priority_score"] - ota_sol["priority_score"] == 20
    # The penalty is explained only when the booking actually came via an OTA.
    assert "OTA" not in direct_sol["priority_rationale"]
    assert "OTA channel booking.com (-20)" in ota_sol["priority_rationale"]


async def test_solve_overbooking_solutions_ordered_by_priority():
    """When multiple bookings must move, solutions are ordered highest priority
    first, and the OTA penalty changes that ordering."""
    rooms = [_room(f"s{i}", f"10{i}", "Standard", 100) for i in range(1, 7)]
    bookings = [
        # s1 double-booked: keep the standard guest, move the VIP (no OTA -> 100).
        _booking("bkA1", "s1", "g_std1", "2026-07-01T14:00:00", "2026-07-02T11:00:00"),
        _booking("bkB1", "s1", "g_vip", "2026-07-01T15:00:00", "2026-07-02T11:00:00",
                 guest_name="Vera VIP"),
        # s2 double-booked: keep the standard guest, move a silver guest booked
        # via an OTA channel (60 - 20 = 40).
        _booking("bkA2", "s2", "g_std2", "2026-07-01T14:00:00", "2026-07-02T11:00:00"),
        _booking("bkB2", "s2", "g_silver", "2026-07-01T15:00:00", "2026-07-02T11:00:00",
                 guest_name="Sid Silver", ota_channel="expedia"),
    ]
    guests = [
        _guest("g_std1", "Std One", "standard"),
        _guest("g_std2", "Std Two", "standard"),
        _guest("g_vip", "Vera VIP", "vip"),
        _guest("g_silver", "Sid Silver", "silver"),
    ]
    fake_db = _FakeDB(rooms=rooms, bookings=bookings, guests=guests)
    user = SimpleNamespace(tenant_id=TENANT)

    with patch("domains.ai.router.autopilot_reco.db", fake_db):
        result = await solve_overbooking(date="2026-07-01", current_user=user, _perm=None)

    assert result["conflicts_found"] == 2
    scores = [s["priority_score"] for s in result["solutions"]]
    # Highest priority first; non-increasing order overall.
    assert scores == sorted(scores, reverse=True)
    # The VIP direct booking (100) outranks the OTA silver booking (40).
    assert result["solutions"][0]["booking_id"] == "bkB1"
    assert result["solutions"][0]["priority_score"] == 100
    assert result["solutions"][1]["booking_id"] == "bkB2"
    assert result["solutions"][1]["priority_score"] == 40


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


# ──────────────── room-move endpoint + end-to-end contract ────────────────
#
# The fakes above are read-only (find / find_one). The room-move service path
# also mutates state (claim target room, release old room, update booking,
# create HK task, deactivate keycards, acquire/release a lock), so the tests
# below use a small write-capable fake DB that supports update_one / insert_one
# / delete_one with the `$set`, `$in`, `$or`, `$lt`, `$exists` operators those
# code paths exercise.


class _UpdateResult:
    def __init__(self, matched_count, modified_count, upserted_id=None):
        self.matched_count = matched_count
        self.modified_count = modified_count
        self.upserted_id = upserted_id


def _match_writeable(doc: dict, query: dict) -> bool:
    """Query matcher extended with the operators the room-move path relies on
    (`$exists` and `$lt`) on top of those `_match` already supports."""
    for key, cond in query.items():
        if key == "$or":
            if not any(_match_writeable(doc, sub) for sub in cond):
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
            if "$lt" in cond and not (value is not None and value < cond["$lt"]):
                return False
            if "$exists" in cond:
                present = key in doc
                if present != cond["$exists"]:
                    return False
        else:
            if value != cond:
                return False
    return True


def _apply_update(doc: dict, update: dict) -> None:
    for op, fields in update.items():
        if op == "$set":
            doc.update(fields)
        else:  # pragma: no cover - room-move only uses $set
            raise NotImplementedError(f"Unsupported update operator: {op}")


class _WriteableCollection:
    def __init__(self, rows=None):
        self._rows = list(rows or [])

    def find(self, query, projection=None):
        return _FakeCursor([r for r in self._rows if _match_writeable(r, query)])

    async def find_one(self, query, projection=None):
        for r in self._rows:
            if _match_writeable(r, query):
                return r
        return None

    async def update_one(self, query, update, upsert=False):
        for r in self._rows:
            if _match_writeable(r, query):
                _apply_update(r, update)
                return _UpdateResult(1, 1)
        if upsert:
            new_doc: dict = {
                k: v for k, v in query.items() if not isinstance(v, dict) and not k.startswith("$")
            }
            _apply_update(new_doc, update)
            self._rows.append(new_doc)
            return _UpdateResult(0, 0, upserted_id="upserted")
        return _UpdateResult(0, 0)

    async def insert_one(self, doc):
        self._rows.append(doc)
        return SimpleNamespace(inserted_id=doc.get("id"))

    async def delete_one(self, query):
        for i, r in enumerate(self._rows):
            if _match_writeable(r, query):
                del self._rows[i]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class _WriteableDB:
    def __init__(self, rooms=None, bookings=None, keycards=None):
        self.rooms = _WriteableCollection(rooms)
        self.bookings = _WriteableCollection(bookings)
        self.keycards = _WriteableCollection(keycards)
        self.housekeeping_tasks = _WriteableCollection()
        self.operation_locks = _WriteableCollection()
        # The @audited wrapper on room_move snapshots the booking via
        # `self._db["bookings"]` and writes to `self._db.audit_logs`.
        self.audit_logs = _WriteableCollection()

    def __getitem__(self, name):
        return getattr(self, name)


def _service_with_db(fake_db) -> FrontdeskServiceV2:
    svc = FrontdeskServiceV2()
    svc._db = fake_db
    return svc


def _ctx(tenant_id=TENANT) -> OperationContext:
    user = SimpleNamespace(
        tenant_id=tenant_id, id="u-1", email="staff@hotel.com", role="front_desk"
    )
    return OperationContext.from_user(user)


async def test_room_move_endpoint_accepts_contract_fields_and_moves():
    """`/api/frontdesk/v2/room-move` accepts {booking_id, new_room_id, reason}
    and performs the move: the booking's room_id is rewritten, the target room
    is claimed (occupied), and the old room is released (dirty)."""
    rooms = [
        _room("s1", "101", "Standard", 100) | {"status": "occupied", "current_booking_id": "bk1"},
        _room("s2", "102", "Standard", 100) | {"status": "available"},
    ]
    bookings = [
        _booking("bk1", "s1", "g1", "2026-07-01T14:00:00", "2026-07-02T11:00:00")
        | {"status": "checked_in"},
    ]
    fake_db = _WriteableDB(rooms=rooms, bookings=bookings)
    svc = _service_with_db(fake_db)

    req = RoomMoveRequest(booking_id="bk1", new_room_id="s2", reason="overbooking fix")

    with patch("domains.pms.frontdesk_router_v2.frontdesk_service_v2", svc):
        resp = await room_move(req, user=SimpleNamespace(
            tenant_id=TENANT, id="u-1", email="staff@hotel.com", role="front_desk"
        ), _perm=None)

    assert resp["status"] == "ok"
    assert resp["data"]["booking_id"] == "bk1"
    assert resp["data"]["from_room"] == "101"
    assert resp["data"]["to_room"] == "102"

    moved = await fake_db.bookings.find_one({"id": "bk1"})
    assert moved["room_id"] == "s2"
    assert moved["room_move_reason"] == "overbooking fix"

    new_room = await fake_db.rooms.find_one({"id": "s2"})
    assert new_room["status"] == "occupied"
    assert new_room["current_booking_id"] == "bk1"

    old_room = await fake_db.rooms.find_one({"id": "s1"})
    assert old_room["status"] == "dirty"
    assert old_room["current_booking_id"] is None


async def test_room_move_is_tenant_scoped():
    """A booking belonging to another tenant is invisible to the move: the
    server derives tenant scope from the authenticated context, not the
    client-supplied booking_id, so the move fails NOT_FOUND and nothing is
    mutated."""
    rooms = [
        _room("s1", "101", "Standard", 100) | {"status": "occupied", "current_booking_id": "bk1"},
        _room("s2", "102", "Standard", 100) | {"status": "available"},
    ]
    bookings = [
        _booking("bk1", "s1", "g1", "2026-07-01T14:00:00", "2026-07-02T11:00:00")
        | {"status": "checked_in"},
    ]
    fake_db = _WriteableDB(rooms=rooms, bookings=bookings)
    svc = _service_with_db(fake_db)

    # Context for a *different* tenant than the booking's TENANT.
    other_ctx = _ctx(tenant_id="t-other")
    result = await svc.room_move(other_ctx, "bk1", "s2", reason="cross-tenant attempt")

    assert result.ok is False
    assert result.code == "NOT_FOUND"

    # Nothing was mutated by the rejected cross-tenant move.
    booking = await fake_db.bookings.find_one({"id": "bk1"})
    assert booking["room_id"] == "s1"
    new_room = await fake_db.rooms.find_one({"id": "s2"})
    assert new_room["status"] == "available"


async def test_solve_overbooking_suggestion_id_is_valid_room_move_input():
    """End-to-end contract: the `recommended_room_id` returned by
    `/api/ai/solve-overbooking` is accepted verbatim as the `new_room_id` of a
    `/api/frontdesk/v2/room-move` request and successfully relocates the
    suggested booking. This catches drift on either side of the apply flow."""
    # ── Step 1: get a suggestion from solve-overbooking. ──
    reco_rooms = [
        _room("s1", "101", "Standard", 100),
        _room("s2", "102", "Standard", 100),
    ]
    reco_bookings = [
        _booking("bkA", "s1", "g_std", "2026-07-01T14:00:00", "2026-07-02T11:00:00",
                 guest_name="Alice Keep"),
        _booking("bkB", "s1", "g_vip", "2026-07-01T15:00:00", "2026-07-02T11:00:00",
                 guest_name="Bob Move"),
    ]
    reco_guests = [
        _guest("g_std", "Alice Keep", "standard"),
        _guest("g_vip", "Bob Move", "vip"),
    ]
    user = SimpleNamespace(tenant_id=TENANT)
    with patch("domains.ai.router.autopilot_reco.db",
               _FakeDB(rooms=reco_rooms, bookings=reco_bookings, guests=reco_guests)):
        reco = await solve_overbooking(date="2026-07-01", current_user=user, _perm=None)

    assert len(reco["solutions"]) == 1
    suggestion = reco["solutions"][0]
    # The suggestion contract the frontend apply action relies on.
    assert "recommended_room_id" in suggestion
    assert "recommended_room" in suggestion
    suggested_booking_id = suggestion["booking_id"]
    suggested_room_id = suggestion["recommended_room_id"]
    assert suggested_booking_id == "bkB"
    assert suggested_room_id == "s2"

    # ── Step 2: feed the suggestion straight into the room-move endpoint. ──
    move_rooms = [
        _room("s1", "101", "Standard", 100) | {"status": "occupied", "current_booking_id": "bkB"},
        _room("s2", "102", "Standard", 100) | {"status": "available"},
    ]
    move_bookings = [
        _booking("bkB", "s1", "g_vip", "2026-07-01T15:00:00", "2026-07-02T11:00:00")
        | {"status": "checked_in", "guest_name": "Bob Move"},
    ]
    fake_db = _WriteableDB(rooms=move_rooms, bookings=move_bookings)
    svc = _service_with_db(fake_db)

    # Field names from the suggestion line up with RoomMoveRequest's fields —
    # if either contract drifts, this construction or the move below breaks.
    req = RoomMoveRequest(
        booking_id=suggested_booking_id,
        new_room_id=suggested_room_id,
        reason="apply AI overbooking suggestion",
    )

    with patch("domains.pms.frontdesk_router_v2.frontdesk_service_v2", svc):
        resp = await room_move(req, user=SimpleNamespace(
            tenant_id=TENANT, id="u-1", email="staff@hotel.com", role="front_desk"
        ), _perm=None)

    assert resp["status"] == "ok"
    assert resp["data"]["to_room"] == "102"

    moved = await fake_db.bookings.find_one({"id": "bkB"})
    assert moved["room_id"] == suggested_room_id
