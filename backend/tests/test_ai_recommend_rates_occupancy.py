"""
Regression test for /api/ai/recommend-rates occupancy counting.

Task #143 rewrote the occupancy calculation in `recommend_rates` from a
per-(room_type x day) `count_documents` loop into a single windowed query plus
in-memory grouping. This test locks in that the in-memory overlap counting
produces the expected per-day occupancy — and therefore the same pricing
strategy / recommended rate — for representative days, including the weekend
premium and the checkout-day overlap edge case.
"""
from types import SimpleNamespace
from unittest.mock import patch

from domains.ai.router.autopilot_reco import recommend_rates


def _match(doc: dict, query: dict) -> bool:
    """Minimal MongoDB query matcher mirroring the operators the handler uses.

    Honors scalar equality plus `$in`, `$lte`, `$gte`. String comparisons use
    Python's lexicographic ordering, identical to how Mongo compares the ISO
    timestamp strings the handler stores/queries.
    """
    for key, cond in query.items():
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
    def __init__(self, rows):
        self._rows = rows

    async def to_list(self, limit):
        if limit is None:
            return list(self._rows)
        return list(self._rows[:limit])


class _FakeCollection:
    def __init__(self, rows):
        self._rows = rows

    def find(self, query, projection=None):
        return _FakeCursor([r for r in self._rows if _match(r, query)])


class _FakeDB:
    def __init__(self, rooms, bookings):
        self.rooms = _FakeCollection(rooms)
        self.bookings = _FakeCollection(bookings)


TENANT = "t-occ"


def _room(room_id, room_type, base_price):
    return {
        "id": room_id,
        "tenant_id": TENANT,
        "room_type": room_type,
        "base_price": base_price,
    }


def _booking(room_id, check_in, check_out):
    return {
        "id": f"bk-{room_id}-{check_in}",
        "tenant_id": TENANT,
        "room_id": room_id,
        "status": "confirmed",
        "check_in": check_in,
        "check_out": check_out,
    }


def _build_fake_db():
    # Standard: 4 rooms @ 100. Deluxe: 2 rooms @ 200.
    rooms = [
        _room("s1", "Standard", 100),
        _room("s2", "Standard", 100),
        _room("s3", "Standard", 100),
        _room("s4", "Standard", 100),
        _room("d1", "Deluxe", 200),
        _room("d2", "Deluxe", 200),
    ]

    # Window: 2026-06-01 (Mon) .. 2026-06-07 (Sun).
    # A booking occupies day d when check_in <= end-of-d and check_out >= start-of-d,
    # i.e. the inclusive date range [check_in_date, check_out_date] — the checkout
    # day counts as occupied.
    #
    # Target Standard occupancy:
    #   2026-06-03 (Wed): 4/4 = 100%  -> demand_surge, rate 125
    #   2026-06-04 (Thu): 1/4 =  25%  -> attract,      rate  85   (checkout-day edge)
    #   2026-06-05 (Fri): 2/4 =  50%  -> maintain,     rate 100 * weekend 1.10 = 110
    bookings = [
        # 2026-06-03 occupied by all four Standard rooms (single-day stays).
        _booking("s1", "2026-06-03T14:00:00", "2026-06-03T23:00:00"),
        _booking("s2", "2026-06-03T14:00:00", "2026-06-03T23:00:00"),
        _booking("s4", "2026-06-03T14:00:00", "2026-06-03T23:00:00"),
        # s3 checks in 06-03 and checks OUT on 06-04 -> the only room on 06-04.
        # This is the checkout-day overlap edge: without counting the checkout
        # day, 06-04 occupancy would be 0 instead of 1.
        _booking("s3", "2026-06-03T14:00:00", "2026-06-04T11:00:00"),
        # 2026-06-05 occupied by two Standard rooms (single-day stays).
        _booking("s1", "2026-06-05T14:00:00", "2026-06-05T23:00:00"),
        _booking("s2", "2026-06-05T14:00:00", "2026-06-05T23:00:00"),
        # Deluxe: one room over 06-05 .. 06-06 -> 1/2 = 50% each day.
        _booking("d1", "2026-06-05T14:00:00", "2026-06-06T11:00:00"),
    ]
    return _FakeDB(rooms, bookings)


def _index(result):
    """Index recommendations by (room_type, date) for assertions."""
    return {
        (r["room_type"], r["date"]): r
        for r in result["recommendations"]
    }


async def test_recommend_rates_occupancy_strategy_and_rate():
    fake_db = _build_fake_db()
    user = SimpleNamespace(tenant_id=TENANT)

    with patch("domains.ai.router.autopilot_reco.db", fake_db):
        result = await recommend_rates(
            start_date="2026-06-01",
            end_date="2026-06-07",
            current_user=user,
            _perm=None,
        )

    by_key = _index(result)

    # Wed 2026-06-03 — 100% Standard occupancy, no weekend premium.
    wed = by_key[("Standard", "2026-06-03")]
    assert wed["occupancy_pct"] == 100.0
    assert wed["strategy"] == "demand_surge"
    assert wed["recommended_rate"] == 125.0
    assert "Weekend premium" not in wed["reason"]

    # Thu 2026-06-04 — checkout-day overlap: s3 checks out on 06-04 and is the
    # only occupied Standard room -> 25%, attract strategy, discounted rate.
    thu = by_key[("Standard", "2026-06-04")]
    assert thu["occupancy_pct"] == 25.0
    assert thu["strategy"] == "attract"
    assert thu["recommended_rate"] == 85.0

    # Fri 2026-06-05 — 50% occupancy -> maintain base rate, plus weekend premium.
    fri = by_key[("Standard", "2026-06-05")]
    assert fri["occupancy_pct"] == 50.0
    assert fri["strategy"] == "maintain"
    assert fri["recommended_rate"] == 110.0  # 100 base * 1.10 weekend
    assert "Weekend premium" in fri["reason"]

    # Empty day -> 0% occupancy, attract, weekday (no premium).
    mon = by_key[("Standard", "2026-06-01")]
    assert mon["occupancy_pct"] == 0.0
    assert mon["strategy"] == "attract"
    assert mon["recommended_rate"] == 85.0

    # Per-room-type grouping: Deluxe occupancy is independent of Standard.
    dlx_fri = by_key[("Deluxe", "2026-06-05")]
    assert dlx_fri["occupancy_pct"] == 50.0
    assert dlx_fri["strategy"] == "maintain"
    assert dlx_fri["recommended_rate"] == 220.0  # 200 base * 1.10 weekend

    dlx_wed = by_key[("Deluxe", "2026-06-03")]
    assert dlx_wed["occupancy_pct"] == 0.0
    assert dlx_wed["strategy"] == "attract"
    assert dlx_wed["recommended_rate"] == 170.0  # 200 base * 0.85
