"""
Perf refactor semantics — CRM customers ($facet) + GM mobile critical-issues
============================================================================

Two slow-page perf changes are pinned here so the optimisation cannot silently
drift behaviour:

* ``sales/crm_router.get_sales_customers`` used to materialise EVERY distinct
  guest row into Python, classify + filter + sort + count there. It now does
  classification ($addFields), type-filtering, sort, paging and the three
  aggregate counts inside a single ``$facet`` so only ``limit`` rows + one stats
  doc come back. The response contract (customers / count / vip_count /
  corporate_count + sample fallback when empty) MUST stay byte-identical and
  the tenant scope + computed-filter semantics MUST be preserved.

* ``pms/mobile_router/dashboard.get_critical_issues_mobile`` used to fetch ALL
  confirmed bookings with ``check_in <= tomorrow`` (incl. all history) via
  ``to_list(length=None)``. It now bounds that to the most-recent
  ``_CRITICAL_CANDIDATE_CAP`` via ``sort('created_at', -1).limit(cap)`` (server
  top-k, memory-safe) while keeping the overbooking detection + response shape.

These are fake-DB unit tests (project convention — no live Mongo); they assert
the pipeline STRUCTURE the handler builds and the response it assembles from a
controlled aggregate result.
"""
import types

import domains.pms.mobile_router.dashboard as mdash
import domains.sales.crm_router as crm


# --------------------------------------------------------------------------- #
# CRM /sales/customers — $facet                                               #
# --------------------------------------------------------------------------- #
class _FacetCursor:
    def __init__(self, result):
        self._result = result

    async def to_list(self, _n):
        return list(self._result)


class _AggColl:
    def __init__(self, facet_result):
        self._facet_result = facet_result
        self.last_pipeline = None
        self.last_kwargs = None

    def aggregate(self, pipeline, **kwargs):
        self.last_pipeline = pipeline
        self.last_kwargs = kwargs
        return _FacetCursor(self._facet_result)


class _AggDB:
    def __init__(self, facet_result):
        self.bookings = _AggColl(facet_result)


def _patch_crm(monkeypatch, facet_result, tenant="t1"):
    fake_db = _AggDB(facet_result)
    monkeypatch.setattr(crm, "db", fake_db)

    async def _user(_creds):
        return types.SimpleNamespace(tenant_id=tenant)

    monkeypatch.setattr(crm, "get_current_user", _user)
    return fake_db


def _facet_stage(fake_db):
    return fake_db.bookings.last_pipeline[0]["$facet"]


async def test_crm_customers_shape_and_tenant_scope(monkeypatch):
    facet = [{
        "page": [
            {"guest_id": "g1", "guest_name": "A", "email": "a@x", "phone": "1",
             "total_bookings": 3, "total_revenue": 60000,
             "last_stay": "2026-01-01", "is_vip": True, "is_corporate": False},
            {"guest_id": "g2", "guest_name": None, "email": None, "phone": None,
             "total_bookings": 1, "total_revenue": 100,
             "last_stay": None, "is_vip": False, "is_corporate": True},
        ],
        "stats": [{"count": 5, "vip_count": 2, "corporate_count": 1}],
    }]
    fake_db = _patch_crm(monkeypatch, facet)

    res = await crm.get_sales_customers(customer_type=None, limit=50,
                                        credentials=None)

    fstage = _facet_stage(fake_db)
    match = fstage["page"][0]["$match"]
    assert match["tenant_id"] == "t1"                       # tenant scope intact
    assert match["guest_id"] == {"$nin": [None, ""]}
    assert {"$sort": {"total_revenue": -1}} in fstage["page"]
    assert {"$limit": 50} in fstage["page"]
    assert fake_db.bookings.last_kwargs.get("allowDiskUse") is True

    # counts come from the stats facet over the FULL filtered set
    assert res["count"] == 5
    assert res["vip_count"] == 2
    assert res["corporate_count"] == 1

    c1, c2 = res["customers"]
    assert c1["guest_id"] == "g1"
    assert c1["is_vip"] is True
    assert c1["customer_type"] == ["vip", "returning"]      # vip + bookings>1
    # None fallbacks preserved exactly as the legacy Python path
    assert c2["guest_name"] == "Unknown"
    assert c2["email"] == "" and c2["phone"] == ""
    assert c2["is_corporate"] is True
    assert c2["customer_type"] == ["corporate", "new"]      # corp + bookings<=1


async def test_crm_customers_vip_filter_pushed_to_pipeline(monkeypatch):
    facet = [{
        "page": [
            {"guest_id": "g1", "guest_name": "A", "email": "", "phone": "",
             "total_bookings": 2, "total_revenue": 90000,
             "last_stay": None, "is_vip": True, "is_corporate": False},
        ],
        "stats": [{"count": 3, "vip_count": 3, "corporate_count": 0}],
    }]
    fake_db = _patch_crm(monkeypatch, facet)

    res = await crm.get_sales_customers(customer_type="vip", limit=50,
                                        credentials=None)

    fstage = _facet_stage(fake_db)
    # the computed-type filter must be applied to BOTH branches so the page and
    # the counts agree (filter-before-limit, never limit-before-filter)
    assert {"$match": {"is_vip": True}} in fstage["page"]
    assert {"$match": {"is_vip": True}} in fstage["stats"]
    assert res["count"] == 3 and res["vip_count"] == 3


async def test_crm_customers_returning_and_new_filters(monkeypatch):
    facet = [{"page": [], "stats": [{"count": 1, "vip_count": 0,
                                     "corporate_count": 0}]}]
    fake_db = _patch_crm(monkeypatch, facet)
    await crm.get_sales_customers(customer_type="returning", limit=10,
                                  credentials=None)
    assert {"$match": {"total_bookings": {"$gt": 1}}} in _facet_stage(fake_db)["page"]

    fake_db = _patch_crm(monkeypatch, facet)
    await crm.get_sales_customers(customer_type="new", limit=10,
                                  credentials=None)
    assert {"$match": {"total_bookings": {"$lte": 1}}} in _facet_stage(fake_db)["page"]


async def test_crm_customers_unknown_type_matches_nothing(monkeypatch):
    # legacy: an unknown type filtered EVERY customer out -> empty -> sample data
    facet = [{"page": [], "stats": []}]
    fake_db = _patch_crm(monkeypatch, facet)
    res = await crm.get_sales_customers(customer_type="bogus", limit=10,
                                        credentials=None)
    assert {"$match": {"_id": {"$exists": False}}} in _facet_stage(fake_db)["page"]
    # empty -> sample fallback (same shape/counts as legacy)
    assert len(res["customers"]) == 2
    assert res["count"] == 2
    assert res["vip_count"] == 1
    assert res["corporate_count"] == 1


async def test_crm_customers_empty_returns_sample(monkeypatch):
    facet = [{"page": [], "stats": [{"count": 0, "vip_count": 0,
                                     "corporate_count": 0}]}]
    fake_db = _patch_crm(monkeypatch, facet)
    res = await crm.get_sales_customers(customer_type=None, limit=50,
                                        credentials=None)
    assert res["count"] == 2          # sample fallback len
    assert res["vip_count"] == 1
    assert res["corporate_count"] == 1
    names = {c["guest_name"] for c in res["customers"]}
    assert names == {"Ahmet Yılmaz", "Ayşe Demir"}


# --------------------------------------------------------------------------- #
# GM mobile critical-issues — bounded candidate scan                          #
# --------------------------------------------------------------------------- #
class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self.sort_args = None
        self.limit_arg = None

    def sort(self, field, direction):
        self.sort_args = (field, direction)
        return self

    def limit(self, n):
        self.limit_arg = n
        return self

    async def to_list(self, _n):
        return list(self._docs)

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self, docs):
        self._docs = docs
        self.last_cursor = None

    def find(self, *a, **k):
        cur = _Cursor(self._docs)
        self.last_cursor = cur
        return cur


class _MDB:
    def __init__(self, tasks, bookings, rooms):
        self.tasks = _Coll(tasks)
        self.bookings = _Coll(bookings)
        self.rooms = _Coll(rooms)


async def test_critical_issues_candidate_scan_is_bounded(monkeypatch):
    tasks = [{"id": "task1", "title": "Leak", "description": "d",
              "room_number": "101", "priority": "urgent", "status": "open",
              "created_at": "2026-06-10"}]
    bookings = [
        {"id": "b1", "room_id": "r1", "room_number": "201", "guest_name": "X",
         "guest_id": "g1", "created_at": "2026-06-12"},
        {"id": "b2", "room_id": "r2", "room_number": "202", "guest_name": "Y",
         "guest_id": "g2", "created_at": "2026-06-11"},
    ]
    rooms = [{"id": "r1"}]  # only r1 is occupied -> only b1 is an overbooking
    fake_db = _MDB(tasks, bookings, rooms)
    monkeypatch.setattr(mdash, "db", fake_db)

    async def _user(_creds):
        return types.SimpleNamespace(tenant_id="t1")

    monkeypatch.setattr(mdash, "get_current_user", _user)

    res = await mdash.get_critical_issues_mobile(limit=5, credentials=None)

    # the formerly-unbounded candidate fetch is now top-k bounded
    bc = fake_db.bookings.last_cursor
    assert bc.sort_args == ("created_at", -1)
    assert bc.limit_arg == mdash._CRITICAL_CANDIDATE_CAP

    issues = res["critical_issues"]
    by_type = {i["type"] for i in issues}
    assert "maintenance" in by_type
    assert "overbooking" in by_type
    overbookings = [i for i in issues if i["type"] == "overbooking"]
    assert len(overbookings) == 1
    assert overbookings[0]["room_number"] == "201"          # b1 (r1 occupied)
    assert res["total_count"] == len(issues)
