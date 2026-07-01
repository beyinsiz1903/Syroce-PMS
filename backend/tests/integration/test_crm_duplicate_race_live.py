"""Task #216 — live proof the duplicate safeguard holds under real concurrency.

Task #205 added DB-level partial unique indexes behind the read-then-insert
guards in ``routers.mice.create_account`` and
``domains.revenue.rms_router.sales.create_corporate_contract``, plus the
``DuplicateKeyError -> 409`` translation. Its unit tests verify the index
*parameters* and the translation with mocks, but never exercise a real
concurrent insert against MongoDB. The read-then-insert guard has a race
window: two near-simultaneous creates with the same identifier can both pass
``find_one``; only the unique index makes the losing write fail.

This module fires two TRULY simultaneous requests (via ``asyncio.gather``)
against a running backend and proves, end to end:

  * Exactly one create succeeds (2xx) and the other returns 409.
  * The collection ends with exactly one row for that identifier.
  * No false positive on blank identifiers (partial index excludes blanks).
  * No false positive on piggybacked banquet-competitor rows
    (``account_type != "client"`` is outside the unique index).

Each race test first asserts the relevant partial unique index is actually
present — the index build (``_ensure_indexes``) is best-effort and silently
*deferred* if pre-existing duplicate data exists, which would leave the race
window open. We assert presence so the test can never fake-green over a
missing backstop. The ``contact_email`` contract index is currently blocked
by legacy duplicate residue, so that one race is precondition-skipped with a
diagnostic rather than asserted (the backstop genuinely is not enforced there).

Integration style — requires a running backend (``VITE_BACKEND_URL``) and the
same MongoDB the backend uses (``MONGO_URL``/``DB_NAME``). The demo login maps
to the pilot tenant, so every row this test creates (incl. the directly-seeded
competitor) is purged in ``finally`` regardless of outcome — net-zero drift.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import httpx
import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")


def _backend_reachable() -> bool:
    if not BASE_URL:
        return False
    try:
        # /api/health 307-redirects to a trailing slash; requests follows it.
        resp = requests.get(f"{BASE_URL}/api/health", timeout=5)
        return resp.status_code < 500
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _backend_reachable(),
    reason="Live concurrency test needs a running backend at VITE_BACKEND_URL",
)


# ── Raw Mongo access (same DB the backend uses) ──────────────────────────
# Seeding piggyback rows, asserting exact row counts, checking index presence,
# and guaranteed cleanup all need direct DB access (CompetitorIn has no tax_no
# field, contracts have no DELETE endpoint). A fresh client binds to the
# running (session) event loop.


def _raw_db():
    from motor.motor_asyncio import AsyncIOMotorClient

    url = os.environ.get("MONGO_URL") or os.environ.get("MONGO_ATLAS_URI")
    name = os.environ.get("DB_NAME", "syroce-pms")
    client = AsyncIOMotorClient(url)
    return client, client[name]


async def _has_unique_index(coll: str, name: str) -> bool:
    client, db = _raw_db()
    try:
        info = await db[coll].index_information()
        return name in info and bool(info[name].get("unique"))
    finally:
        client.close()


async def _count(coll: str, flt: dict) -> int:
    client, db = _raw_db()
    try:
        return await db[coll].count_documents(flt)
    finally:
        client.close()


async def _purge(coll: str, flt: dict) -> None:
    """Bulletproof teardown: remove every row matching the unique identifier.

    Runs even when the safeguard *fails* to fire (both creates succeed), so a
    regression never leaks duplicate rows into the (pilot) tenant.
    """
    client, db = _raw_db()
    try:
        await db[coll].delete_many(flt)
    finally:
        client.close()


_CLIENT_OR = [{"account_type": {"$exists": False}}, {"account_type": "client"}]


# ── Helpers ──────────────────────────────────────────────────────────────


def _tag() -> str:
    return uuid.uuid4().hex[:10].upper()


async def _fire_two(path: str, payload_a: dict, payload_b: dict,
                    headers: dict) -> list[httpx.Response]:
    """Fire two POSTs as concurrently as the loop allows and return both."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        return await asyncio.gather(
            client.post(path, json=payload_a, headers=headers),
            client.post(path, json=payload_b, headers=headers),
        )


def _assert_exactly_one_won(responses: list[httpx.Response]) -> None:
    """Exactly one 2xx winner, exactly one 409 loser."""
    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 409], (
        f"expected one 2xx + one 409, got {codes}: "
        f"{[r.text[:200] for r in responses]}")


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def demo_tenant_id(demo_auth_headers) -> str:
    """Resolve the demo user's tenant_id via a throwaway account (then delete).

    Creating one account also triggers the backend's ``_ensure_indexes`` so the
    partial unique indexes exist before the race tests run.
    """
    probe_tax = f"PROBE-{_tag()}"
    r = requests.post(f"{BASE_URL}/api/mice/accounts",
                      json={"name": f"Probe {probe_tax}", "tax_no": probe_tax},
                      headers=demo_auth_headers)
    assert r.status_code == 200, f"probe create failed: {r.status_code} {r.text}"
    doc = r.json()
    tenant_id = doc["tenant_id"]
    requests.delete(f"{BASE_URL}/api/mice/accounts/{doc['id']}",
                    headers=demo_auth_headers)
    return tenant_id


# ── Tests: accounts ──────────────────────────────────────────────────────


async def test_concurrent_account_create_same_tax_no_one_wins(
        demo_auth_headers, demo_tenant_id):
    """Two simultaneous /api/mice/accounts (same tax_no) → 1 wins, 1×409, 1 row."""
    assert await _has_unique_index("mice_accounts", "uniq_mice_acc_client_taxno"), (
        "uniq_mice_acc_client_taxno is missing — the race backstop is NOT "
        "enforced (index build deferred by pre-existing duplicate data)")

    tax_no = f"RACE-ACC-{_tag()}"
    acct_flt = {"tenant_id": demo_tenant_id, "tax_no": tax_no, "$or": _CLIENT_OR}
    try:
        responses = await _fire_two(
            "/api/mice/accounts",
            {"name": "Race Co A", "tax_no": tax_no},
            {"name": "Race Co B", "tax_no": tax_no},
            demo_auth_headers)
        _assert_exactly_one_won(responses)
        # The index — not the app-level guard — is what proves race safety.
        assert await _count("mice_accounts", acct_flt) == 1
    finally:
        await _purge("mice_accounts", acct_flt)


async def test_concurrent_account_create_same_email_one_wins(
        demo_auth_headers, demo_tenant_id):
    """Same race, collision on email instead of tax_no → 1 wins, 1×409, 1 row."""
    assert await _has_unique_index("mice_accounts", "uniq_mice_acc_client_email"), (
        "uniq_mice_acc_client_email is missing — the race backstop is NOT "
        "enforced (index build deferred by pre-existing duplicate data)")

    email = f"race-{_tag().lower()}@example.invalid"
    acct_flt = {"tenant_id": demo_tenant_id, "email": email, "$or": _CLIENT_OR}
    try:
        responses = await _fire_two(
            "/api/mice/accounts",
            {"name": "Email Race A", "email": email},
            {"name": "Email Race B", "email": email},
            demo_auth_headers)
        _assert_exactly_one_won(responses)
        assert await _count("mice_accounts", acct_flt) == 1
    finally:
        await _purge("mice_accounts", acct_flt)


async def test_blank_identifiers_no_false_positive(
        demo_auth_headers, demo_tenant_id):
    """Two accounts with blank tax_no/email both succeed — partial index skips blanks."""
    name_a, name_b = f"Blank A {_tag()}", f"Blank B {_tag()}"
    try:
        responses = await _fire_two(
            "/api/mice/accounts",
            {"name": name_a, "tax_no": "", "email": ""},
            {"name": name_b, "tax_no": "", "email": ""},
            demo_auth_headers)
        codes = sorted(r.status_code for r in responses)
        assert codes == [200, 200], (
            f"blank identifiers must not collide, got {codes}: "
            f"{[r.text[:200] for r in responses]}")
    finally:
        await _purge("mice_accounts",
                     {"tenant_id": demo_tenant_id, "name": {"$in": [name_a, name_b]}})


async def test_piggyback_competitor_no_false_positive(
        demo_auth_headers, demo_tenant_id):
    """A banquet-competitor row sharing the tax_no must NOT block a client create.

    The unique index is scoped to ``account_type == "client"``; piggybacked
    rows (``account_type == "banquet_competitor"``) live in the same collection
    but outside the index, so they must never produce a false 409.
    """
    tax_no = f"PIGGY-{_tag()}"
    comp_id = str(uuid.uuid4())
    client, db = _raw_db()
    try:
        await db.mice_accounts.insert_one({
            "id": comp_id, "tenant_id": demo_tenant_id,
            "account_type": "banquet_competitor",
            "name": f"Competitor {tax_no}", "tax_no": tax_no,
        })
    finally:
        client.close()

    acct_flt = {"tenant_id": demo_tenant_id, "tax_no": tax_no, "$or": _CLIENT_OR}
    try:
        r = requests.post(f"{BASE_URL}/api/mice/accounts",
                          json={"name": f"Client {tax_no}", "tax_no": tax_no},
                          headers=demo_auth_headers)
        assert r.status_code == 200, (
            f"client create must not collide with a piggyback row: "
            f"{r.status_code} {r.text}")
        # Exactly one *client* row; the competitor row is untouched.
        assert await _count("mice_accounts", acct_flt) == 1
    finally:
        await _purge("mice_accounts", acct_flt)
        await _purge("mice_accounts",
                     {"id": comp_id, "tenant_id": demo_tenant_id})


# ── Tests: corporate contracts ───────────────────────────────────────────


def _contract_payload(rate_code: str, **over) -> dict:
    base = {
        "company_name": "Race Holdings",
        "contract_type": "negotiated",
        "rate_code": rate_code,
        "start_date": "2040-01-01",
        "end_date": "2040-12-31",
        "contact_person": "Race Contact",
        "contact_email": f"contract-{_tag().lower()}@example.invalid",
        "contact_phone": "+900000000000",
    }
    base.update(over)
    return base


async def test_concurrent_contract_create_same_rate_code_one_wins(
        demo_auth_headers, demo_tenant_id):
    """Two simultaneous corporate-contract creates (same rate_code) → 1 wins, 1×409."""
    assert await _has_unique_index(
        "corporate_contracts", "uniq_corp_contract_rate_code"), (
        "uniq_corp_contract_rate_code is missing — the race backstop is NOT "
        "enforced (index build deferred by pre-existing duplicate data)")

    rate_code = f"RC-{_tag()}"
    flt = {"tenant_id": demo_tenant_id, "rate_code": rate_code}
    try:
        responses = await _fire_two(
            "/api/sales/corporate-contract",
            _contract_payload(rate_code, company_name="RC Co A"),
            _contract_payload(rate_code, company_name="RC Co B"),
            demo_auth_headers)
        _assert_exactly_one_won(responses)
        assert await _count("corporate_contracts", flt) == 1
    finally:
        await _purge("corporate_contracts", flt)


async def test_concurrent_contract_create_same_contact_email_one_wins(
        demo_auth_headers, demo_tenant_id):
    """Same race on contact_email.

    The ``uniq_corp_contract_contact_email`` partial unique index is currently
    *deferred* because legacy duplicate contact_email rows exist in another
    tenant (the index is global). Until that residue is cleaned the contact_email
    race backstop is genuinely OFF, so we precondition-skip with a diagnostic
    rather than fake-green — the rate_code test above already proves the
    index-backed mechanism works end to end.
    """
    if not await _has_unique_index(
            "corporate_contracts", "uniq_corp_contract_contact_email"):
        pytest.skip(
            "uniq_corp_contract_contact_email not built (deferred by legacy "
            "duplicate contact_email residue) — contact_email race backstop "
            "is NOT enforced in this DB; clean the residue to enable it")

    email = f"shared-{_tag().lower()}@example.invalid"
    flt = {"tenant_id": demo_tenant_id, "contact_email": email}
    try:
        responses = await _fire_two(
            "/api/sales/corporate-contract",
            _contract_payload(f"RC-{_tag()}", contact_email=email),
            _contract_payload(f"RC-{_tag()}", contact_email=email),
            demo_auth_headers)
        _assert_exactly_one_won(responses)
        assert await _count("corporate_contracts", flt) == 1
    finally:
        await _purge("corporate_contracts", flt)
