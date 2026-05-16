"""F8A tur-10 — _build_factory_docs() extra room_move_target pool tests.

These tests do NOT touch the DB. They validate the pure factory contract so
the 03-room-move setup can rely on a deterministic vacant pool.

Acceptance per `replit.md` F8A tur-10 gotcha:
  * 3 extra vacant rooms per ROOM_TYPE (=60 total for default seed)
  * extra rooms: status=available, current_booking_id=None, no booking/RNL
  * stress_seed + stress_prefix tagged → cleanup prefix-scoped removes them
  * room_move_target=True marker present
"""
from datetime import datetime, UTC

from domains.admin.router import stress as stress_mod


def _build():
    return stress_mod._build_factory_docs(
        rc=500,
        stress_tid="TID_TEST",
        prefix="E2E_TEST_",
        now=datetime.now(UTC),
    )


def test_factory_extra_vacant_pool_count_per_type():
    rooms, _g, _b, _f, _c, _rnl, _hk = _build()
    extras = [r for r in rooms if r.get("room_move_target") is True]
    assert len(extras) == 3 * len(stress_mod.ROOM_TYPES), (
        f"expected 3 extra per ROOM_TYPE; got {len(extras)}"
    )
    per_type = {}
    for r in extras:
        per_type[r["room_type"]] = per_type.get(r["room_type"], 0) + 1
    for rtype in stress_mod.ROOM_TYPES:
        assert per_type.get(rtype, 0) == 3, (
            f"room_type={rtype} extras={per_type.get(rtype, 0)} (≠3)"
        )


def test_factory_extras_are_vacant_and_tagged():
    rooms, _g, _b, _f, _c, _rnl, _hk = _build()
    extras = [r for r in rooms if r.get("room_move_target") is True]
    for r in extras:
        assert r["status"] == "available", r
        assert r["current_booking_id"] is None, r
        assert r["stress_seed"] is True, r
        assert r["stress_prefix"] == "E2E_TEST_", r
        assert r["is_active"] is True
        assert r["is_virtual"] is False


def test_factory_extras_have_no_booking_or_rnl():
    rooms, _guests, bookings, _f, _c, rnls, _hk = _build()
    extras = [r for r in rooms if r.get("room_move_target") is True]
    extra_ids = {r["id"] for r in extras}
    booking_rids = {b["room_id"] for b in bookings}
    rnl_rids = {x["room_id"] for x in rnls}
    leaked_bookings = extra_ids & booking_rids
    leaked_rnls = extra_ids & rnl_rids
    assert not leaked_bookings, f"extras have bookings: {leaked_bookings}"
    assert not leaked_rnls, f"extras have RNLs: {leaked_rnls}"


def test_factory_total_rooms_count_with_extras():
    rooms, _g, _b, _f, _c, _rnl, _hk = _build()
    extras = [r for r in rooms if r.get("room_move_target") is True]
    assert len(rooms) == 500 + len(extras), (
        f"total={len(rooms)} base=500 extras={len(extras)}"
    )
    assert len(rooms) >= 550, "must guarantee ≥550 rooms for room-move setup"


def test_factory_base_rooms_unchanged_by_extra_pool():
    """Regression: extra pool must NOT mutate base 500 (no shared refs)."""
    rooms, _g, _b, _f, _c, _rnl, _hk = _build()
    base = [r for r in rooms if not r.get("room_move_target")]
    assert len(base) == 500
    occupied_base = [r for r in base if r["status"] == "occupied"]
    available_base = [r for r in base if r["status"] == "available"]
    # i%8==0 → pre_vacant: indices 0,8,16,...,496 = 63 pre_vacant in [0..499]
    assert len(available_base) == 63
    assert len(occupied_base) == 437
