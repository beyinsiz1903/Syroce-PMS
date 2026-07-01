"""
Task #174 — B2B per-subrouter scope enforcement (unit-level, no live server).

Verifies:
  - normalize_scopes(): unknown scope -> 400, valid subset normalized to
    canonical order, empty/None -> unrestricted (None).
  - authenticate_b2b_agency(): scoped key reaches granted sub-router, is denied
    (403) on a sub-router outside its scope, while a legacy unscoped key keeps
    full access (fail-open only for legacy keys, fail-closed for scoped keys).
  - Missing / invalid key -> 401; inactive agency -> 403.
"""
import hashlib

import pytest
from fastapi import HTTPException

from routers.b2b_api import _scope
from routers.b2b_api._scope import (
    B2B_SCOPES,
    authenticate_b2b_agency,
    normalize_scopes,
)


def _hash(k: str) -> str:
    return hashlib.sha256(k.encode()).hexdigest()


class _Coll:
    def __init__(self, find_result=None):
        self._find_result = find_result
        self.updates = []

    async def find_one(self, *_a, **_k):
        return self._find_result

    async def update_one(self, flt, update, *_a, **_k):
        self.updates.append((flt, update))
        return None


class _FakeSysDb:
    def __init__(self, key_doc, agency_doc):
        self.agency_api_keys = _Coll(key_doc)
        self.agencies = _Coll(agency_doc)


@pytest.fixture
def patch_sysdb(monkeypatch):
    """Install a fake system DB + no-op tenant context for _scope."""
    state = {}

    def _factory(key_doc, agency_doc):
        fake = _FakeSysDb(key_doc, agency_doc)
        state["fake"] = fake

        def _get_system_db():
            return fake

        monkeypatch.setattr("core.tenant_db.get_system_db", _get_system_db)
        monkeypatch.setattr("core.tenant_db.set_tenant_context", lambda *_a, **_k: None)
        return fake

    return _factory


# ── normalize_scopes ───────────────────────────────────────────────

def test_normalize_none_and_empty_is_unrestricted():
    assert normalize_scopes(None) is None
    assert normalize_scopes([]) is None
    assert normalize_scopes(["", "   "]) is None


def test_normalize_valid_subset_canonical_order():
    out = normalize_scopes(["wake_up", "housekeeping", "wake_up"])
    # de-duplicated + canonical (B2B_SCOPES) ordering: housekeeping before wake_up
    assert out == ["housekeeping", "wake_up"]


def test_normalize_unknown_scope_rejected_400():
    with pytest.raises(HTTPException) as ei:
        normalize_scopes(["housekeeping", "not_a_router"])
    assert ei.value.status_code == 400
    assert "not_a_router" in ei.value.detail


def test_all_canonical_scopes_accepted():
    out = normalize_scopes(list(B2B_SCOPES))
    assert out == list(B2B_SCOPES)


# ── authenticate_b2b_agency scope enforcement ──────────────────────

RAW = "syroce_b2b_TESTKEY_0001"
ACTIVE_AGENCY = {"id": "ag-1", "name": "Test Agency", "commission_rate": 5, "status": "active"}


@pytest.mark.asyncio
async def test_scoped_key_allows_granted_subrouter(patch_sysdb):
    key_doc = {
        "agency_id": "ag-1",
        "tenant_id": "t-1",
        "key_hash": _hash(RAW),
        "is_active": True,
        "scopes": ["housekeeping", "wake_up"],
    }
    patch_sysdb(key_doc, ACTIVE_AGENCY)
    ctx = await authenticate_b2b_agency(RAW, required_scope="housekeeping")
    assert ctx["agency_id"] == "ag-1"
    assert ctx["tenant_id"] == "t-1"
    assert ctx["scopes"] == ["housekeeping", "wake_up"]


@pytest.mark.asyncio
async def test_scoped_key_denies_ungranted_subrouter_403(patch_sysdb):
    key_doc = {
        "agency_id": "ag-1",
        "tenant_id": "t-1",
        "key_hash": _hash(RAW),
        "is_active": True,
        "scopes": ["housekeeping"],
    }
    patch_sysdb(key_doc, ACTIVE_AGENCY)
    with pytest.raises(HTTPException) as ei:
        await authenticate_b2b_agency(RAW, required_scope="folio")
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_legacy_unscoped_key_keeps_full_access(patch_sysdb):
    key_doc = {
        "agency_id": "ag-1",
        "tenant_id": "t-1",
        "key_hash": _hash(RAW),
        "is_active": True,
        # no "scopes" field -> legacy unrestricted key
    }
    patch_sysdb(key_doc, ACTIVE_AGENCY)
    for scope in B2B_SCOPES:
        ctx = await authenticate_b2b_agency(RAW, required_scope=scope)
        assert ctx["agency_id"] == "ag-1"
        assert ctx["scopes"] is None


@pytest.mark.asyncio
async def test_explicit_none_scopes_is_unrestricted(patch_sysdb):
    key_doc = {
        "agency_id": "ag-1",
        "tenant_id": "t-1",
        "key_hash": _hash(RAW),
        "is_active": True,
        "scopes": None,
    }
    patch_sysdb(key_doc, ACTIVE_AGENCY)
    ctx = await authenticate_b2b_agency(RAW, required_scope="identity")
    assert ctx["scopes"] is None


@pytest.mark.asyncio
async def test_missing_key_401(patch_sysdb):
    patch_sysdb(None, None)
    with pytest.raises(HTTPException) as ei:
        await authenticate_b2b_agency(None, required_scope="folio")
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_invalid_key_401(patch_sysdb):
    # find_one returns None -> unknown key
    patch_sysdb(None, ACTIVE_AGENCY)
    with pytest.raises(HTTPException) as ei:
        await authenticate_b2b_agency("syroce_b2b_BOGUS", required_scope="folio")
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_inactive_agency_403(patch_sysdb):
    key_doc = {
        "agency_id": "ag-1",
        "tenant_id": "t-1",
        "key_hash": _hash(RAW),
        "is_active": True,
        "scopes": ["folio"],
    }
    # agencies.find_one (status active) returns None -> inactive
    patch_sysdb(key_doc, None)
    with pytest.raises(HTTPException) as ei:
        await authenticate_b2b_agency(RAW, required_scope="folio")
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_scope_denied_does_not_bump_usage(patch_sysdb):
    """A scope-denied call must not increment usage_count (deny before write)."""
    key_doc = {
        "agency_id": "ag-1",
        "tenant_id": "t-1",
        "key_hash": _hash(RAW),
        "is_active": True,
        "scopes": ["housekeeping"],
    }
    fake = patch_sysdb(key_doc, ACTIVE_AGENCY)
    with pytest.raises(HTTPException):
        await authenticate_b2b_agency(RAW, required_scope="folio")
    assert fake.agency_api_keys.updates == []
