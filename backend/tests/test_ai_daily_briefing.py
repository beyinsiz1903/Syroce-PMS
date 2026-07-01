"""
AI daily briefing — metric correctness after the rooms count_documents change
=============================================================================

``get_daily_briefing`` powers the executive dashboard. It used to materialise
the full ``rooms`` collection just to take ``len(rooms)``; that was switched to
``db.rooms.count_documents(...)`` (same virtual-room-excluding filter) to avoid
pulling room documents into the single shared event loop on every cache miss.

This test pins the metric semantics so the refactor (and future edits) cannot
silently drift: ``total_rooms`` must come from the count query, and the
occupancy / check-in / check-out / invoice / revenue numbers must match the
hand-computed expectations for a controlled dataset.
"""
import types
from datetime import date, timedelta

import domains.ai.endpoints as endpoints


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, _n):
        return list(self._docs)


class _FakeColl:
    def __init__(self, docs=None, count=0):
        self._docs = docs or []
        self._count = count
        self.last_count_filter = None

    def find(self, *a, **k):
        return _FakeCursor(self._docs)

    async def count_documents(self, *a, **k):
        self.last_count_filter = a[0] if a else k.get("filter")
        return self._count

    async def find_one(self, *a, **k):
        return self._docs[0] if self._docs else None


class _FakeDB:
    def __init__(self, rooms_count, bookings, invoices, tenant):
        self.rooms = _FakeColl(count=rooms_count)
        self.bookings = _FakeColl(docs=bookings)
        self.accounting_invoices = _FakeColl(docs=invoices)
        self.tenants = _FakeColl(docs=[tenant])


async def test_daily_briefing_metrics_use_room_count(monkeypatch):
    today = date.today()
    today_s = today.isoformat()
    two_ago = (today - timedelta(days=2)).isoformat()
    two_fut = (today + timedelta(days=2)).isoformat()

    bookings = [
        # occupied today (checked_in, spans today)
        {"status": "checked_in", "check_in": two_ago, "check_out": two_fut, "total_amount": 100},
        # confirmed, checks in today, also occupied
        {"status": "confirmed", "check_in": today_s, "check_out": two_fut, "total_amount": 200},
        # confirmed, checks out today (not occupied — co == today)
        {"status": "confirmed", "check_in": two_ago, "check_out": today_s, "total_amount": 300},
        # cancelled/no_show must be ignored everywhere
        {"status": "cancelled", "check_in": today_s, "check_out": two_fut, "total_amount": 400},
        {"status": "no_show", "check_in": two_ago, "check_out": today_s, "total_amount": 500},
    ]
    invoices = [
        {"status": "pending", "total": 500, "invoice_date": today_s},
        {"status": "paid", "total": 300, "invoice_date": today_s},
        {"status": "paid", "total": 999, "invoice_date": "2000-01-15"},  # old, out of month
    ]
    tenant = {"property_name": "Test Hotel"}

    fake_db = _FakeDB(rooms_count=42, bookings=bookings, invoices=invoices, tenant=tenant)
    monkeypatch.setattr(endpoints, "db", fake_db)
    monkeypatch.setattr(
        endpoints, "get_ai_service", lambda: types.SimpleNamespace(llm_enabled=False)
    )

    async def _fake_currency(_tenant_id):
        return ("TRY", "\u20ba")

    monkeypatch.setattr(endpoints, "get_tenant_currency", _fake_currency)

    user = types.SimpleNamespace(tenant_id="t1")
    result = await endpoints.get_daily_briefing.__wrapped__(
        lang="en", current_user=user, _perm=None
    )

    # The room count MUST be derived from count_documents using the same
    # tenant-scoped, virtual-room-excluding filter the dashboard KPI cards use
    # — not a len() over an unfiltered/over-broad fetch.
    rooms_filter = fake_db.rooms.last_count_filter
    assert rooms_filter is not None
    assert rooms_filter["tenant_id"] == "t1"
    assert {"is_virtual": False} in rooms_filter["$or"]
    assert {"is_virtual": {"$exists": False}} in rooms_filter["$or"]

    m = result["metrics"]
    assert m["total_rooms"] == 42           # from count_documents, not len(rooms)
    assert m["occupied_rooms"] == 2         # b1 + b2
    assert m["confirmed_bookings"] == 2     # b2 + b3
    assert m["today_checkins"] == 1         # b2
    assert m["today_checkouts"] == 1        # b3
    assert m["pending_invoices"] == 1       # one pending invoice
    assert m["monthly_revenue"] == 800      # 500 + 300 (this-month invoices)
    assert m["occupancy_rate"] == 4.8       # round(2/42*100, 1)
    assert m["currency"] == "TRY"
    assert m["currency_symbol"] == "\u20ba"

    assert result["ai_powered"] is False
    for key in ("summary", "text", "briefing", "insights", "metrics"):
        assert key in result


async def test_daily_briefing_revenue_fallback_from_bookings(monkeypatch):
    """When there are no in-month invoices, monthly_revenue falls back to the
    sum of active bookings checking in this month — unchanged by the refactor."""
    today = date.today()
    today_s = today.isoformat()

    bookings = [
        {"status": "confirmed", "check_in": today_s, "check_out": today_s, "total_amount": 150.0},
        {"status": "cancelled", "check_in": today_s, "check_out": today_s, "total_amount": 999.0},
    ]
    fake_db = _FakeDB(rooms_count=10, bookings=bookings, invoices=[], tenant={"property_name": "H"})
    monkeypatch.setattr(endpoints, "db", fake_db)
    monkeypatch.setattr(
        endpoints, "get_ai_service", lambda: types.SimpleNamespace(llm_enabled=False)
    )

    async def _fake_currency(_tenant_id):
        return ("TRY", "\u20ba")

    monkeypatch.setattr(endpoints, "get_tenant_currency", _fake_currency)

    user = types.SimpleNamespace(tenant_id="t1")
    result = await endpoints.get_daily_briefing.__wrapped__(
        lang="tr", current_user=user, _perm=None
    )

    assert result["metrics"]["total_rooms"] == 10
    assert result["metrics"]["monthly_revenue"] == 150.0  # fallback, cancelled excluded
