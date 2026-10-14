"""Legacy hotel-bound agencies move onto the marketplace."""

import copy

import pytest

from routers import agency_contracts, agency_migration


def _match(doc, query):
    for key, cond in query.items():
        value = doc.get(key)
        if isinstance(cond, dict):
            for op, arg in cond.items():
                if op == "$in" and value not in arg:
                    return False
                if op == "$ne" and value == arg:
                    return False
                if op == "$gte" and not (value is not None and value >= arg):
                    return False
                if op == "$type" and not isinstance(value, str):
                    return False
        elif value != cond:
            return False
    return True


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _n=None):
        return self.rows

    def __aiter__(self):
        self._it = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration from None


class _Coll:
    def __init__(self, rows=None):
        self.rows = [copy.deepcopy(r) for r in rows or []]

    def find(self, query, *_a, **_k):
        return _Cursor([copy.deepcopy(r) for r in self.rows if _match(r, query)])

    async def find_one(self, query, *_a, **_k):
        hits = [r for r in self.rows if _match(r, query)]
        return copy.deepcopy(hits[0]) if hits else None

    async def count_documents(self, query):
        return sum(1 for r in self.rows if _match(r, query))

    async def insert_one(self, doc):
        self.rows.append(copy.deepcopy(doc))

    async def update_one(self, query, update, upsert=False):
        for r in self.rows:
            if _match(r, query):
                r.update(update.get("$set", {}))
                return
        if upsert:
            self.rows.append({**update.get("$setOnInsert", {}), **update.get("$set", {})})


class _DB:
    def __init__(self, **colls):
        self.colls = colls

    def __getattr__(self, name):
        return self.colls.setdefault(name, _Coll())


@pytest.fixture
def db(monkeypatch):
    sysdb = _DB(
        agencies=_Coll([{"id": "L1", "tenant_id": "t1", "status": "active", "name": "Atlas Turizm", "contact_email": "ops@atlas.test", "commission_rate": 10}]),
        agency_contracts=_Coll([{"id": "c-legacy", "tenant_id": "t1", "agency_id": "L1", "is_active": True, "contract_type": "net_rate",
                                 "start_date": "2026-01-01", "end_date": "2099-12-31", "credit_limit": 50000, "credit_currency": "TRY",
                                 "season_rates": [{"room_type_id": "Superior", "season_start": "2026-11-01", "season_end": "2026-11-30", "price": 700}]}]),
        users=_Coll([
            {"id": "u1", "tenant_id": "t1", "agency_id": "L1", "role": "agency_admin", "_hash_email": "h1", "password_hash": "bcrypt$x"},
            {"id": "u2", "tenant_id": "t1", "agency_id": "L1", "role": "agency_agent", "_hash_email": "h2", "hashed_password": "bcrypt$y"},
            {"id": "other", "tenant_id": None, "agency_id": "M-OTHER", "role": "marketplace_agent", "_hash_email": "h2"},
        ]),
        bookings=_Coll([
            {"id": "b-future", "tenant_id": "t1", "agency_id": "L1", "status": "confirmed", "check_in": "2099-01-01T14:00:00", "check_out": "2099-01-03T11:00:00",
             "total_amount": 2000, "agency_commission_rate": 10, "agency_commission_amount": 200, "currency": "TRY"},
            {"id": "b-past", "tenant_id": "t1", "agency_id": "L1", "status": "checked_out", "check_in": "2020-01-01", "check_out": "2020-01-02"},
        ]),
        marketplace_agencies=_Coll([]),
        marketplace_listings=_Coll([{"tenant_id": "t1", "is_listed": True, "hotel_name": "Demo"}]),
        tenants=_Coll([{"id": "t1", "property_name": "Demo"}]),
    )
    monkeypatch.setattr(agency_migration, "get_system_db", lambda: sysdb)

    async def no_indexes():
        return None

    async def code(_db):
        return "SOZ-2026-9999"

    monkeypatch.setattr(agency_contracts, "_ensure_indexes", no_indexes)
    monkeypatch.setattr(agency_contracts, "_next_contract_code", code)
    return sysdb


def _request(dry_run, target=None):
    return agency_migration.MigrationRequest(tenant_id="t1", dry_run=dry_run,
                                             items=[agency_migration.MigrationItem(legacy_agency_id="L1", marketplace_agency_id=target)])


@pytest.mark.asyncio
async def test_preview_and_dry_run_write_nothing(db):
    preview = await agency_migration.migration_preview(tenant_id="t1", _=True)
    row = preview["agencies"][0]
    assert (row["user_count"], row["future_bookings"], row["season_rate_count"]) == (2, 1, 1)

    result = await agency_migration.migration_execute(_request(True), _=True)
    assert result["results"][0]["actions"]
    assert db.marketplace_agencies.rows == [] and db.agencies.rows[0]["status"] == "active"


@pytest.mark.asyncio
async def test_execute_moves_agency_contract_users_and_future_bookings(db):
    result = (await agency_migration.migration_execute(_request(False), _=True))["results"][0]
    target_id = result["marketplace_agency_id"]

    assert db.marketplace_agencies.rows[0]["name"] == "Atlas Turizm"
    contract = next(c for c in db.agency_contracts.rows if c.get("contract_code"))
    assert (contract["status"], contract["contract_type"], contract["commission_pct"]) == ("approved", "net_rate", 0.0)
    assert contract["season_rates"][0]["price"] == 700 and contract["credit_limit"] == 50000

    u1 = next(u for u in db.users.rows if u["id"] == "u1")
    assert (u1["role"], u1["agency_id"], u1["tenant_id"], u1["hashed_password"]) == ("marketplace_agent", target_id, None, "bcrypt$x")
    u2 = next(u for u in db.users.rows if u["id"] == "u2")
    assert u2["role"] == "agency_agent"  # e-mail already used by another marketplace agency
    assert any("başka bir marketplace" in s for s in result["skipped"])

    future = next(b for b in db.bookings.rows if b["id"] == "b-future")
    past = next(b for b in db.bookings.rows if b["id"] == "b-past")
    assert (future["agency_id"], past["agency_id"]) == (target_id, "L1")
    ledger = db.marketplace_bookings.rows[0]
    assert (ledger["id"], ledger["net_to_hotel"], ledger["check_in"]) == ("b-future", 1800.0, "2099-01-01")

    assert db.agencies.rows[0]["status"] == "migrated"
    assert db.agency_migrations.rows


@pytest.mark.asyncio
async def test_existing_marketplace_contract_is_kept(db):
    db.marketplace_agencies.rows.append({"id": "M1", "status": "active", "name": "Atlas"})
    db.agency_contracts.rows.append({"tenant_id": "t1", "agency_id": "M1", "status": "approved", "contract_code": "SOZ-1"})
    result = (await agency_migration.migration_execute(_request(False, "M1"), _=True))["results"][0]
    assert any("SOZ-1" in s for s in result["skipped"])
    assert sum(1 for c in db.agency_contracts.rows if c.get("contract_code")) == 1
