"""Task #279 — GM snapshot-enhanced uses REAL per-date data (regression guard).

`/api/gm/snapshot-enhanced` previously SIMULATED the yesterday/last-week
columns as fixed arithmetic offsets of today's live numbers. It was changed
to compute each period from real per-date queries against
bookings/payments/feedback (`_compute_period_metrics`). Nothing guarded that
behaviour, so a future change could silently reintroduce simulated numbers.

These tests pin the real behaviour without requiring a live MongoDB:

  * A small, faithful in-memory fake DB implements exactly the Mongo query
    operators `_compute_period_metrics` relies on (`$lte/$lt/$gte/$gt/$nin/
    $in/$ne/$exists`, exact match, and the `$match`+`$group $sum` aggregate).
  * Bookings/payments/feedback are seeded across today, yesterday and
    7-days-ago for one tenant so every metric (occupancy / revenue /
    check_ins / check_outs / complaints) is DISTINCT per period and equals a
    hand-computed, data-derived value — which no single fixed offset of
    "today" could reproduce across all five metrics simultaneously.
  * A second tenant is seeded on the same dates with large values to prove
    tenant isolation (the other tenant's data is excluded).

The monkeypatch-the-module-level-`db` approach mirrors
`test_ai_noshow_tenant_isolation.py`.
"""
from datetime import UTC, datetime, timedelta

import pytest

from domains.pms.dashboard_router import gm


# ── in-memory fake DB implementing the operators gm.py uses ─────────────────

def _match(doc: dict, query: dict) -> bool:
    for field, cond in query.items():
        val = doc.get(field)
        if isinstance(cond, dict):
            for op, opv in cond.items():
                if op == "$lte":
                    if not (val is not None and val <= opv):
                        return False
                elif op == "$lt":
                    if not (val is not None and val < opv):
                        return False
                elif op == "$gte":
                    if not (val is not None and val >= opv):
                        return False
                elif op == "$gt":
                    if not (val is not None and val > opv):
                        return False
                elif op == "$nin":
                    if val in opv:
                        return False
                elif op == "$in":
                    if val not in opv:
                        return False
                elif op == "$ne":
                    if val == opv:
                        return False
                elif op == "$exists":
                    if (field in doc) != opv:
                        return False
                else:  # pragma: no cover - guards against silent test rot
                    raise AssertionError(f"unsupported operator in test fake DB: {op}")
        else:
            if val != cond:
                return False
    return True


class _FakeAggCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n):
        return list(self._docs[:n]) if n else list(self._docs)


class _FakeCollection:
    def __init__(self, docs):
        self.docs = list(docs)
        self.queries = []  # captured for filter-presence assertions

    async def count_documents(self, query):
        self.queries.append(query)
        return sum(1 for d in self.docs if _match(d, query))

    def aggregate(self, pipeline):
        match = {}
        group = None
        for stage in pipeline:
            if "$match" in stage:
                match = stage["$match"]
            if "$group" in stage:
                group = stage["$group"]
        self.queries.append(match)
        selected = [d for d in self.docs if _match(d, match)]
        if not selected:
            # Real Mongo $group with _id:None over empty input yields no docs.
            return _FakeAggCursor([])
        out = {"_id": None}
        for key, spec in (group or {}).items():
            if key == "_id":
                continue
            if isinstance(spec, dict) and "$sum" in spec:
                fld = str(spec["$sum"]).lstrip("$")
                out[key] = sum((d.get(fld) or 0) for d in selected)
        return _FakeAggCursor([out])


class _FakeDB:
    def __init__(self, *, bookings, payments, feedback, rooms, maintenance_tasks):
        self.bookings = _FakeCollection(bookings)
        self.payments = _FakeCollection(payments)
        self.feedback = _FakeCollection(feedback)
        self.rooms = _FakeCollection(rooms)
        self.maintenance_tasks = _FakeCollection(maintenance_tasks)
        self.tasks = _FakeCollection([])


class _FakeUser:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


# ── seed: distinct, data-derived metrics per period for tenant A ────────────

TENANT_A = "tenant_gm_a"
TENANT_B = "tenant_gm_b"
TENANT_EMPTY = "tenant_gm_empty"
TOTAL_ROOMS_A = 10


def _d(base, offset: int) -> str:
    """ISO date string `offset` days from `base` (matches gm's date.isoformat())."""
    return (base + timedelta(days=offset)).isoformat()


def _build_fake_db():
    today = datetime.now(UTC).date()
    T, Y, W = _d(today, 0), _d(today, -1), _d(today, -7)

    # Bookings hand-designed so each derived metric is distinct per period.
    # (See module docstring; offsets avoid coinciding with T/Y/W except where a
    #  check-in/check-out is intentionally counted.)
    bookings = [
        # occupancy + arrivals/departures
        {"tenant_id": TENANT_A, "check_in": _d(today, -7), "check_out": _d(today, -6), "status": "confirmed"},   # A1: occ W, ci W
        {"tenant_id": TENANT_A, "check_in": _d(today, -1), "check_out": _d(today, 0),  "status": "confirmed"},   # A2: occ Y, ci Y, co T
        {"tenant_id": TENANT_A, "check_in": _d(today, -1), "check_out": _d(today, 1),  "status": "confirmed"},   # A3: occ Y+T, ci Y
        {"tenant_id": TENANT_A, "check_in": _d(today, 0),  "check_out": _d(today, 2),  "status": "confirmed"},   # A4: occ T, ci T
        {"tenant_id": TENANT_A, "check_in": _d(today, -2), "check_out": _d(today, 3),  "status": "confirmed"},   # A5: occ Y+T
        {"tenant_id": TENANT_A, "check_in": _d(today, 0),  "check_out": _d(today, 1),  "status": "confirmed"},   # A6: occ T, ci T
        {"tenant_id": TENANT_A, "check_in": _d(today, -3), "check_out": _d(today, 0),  "status": "confirmed"},   # A7: occ Y, co T
        {"tenant_id": TENANT_A, "check_in": _d(today, -8), "check_out": _d(today, -7), "status": "confirmed"},   # A8: co W
        {"tenant_id": TENANT_A, "check_in": _d(today, -10),"check_out": _d(today, -7), "status": "confirmed"},   # A9: co W
        {"tenant_id": TENANT_A, "check_in": _d(today, 0),  "check_out": _d(today, 4),  "status": "confirmed"},   # A12: occ T, ci T
        {"tenant_id": TENANT_A, "check_in": _d(today, -4), "check_out": _d(today, -1), "status": "confirmed"},   # A13: co Y
        {"tenant_id": TENANT_A, "check_in": _d(today, -9), "check_out": _d(today, -7), "status": "confirmed"},   # A14: co W
        # terminal-state bookings that MUST be excluded everywhere
        {"tenant_id": TENANT_A, "check_in": _d(today, 0),  "check_out": _d(today, 1),  "status": "cancelled"},   # A10
        {"tenant_id": TENANT_A, "check_in": _d(today, -1), "check_out": _d(today, 0),  "status": "no_show"},     # A11
    ]
    # Tenant B — same dates, must never leak into tenant A's numbers.
    bookings += [
        {"tenant_id": TENANT_B, "check_in": _d(today, -1), "check_out": _d(today, 5), "status": "confirmed"},
        {"tenant_id": TENANT_B, "check_in": _d(today, 0),  "check_out": _d(today, 5), "status": "confirmed"},
        {"tenant_id": TENANT_B, "check_in": _d(today, 0),  "check_out": _d(today, 1), "status": "confirmed"},
    ]

    payments = [
        {"tenant_id": TENANT_A, "payment_date": T, "amount": 1000},
        {"tenant_id": TENANT_A, "payment_date": T, "amount": 500},
        {"tenant_id": TENANT_A, "payment_date": Y, "amount": 750},
        {"tenant_id": TENANT_A, "payment_date": W, "amount": 250},
        # Tenant B big payments on the same dates — must be excluded.
        {"tenant_id": TENANT_B, "payment_date": T, "amount": 99999},
        {"tenant_id": TENANT_B, "payment_date": Y, "amount": 88888},
        {"tenant_id": TENANT_B, "payment_date": W, "amount": 77777},
    ]

    feedback = [
        {"tenant_id": TENANT_A, "created_at": f"{T}T10:00:00+00:00", "rating": 1},
        {"tenant_id": TENANT_A, "created_at": f"{T}T11:00:00+00:00", "rating": 2},
        {"tenant_id": TENANT_A, "created_at": f"{Y}T10:00:00+00:00", "rating": 2},
        {"tenant_id": TENANT_A, "created_at": f"{W}T10:00:00+00:00", "rating": 1},
        {"tenant_id": TENANT_A, "created_at": f"{W}T11:00:00+00:00", "rating": 2},
        {"tenant_id": TENANT_A, "created_at": f"{W}T12:00:00+00:00", "rating": 1},
        # rating > 2 is NOT a complaint — must be excluded.
        {"tenant_id": TENANT_A, "created_at": f"{T}T13:00:00+00:00", "rating": 4},
        # Tenant B complaints on the same dates — must be excluded.
        {"tenant_id": TENANT_B, "created_at": f"{T}T10:00:00+00:00", "rating": 1},
        {"tenant_id": TENANT_B, "created_at": f"{Y}T10:00:00+00:00", "rating": 1},
        {"tenant_id": TENANT_B, "created_at": f"{W}T10:00:00+00:00", "rating": 1},
    ]

    rooms = (
        [{"tenant_id": TENANT_A} for _ in range(TOTAL_ROOMS_A)]
        + [{"tenant_id": TENANT_B} for _ in range(20)]
    )
    maintenance_tasks = [
        {"tenant_id": TENANT_A, "status": "pending", "priority": "high"},
        {"tenant_id": TENANT_A, "status": "pending", "priority": "urgent"},
        # excluded: wrong status / wrong priority / other tenant
        {"tenant_id": TENANT_A, "status": "done", "priority": "high"},
        {"tenant_id": TENANT_A, "status": "pending", "priority": "low"},
        {"tenant_id": TENANT_B, "status": "pending", "priority": "high"},
    ]
    return _FakeDB(
        bookings=bookings, payments=payments, feedback=feedback,
        rooms=rooms, maintenance_tasks=maintenance_tasks,
    )


# Hand-computed, data-derived expectations for tenant A.
EXPECTED_A = {
    "today":     {"occupancy": 50.0, "revenue": 1500, "check_ins": 3, "check_outs": 2, "complaints": 2},
    "yesterday": {"occupancy": 40.0, "revenue": 750,  "check_ins": 2, "check_outs": 1, "complaints": 1},
    "last_week": {"occupancy": 10.0, "revenue": 250,  "check_ins": 1, "check_outs": 3, "complaints": 3},
}
EXPECTED_PENDING_TASKS = 2


@pytest.fixture
def patched(monkeypatch):
    fake = _build_fake_db()
    monkeypatch.setattr(gm, "db", fake)

    def _use_tenant(tenant_id: str = TENANT_A):
        async def _fake_get_current_user(_credentials):
            return _FakeUser(tenant_id)
        monkeypatch.setattr(gm, "get_current_user", _fake_get_current_user)

    fake.use_tenant = _use_tenant
    return fake


# ── tests ───────────────────────────────────────────────────────────────────

async def test_compute_period_metrics_per_date_is_data_derived(patched):
    """`_compute_period_metrics` returns the seeded, per-date numbers — proving
    each period is queried independently rather than offset from today."""
    today = datetime.now(UTC).date()
    for label, day in (("today", today), ("yesterday", today - timedelta(days=1)),
                       ("last_week", today - timedelta(days=7))):
        metrics = await gm._compute_period_metrics(TENANT_A, day, TOTAL_ROOMS_A)
        exp = EXPECTED_A[label]
        assert metrics["date"] == day.isoformat()
        assert metrics["occupancy"] == exp["occupancy"], label
        assert metrics["revenue"] == exp["revenue"], label
        assert metrics["check_ins"] == exp["check_ins"], label
        assert metrics["check_outs"] == exp["check_outs"], label
        assert metrics["complaints"] == exp["complaints"], label


async def test_snapshot_periods_are_distinct_not_fixed_offsets(patched):
    """The whole endpoint returns distinct per-period data for every metric.

    If a future change reverts to simulated offsets of "today", at least one
    metric's three periods would become a deterministic function of today; the
    seeded numbers below are not reproducible by any single offset/ratio that
    simultaneously maps today->yesterday->last_week for all five metrics.
    """
    patched.use_tenant(TENANT_A)
    snap = await gm.get_enhanced_snapshot(credentials=None)

    for label in ("today", "yesterday", "last_week"):
        exp = EXPECTED_A[label]
        period = snap[label]
        assert period["occupancy"] == exp["occupancy"], label
        assert period["revenue"] == exp["revenue"], label
        assert period["check_ins"] == exp["check_ins"], label
        assert period["check_outs"] == exp["check_outs"], label
        assert period["complaints"] == exp["complaints"], label
        # pending backlog is a point-in-time read repeated across periods (honest 0 delta)
        assert period["pending_tasks"] == EXPECTED_PENDING_TASKS, label

    # Every metric must differ across the three periods (no flat/offset columns).
    for metric in ("occupancy", "revenue", "check_ins", "check_outs", "complaints"):
        vals = {snap["today"][metric], snap["yesterday"][metric], snap["last_week"][metric]}
        assert len(vals) == 3, f"{metric} not distinct across periods: {vals}"

    # Trends are derived from the real today-vs-yesterday comparison.
    assert snap["trends"]["occupancy_trend"] == "up"      # 50 > 40
    assert snap["trends"]["revenue_trend"] == "up"        # 1500 > 750
    assert snap["trends"]["complaints_trend"] == "up"     # 2 > 1


async def test_tenant_isolation_excludes_other_tenant(patched):
    """Tenant B's (larger) same-date data must never bleed into tenant A's
    snapshot, and a tenant with no data gets honest zeros."""
    patched.use_tenant(TENANT_A)
    snap_a = await gm.get_enhanced_snapshot(credentials=None)
    # Tenant B seeded revenue is far larger; A must stay on its own numbers.
    assert snap_a["today"]["revenue"] == EXPECTED_A["today"]["revenue"]
    assert snap_a["today"]["revenue"] != 99999

    # Every captured Mongo query was tenant-scoped to A (catches a dropped filter).
    fake = patched
    for coll in (fake.bookings, fake.payments, fake.feedback, fake.rooms, fake.maintenance_tasks):
        assert coll.queries, "collection was never queried"
        for q in coll.queries:
            assert q.get("tenant_id") == TENANT_A, q

    # Empty tenant -> zeros everywhere (no fabricated fallback).
    patched.use_tenant(TENANT_EMPTY)
    snap_empty = await gm.get_enhanced_snapshot(credentials=None)
    for label in ("today", "yesterday", "last_week"):
        p = snap_empty[label]
        assert p["occupancy"] == 0
        assert p["revenue"] == 0
        assert p["check_ins"] == 0
        assert p["check_outs"] == 0
        assert p["complaints"] == 0
