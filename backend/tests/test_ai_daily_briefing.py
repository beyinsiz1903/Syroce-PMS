"""AI daily briefing consumes the canonical PMS operational snapshot."""
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
        {"status": "paid", "total": 111, "invoice_date": (today + timedelta(days=40)).isoformat()},  # future month
    ]
    tenant = {"property_name": "Test Hotel"}

    fake_db = _FakeDB(rooms_count=42, bookings=bookings, invoices=invoices, tenant=tenant)
    monkeypatch.setattr(endpoints, "db", fake_db)

    async def _snapshot(tenant_id, **_kwargs):
        assert tenant_id == "t1"
        return {
            "snapshot_id": "snapshot-1",
            "as_of": f"{today_s}T08:00:00+00:00",
            "business_date": today_s,
            "calendar_date": today_s,
            "inventory_scope": "active_non_virtual_rooms",
            "total_rooms": 42,
            "occupied_rooms": 2,
            "available_rooms": 40,
            "occupancy_rate": 4.76,
            "today_checkins": 1,
            "today_checkouts": 1,
            "total_guests": 2,
            "in_house_stays": 1,
            "unassigned_occupied_stays": 0,
            "room_status": {"occupied": 2, "available": 40},
        }

    monkeypatch.setattr(endpoints, "build_operational_snapshot", _snapshot)
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

    m = result["metrics"]
    assert m["total_rooms"] == 42           # from the shared operational snapshot
    assert m["occupied_rooms"] == 2         # b1 + b2
    assert m["confirmed_bookings"] == 2     # b2 + b3
    assert m["today_checkins"] == 1         # b2
    assert m["today_checkouts"] == 1        # b3
    assert m["pending_invoices"] == 1       # one pending invoice
    assert m["monthly_revenue"] == 800      # 500 + 300 (this-month invoices)
    assert m["occupancy_rate"] == 4.8       # round(2/42*100, 1)
    assert m["currency"] == "TRY"
    assert m["currency_symbol"] == "\u20ba"
    assert m["snapshot_id"] == "snapshot-1"
    assert result["business_date"] == today_s
    assert result["inventory_scope"] == "active_non_virtual_rooms"

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

    async def _snapshot(_tenant_id, **_kwargs):
        return {
            "snapshot_id": "snapshot-2", "as_of": f"{today_s}T08:00:00+00:00",
            "business_date": today_s, "calendar_date": today_s,
            "inventory_scope": "active_non_virtual_rooms", "total_rooms": 10,
            "occupied_rooms": 0, "available_rooms": 10, "occupancy_rate": 0,
            "today_checkins": 1, "today_checkouts": 0, "total_guests": 0,
            "in_house_stays": 0, "unassigned_occupied_stays": 0, "room_status": {"available": 10},
        }

    monkeypatch.setattr(endpoints, "build_operational_snapshot", _snapshot)
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
