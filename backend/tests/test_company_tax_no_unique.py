"""Wave 9 — Corporate company tax_number uniqueness (per tenant).

Product decision: within a tenant the corporate tax_number is unique. Enforced
ONLY when a value is supplied (tax_number is optional; many companies legitimately
have none — backward-compatible). Whitespace is normalized.

Contained to the single create/update insert path; no other code inserts into
db.companies. Failures here mean the dup-guard regressed.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import domains.pms.misc.companies as companies_mod


class _Coll:
    def __init__(self, find_one_result=None):
        self._find_one_result = find_one_result
        self.find_one_queries = []
        self.inserts = []
        self.updates = []

    async def find_one(self, query, *a, **k):
        self.find_one_queries.append(query)
        return self._find_one_result

    async def insert_one(self, doc):
        self.inserts.append(doc)
        return SimpleNamespace(inserted_id="x")

    async def update_one(self, query, update, *a, **k):
        self.updates.append((query, update))
        return SimpleNamespace(modified_count=1)


def _user():
    return SimpleNamespace(tenant_id="t1")


def _payload(tax_number=None, name="Acme A.S."):
    return SimpleNamespace(
        tax_number=tax_number,
        model_dump=lambda: {
            "id": "c-new",
            "name": name,
            "tax_number": tax_number,
            "created_at": __import__("datetime").datetime(2026, 1, 1),
            "updated_at": __import__("datetime").datetime(2026, 1, 1),
        },
    )


@pytest.mark.asyncio
async def test_create_rejects_duplicate_tax_no(monkeypatch):
    coll = _Coll(find_one_result={"id": "c-existing", "tax_number": "1234567890"})
    monkeypatch.setattr(companies_mod, "db", SimpleNamespace(companies=coll))
    # patch Company so model_dump path doesn't depend on real schema
    monkeypatch.setattr(
        companies_mod, "Company",
        lambda **kw: SimpleNamespace(model_dump=lambda: _payload("1234567890").model_dump()),
    )
    with pytest.raises(HTTPException) as exc:
        await companies_mod.create_company(_payload("  1234567890  "), current_user=_user())
    assert exc.value.status_code == 409
    assert coll.inserts == []  # never inserted
    # dup query was tenant-scoped on the normalized value
    assert coll.find_one_queries[0]["tenant_id"] == "t1"
    assert coll.find_one_queries[0]["tax_number"] == "1234567890"


@pytest.mark.asyncio
async def test_create_allows_unique_tax_no(monkeypatch):
    coll = _Coll(find_one_result=None)
    monkeypatch.setattr(companies_mod, "db", SimpleNamespace(companies=coll))
    monkeypatch.setattr(
        companies_mod, "Company",
        lambda **kw: SimpleNamespace(model_dump=lambda: _payload("9999999999").model_dump()),
    )
    await companies_mod.create_company(_payload("9999999999"), current_user=_user())
    assert len(coll.inserts) == 1
    assert coll.inserts[0]["tax_number"] == "9999999999"  # normalized stored


@pytest.mark.asyncio
async def test_create_without_tax_no_skips_guard(monkeypatch):
    coll = _Coll(find_one_result={"id": "should-not-matter"})
    monkeypatch.setattr(companies_mod, "db", SimpleNamespace(companies=coll))
    monkeypatch.setattr(
        companies_mod, "Company",
        lambda **kw: SimpleNamespace(model_dump=lambda: _payload(None).model_dump()),
    )
    await companies_mod.create_company(_payload(None), current_user=_user())
    assert len(coll.inserts) == 1
    assert coll.find_one_queries == []  # no dup query when tax_number absent


@pytest.mark.asyncio
async def test_create_whitespace_only_tax_no_persists_none(monkeypatch):
    coll = _Coll(find_one_result=None)
    monkeypatch.setattr(companies_mod, "db", SimpleNamespace(companies=coll))
    monkeypatch.setattr(
        companies_mod, "Company",
        lambda **kw: SimpleNamespace(model_dump=lambda: _payload("   ").model_dump()),
    )
    await companies_mod.create_company(_payload("   "), current_user=_user())
    assert len(coll.inserts) == 1
    assert coll.inserts[0]["tax_number"] is None  # dirty whitespace not persisted
    assert coll.find_one_queries == []  # guard skipped (no real value)


@pytest.mark.asyncio
async def test_update_whitespace_only_tax_no_persists_none(monkeypatch):
    coll = _Coll()

    async def _find_one(query, *a, **k):
        coll.find_one_queries.append(query)
        return {"id": "c1", "tenant_id": "t1"}

    coll.find_one = _find_one
    monkeypatch.setattr(companies_mod, "db", SimpleNamespace(companies=coll))
    await companies_mod.update_company("c1", _payload("   "), current_user=_user())
    assert len(coll.updates) == 1
    _, update = coll.updates[0]
    assert update["$set"]["tax_number"] is None


@pytest.mark.asyncio
async def test_update_rejects_duplicate_tax_no_on_other_record(monkeypatch):
    coll = _Coll()

    async def _find_one(query, *a, **k):
        coll.find_one_queries.append(query)
        # first call: load the company being updated; later: dup lookup
        if query.get("id") == "c1" and "$ne" not in str(query):
            return {"id": "c1", "tenant_id": "t1"}
        return {"id": "c2", "tenant_id": "t1", "tax_number": "1234567890"}

    coll.find_one = _find_one
    monkeypatch.setattr(companies_mod, "db", SimpleNamespace(companies=coll))
    with pytest.raises(HTTPException) as exc:
        await companies_mod.update_company(
            "c1", _payload("1234567890"), current_user=_user()
        )
    assert exc.value.status_code == 409
    assert coll.updates == []
