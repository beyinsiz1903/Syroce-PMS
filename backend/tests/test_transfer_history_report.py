"""Task #73 — Backend regression tests for the transfer history report.

Verifies `GET /api/accounting/inventory/transfers` (introduced for finance
reconciliation) correctly pairs both legs of a warehouse transfer, scopes
results to the calling tenant, and honours the inclusive `start_date` /
`end_date` filter.

Lives as a live HTTP integration test against the demo backend (port 8000)
to match the existing conftest fixture pattern (see
`test_inventory_negative_stock_guard.py`). Cross-tenant isolation uses
the same Mongo-seeded "Tenant B" pattern as `test_cross_tenant_isolation_e2e.py`.
"""
import os
import random
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
import requests
from pymongo import MongoClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms")
DB_NAME = os.environ.get("DB_NAME", "hotel_pms")
BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set — integration tests require a running server",
)


def _sync_db():
    client = MongoClient(MONGO_URL)
    return client, client[DB_NAME]


def _create_item(headers, qty, *, location, name_prefix="T73"):
    sku = f"{name_prefix}_{uuid.uuid4().hex[:10].upper()}"
    payload = {
        "name": f"{name_prefix} transfer item {sku}",
        "sku": sku,
        "category": "amenity",
        "unit": "piece",
        "quantity": qty,
        "unit_cost": 1.0,
        "reorder_level": 1,
        "location": location,
    }
    r = requests.post(
        f"{BASE_URL}/api/accounting/inventory",
        json=payload,
        headers=headers,
        timeout=15,
    )
    if r.status_code in (401, 403):
        pytest.skip(f"caller lacks inventory create perm (status={r.status_code})")
    assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert body.get("id"), f"create response missing id: {body}"
    return body["id"]


def _transfer(headers, src_id, dst_id, qty, *, reference=None, notes=None):
    payload = {
        "source_item_id": src_id,
        "destination_item_id": dst_id,
        "quantity": qty,
        "unit_cost": 1.0,
    }
    if reference is not None:
        payload["reference"] = reference
    if notes is not None:
        payload["notes"] = notes
    r = requests.post(
        f"{BASE_URL}/api/accounting/inventory/transfer",
        json=payload,
        headers=headers,
        timeout=15,
    )
    if r.status_code in (401, 403):
        pytest.skip(f"caller lacks transfer perm (status={r.status_code})")
    assert r.status_code in (200, 201), f"transfer failed: {r.status_code} {r.text[:200]}"
    return r.json()


def _history(headers, *, start_date=None, end_date=None, limit=None):
    params: dict = {}
    if start_date is not None:
        params["start_date"] = start_date
    if end_date is not None:
        params["end_date"] = end_date
    if limit is not None:
        params["limit"] = limit
    r = requests.get(
        f"{BASE_URL}/api/accounting/inventory/transfers",
        headers=headers,
        params=params,
        timeout=15,
    )
    if r.status_code in (401, 403):
        pytest.skip(f"caller lacks finance report perm (status={r.status_code})")
    assert r.status_code == 200, f"history failed: {r.status_code} {r.text[:200]}"
    return r.json()


def _find_transfer(history_body, transfer_id):
    transfers = history_body.get("transfers") or []
    for t in transfers:
        if t.get("transfer_id") == transfer_id:
            return t
    return None


# ── Tenant B seed helpers (mirrors test_cross_tenant_isolation_e2e.py) ────


class _TenantB:
    """Class-scoped Tenant B fixture container."""
    tenant: dict = {}
    user: dict = {}
    password = "t73-xtenant-pw"
    token: str = ""
    auth_mode: str = ""
    created_item_ids: list[str] = []
    transfer_ids: list[str] = []


def _seed_tenant_b() -> bool:
    try:
        from core._pwd import BcryptContext
    except Exception:
        return False
    pwd = BcryptContext()
    client, db = _sync_db()
    try:
        now = datetime.now(UTC)
        tenant_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        suffix = uuid.uuid4().hex[:8]
        _TenantB.tenant = {
            "id": tenant_id,
            "hotel_id": str(random.randint(800000, 899999)),
            "property_name": f"T73 X-Tenant Hotel {suffix}",
            "property_type": "hotel",
            "subscription_status": "active",
            "plan": "core_small_hotel",
            "modules": {
                "pms": True, "reports": True, "invoices": True, "ai": True,
                "finance": True, "accounting": True,
            },
            "created_at": now,
        }
        _TenantB.user = {
            "id": user_id,
            "tenant_id": tenant_id,
            "email": f"t73-xtenant-{suffix}@example.com",
            "username": f"t73-xtuser-{suffix}",
            "name": "T73 X-Tenant Admin",
            "role": "admin",
            "password": pwd.hash(_TenantB.password),
            "is_active": True,
            "created_at": now,
        }
        db.tenants.insert_one(_TenantB.tenant)
        db.users.insert_one(_TenantB.user)
        return True
    except Exception:
        return False
    finally:
        client.close()


def _login_tenant_b() -> str:
    try:
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "hotel_id": _TenantB.tenant["hotel_id"],
                "username": _TenantB.user["username"],
                "password": _TenantB.password,
            },
            timeout=10,
        )
        if r.status_code == 200:
            _TenantB.auth_mode = "real_login"
            return r.json()["access_token"]
    except Exception:
        pass
    secret = os.environ.get("JWT_SECRET")
    if secret:
        now = datetime.now(UTC)
        payload = {
            "user_id": _TenantB.user["id"],
            "tenant_id": _TenantB.user["tenant_id"],
            "iat": now,
            "jti": secrets.token_urlsafe(16),
            "exp": now + timedelta(minutes=60),
            "type": "access",
        }
        _TenantB.auth_mode = "manual_jwt_fallback"
        return pyjwt.encode(payload, secret, algorithm="HS256")
    return ""


def _nuke_tenant_b():
    if not _TenantB.tenant:
        return
    try:
        client, db = _sync_db()
        tid = _TenantB.tenant["id"]
        db.tenants.delete_many({"id": tid})
        db.users.delete_many({"tenant_id": tid})
        db.inventory_items.delete_many({"tenant_id": tid})
        db.stock_movements.delete_many({"tenant_id": tid})
        client.close()
    except Exception:
        pass


class TestTransferHistoryReport:
    @pytest.fixture(scope="class", autouse=True)
    def _class_setup(self):
        if not BASE_URL:
            pytest.skip("VITE_BACKEND_URL missing")
        if not _seed_tenant_b():
            pytest.skip("Tenant B seed failed (BcryptContext or Mongo unavailable)")
        _TenantB.token = _login_tenant_b()
        if not _TenantB.token:
            _nuke_tenant_b()
            pytest.skip(
                "Tenant B auth fixture unavailable: real login failed and "
                "JWT_SECRET fallback unavailable"
            )
        yield
        _nuke_tenant_b()

    @pytest.fixture
    def headers_b(self):
        return {
            "Authorization": f"Bearer {_TenantB.token}",
            "Content-Type": "application/json",
        }

    # ── A. Round-trip: transfer → history pairs both legs correctly ─────
    def test_a_history_returns_paired_row(self, demo_auth_headers):
        src_loc = f"WH-SRC-{uuid.uuid4().hex[:6]}"
        dst_loc = f"WH-DST-{uuid.uuid4().hex[:6]}"
        src_id = _create_item(demo_auth_headers, 50, location=src_loc)
        dst_id = _create_item(demo_auth_headers, 0, location=dst_loc)

        reference = f"T73-REF-{uuid.uuid4().hex[:6]}"
        transfer = _transfer(
            demo_auth_headers, src_id, dst_id, 12,
            reference=reference, notes="t73 round-trip",
        )
        transfer_id = transfer["transfer_id"]
        assert transfer_id, "transfer endpoint must return a transfer_id"

        body = _history(demo_auth_headers, limit=500)
        row = _find_transfer(body, transfer_id)
        assert row is not None, (
            f"new transfer {transfer_id} missing from history; "
            f"count={body.get('count')}"
        )

        # Both legs must be paired into a single row with correct fields.
        assert row["source_item_id"] == src_id, (
            f"source_item_id mismatch: expected {src_id}, got {row['source_item_id']}"
        )
        assert row["destination_item_id"] == dst_id, (
            f"destination_item_id mismatch: expected {dst_id}, "
            f"got {row['destination_item_id']}"
        )
        assert float(row["quantity"]) == 12.0, (
            f"quantity mismatch: expected 12.0, got {row['quantity']}"
        )
        assert row["reference"] == reference
        assert row.get("created_by"), "created_by must be populated from staff identity"
        assert row.get("created_at"), "created_at must be set on paired row"
        # Item names should be resolved with location suffix.
        assert row.get("source_item_name") and src_loc in row["source_item_name"], (
            f"source name should include location {src_loc}; got "
            f"{row.get('source_item_name')}"
        )
        assert row.get("destination_item_name") and dst_loc in row["destination_item_name"], (
            f"destination name should include location {dst_loc}; got "
            f"{row.get('destination_item_name')}"
        )

        # Pairing invariant: exactly one row per transfer_id (not two legs).
        all_for_id = [
            t for t in body.get("transfers", [])
            if t.get("transfer_id") == transfer_id
        ]
        assert len(all_for_id) == 1, (
            f"history must collapse both legs into one row; got {len(all_for_id)}"
        )

    # ── B. Cross-tenant isolation: Tenant B must not see Tenant A rows ──
    def test_b_cross_tenant_isolation(self, demo_auth_headers, headers_b):
        # Tenant A creates a transfer.
        src_a = _create_item(demo_auth_headers, 25, location=f"A-SRC-{uuid.uuid4().hex[:6]}")
        dst_a = _create_item(demo_auth_headers, 0, location=f"A-DST-{uuid.uuid4().hex[:6]}")
        tr_a = _transfer(demo_auth_headers, src_a, dst_a, 5, reference="T73-XTENANT-A")
        tid_a = tr_a["transfer_id"]

        # Tenant B creates its own transfer so the endpoint returns ≥1 row
        # (proves we're not just observing an empty-result false negative).
        src_b = _create_item(headers_b, 10, location=f"B-SRC-{uuid.uuid4().hex[:6]}",
                             name_prefix="T73B")
        dst_b = _create_item(headers_b, 0, location=f"B-DST-{uuid.uuid4().hex[:6]}",
                             name_prefix="T73B")
        _TenantB.created_item_ids.extend([src_b, dst_b])
        tr_b = _transfer(headers_b, src_b, dst_b, 3, reference="T73-XTENANT-B")
        tid_b = tr_b["transfer_id"]
        _TenantB.transfer_ids.append(tid_b)

        # Tenant B's history must include B's transfer but NOT A's.
        body_b = _history(headers_b, limit=500)
        b_ids = {t.get("transfer_id") for t in body_b.get("transfers", [])}
        assert tid_b in b_ids, (
            f"Tenant B must see own transfer {tid_b}; got ids={list(b_ids)[:5]}..."
        )
        assert tid_a not in b_ids, (
            f"Tenant B leak: Tenant A transfer {tid_a} visible in B's history"
        )
        # Belt-and-suspenders: no Tenant B row should reference a Tenant A
        # item id, regardless of transfer_id.
        leaked = [
            t for t in body_b.get("transfers", [])
            if t.get("source_item_id") in (src_a, dst_a)
            or t.get("destination_item_id") in (src_a, dst_a)
        ]
        assert not leaked, (
            f"Tenant B leak: rows reference Tenant A item ids: {leaked}"
        )

    # ── C. Date-range filter: inclusive start_date / end_date ───────────
    def test_c_date_range_filter_inclusive(self, demo_auth_headers):
        src = _create_item(demo_auth_headers, 30, location=f"D-SRC-{uuid.uuid4().hex[:6]}")
        dst = _create_item(demo_auth_headers, 0, location=f"D-DST-{uuid.uuid4().hex[:6]}")
        tr = _transfer(demo_auth_headers, src, dst, 4, reference="T73-DATE-FILTER")
        tid = tr["transfer_id"]

        # Look up the actual created_at to build inclusive/exclusive windows
        # that don't depend on wall-clock drift between client and server.
        baseline = _history(demo_auth_headers, limit=500)
        row = _find_transfer(baseline, tid)
        assert row is not None, "new transfer must appear in unfiltered history"
        created_at = row["created_at"]
        assert isinstance(created_at, str) and "T" in created_at, (
            f"created_at must be ISO string; got {created_at!r}"
        )

        ts = datetime.fromisoformat(created_at)
        # Inclusive window: [created_at, created_at] — must include the row.
        body_inc = _history(
            demo_auth_headers,
            start_date=created_at,
            end_date=created_at,
            limit=500,
        )
        assert _find_transfer(body_inc, tid) is not None, (
            f"inclusive window [{created_at}, {created_at}] must include the "
            f"transfer; count={body_inc.get('count')}"
        )

        # Exclusive window strictly BEFORE the transfer: must NOT include.
        before = (ts - timedelta(days=2)).isoformat()
        before_end = (ts - timedelta(seconds=1)).isoformat()
        body_before = _history(
            demo_auth_headers,
            start_date=before,
            end_date=before_end,
            limit=500,
        )
        assert _find_transfer(body_before, tid) is None, (
            f"window strictly before created_at ({before_end}) must NOT "
            f"include the transfer {tid}"
        )

        # Exclusive window strictly AFTER the transfer: must NOT include.
        after_start = (ts + timedelta(seconds=1)).isoformat()
        after_end = (ts + timedelta(days=2)).isoformat()
        body_after = _history(
            demo_auth_headers,
            start_date=after_start,
            end_date=after_end,
            limit=500,
        )
        assert _find_transfer(body_after, tid) is None, (
            f"window strictly after created_at ({after_start}) must NOT "
            f"include the transfer {tid}"
        )

        # Filter echo: response must reflect the filters used.
        echoed = body_inc.get("filters") or {}
        assert echoed.get("start_date") == created_at
        assert echoed.get("end_date") == created_at
