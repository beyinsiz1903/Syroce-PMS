"""Task #209 — Negative stock guard for /api/accounting/inventory/movement.

Verifies F8F spec 70 § C invariant: out-movement with quantity > current_stock
must reject (4xx) and item.quantity must never go negative.

Lives as a live HTTP integration test against the demo backend (port 8000)
to match the existing conftest fixture pattern.
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set — integration tests require a running server",
)


def _create_item(headers, qty):
    sku = f"T209_{uuid.uuid4().hex[:10].upper()}"
    payload = {
        "name": f"T209 guard item {sku}",
        "sku": sku,
        "category": "amenity",
        "unit": "piece",
        "quantity": qty,
        "unit_cost": 1.0,
        "reorder_level": 1,
    }
    r = requests.post(
        f"{BASE_URL}/api/accounting/inventory",
        json=payload,
        headers=headers,
        timeout=15,
    )
    if r.status_code in (401, 403):
        pytest.skip(f"demo user lacks inventory create perm (status={r.status_code})")
    assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert body.get("id"), f"create response missing id: {body}"
    return body["id"]


def _read_qty(headers, item_id):
    r = requests.get(
        f"{BASE_URL}/api/accounting/inventory", headers=headers, timeout=15
    )
    assert r.status_code == 200, f"list failed: {r.status_code}"
    items = r.json().get("items") or []
    for it in items:
        if it.get("id") == item_id:
            return it.get("quantity")
    return None


def _movement(headers, item_id, mtype, qty, unit_cost=1.0):
    params = {
        "item_id": item_id,
        "movement_type": mtype,
        "quantity": qty,
        "unit_cost": unit_cost,
        "reference": f"T209_{mtype.upper()}",
        "notes": "task #209 guard test",
    }
    return requests.post(
        f"{BASE_URL}/api/accounting/inventory/movement",
        params=params,
        headers=headers,
        timeout=15,
    )


class TestNegativeStockGuard:
    def test_a_sufficient_stock_out_decrements(self, demo_auth_headers):
        item_id = _create_item(demo_auth_headers, 10)
        r = _movement(demo_auth_headers, item_id, "out", 3)
        assert r.status_code in (200, 201), f"out failed: {r.status_code} {r.text[:200]}"
        assert _read_qty(demo_auth_headers, item_id) == 7

    def test_b_insufficient_stock_out_rejected(self, demo_auth_headers):
        item_id = _create_item(demo_auth_headers, 5)
        r = _movement(demo_auth_headers, item_id, "out", 50)
        # ADR contract: insufficient stock MUST be 409 (not generic 4xx).
        assert r.status_code == 409, (
            f"insufficient stock must be 409 per ADR contract; got "
            f"{r.status_code} {r.text[:200]}"
        )
        # Detail body must surface requested + available for client UX.
        body_text = r.text.lower()
        assert "requested" in body_text and "available" in body_text, (
            f"409 body must mention requested+available; got {r.text[:200]}"
        )
        qty = _read_qty(demo_auth_headers, item_id)
        assert qty is not None and qty == 5, (
            f"qty must remain unchanged after reject; got {qty}"
        )

    def test_c_exact_boundary_out_zero(self, demo_auth_headers):
        item_id = _create_item(demo_auth_headers, 5)
        r = _movement(demo_auth_headers, item_id, "out", 5)
        assert r.status_code in (200, 201), f"exact-boundary out failed: {r.status_code}"
        assert _read_qty(demo_auth_headers, item_id) == 0

    def test_d_zero_quantity_rejected(self, demo_auth_headers):
        item_id = _create_item(demo_auth_headers, 5)
        r = _movement(demo_auth_headers, item_id, "out", 0)
        assert r.status_code == 422, f"zero qty must be 422; got {r.status_code}"

    def test_e_negative_quantity_rejected(self, demo_auth_headers):
        item_id = _create_item(demo_auth_headers, 5)
        r = _movement(demo_auth_headers, item_id, "out", -3)
        assert r.status_code == 422, f"negative qty must be 422; got {r.status_code}"

    def test_f_unknown_movement_type_rejected(self, demo_auth_headers):
        item_id = _create_item(demo_auth_headers, 5)
        r = _movement(demo_auth_headers, item_id, "bogus", 1)
        assert r.status_code == 422, (
            f"unknown movement_type must be 422; got {r.status_code}"
        )

    def test_g_in_movement_increments(self, demo_auth_headers):
        item_id = _create_item(demo_auth_headers, 5)
        r = _movement(demo_auth_headers, item_id, "in", 7)
        assert r.status_code in (200, 201)
        assert _read_qty(demo_auth_headers, item_id) == 12

    def test_h_adjustment_to_zero_ok(self, demo_auth_headers):
        item_id = _create_item(demo_auth_headers, 5)
        r = _movement(demo_auth_headers, item_id, "adjustment", 0)
        assert r.status_code in (200, 201)
        assert _read_qty(demo_auth_headers, item_id) == 0

    def test_i_adjustment_negative_rejected(self, demo_auth_headers):
        item_id = _create_item(demo_auth_headers, 5)
        r = _movement(demo_auth_headers, item_id, "adjustment", -1)
        assert r.status_code == 422
        assert _read_qty(demo_auth_headers, item_id) == 5

    def test_j_unknown_item_id_404(self, demo_auth_headers):
        r = _movement(demo_auth_headers, f"nonexistent-{uuid.uuid4()}", "out", 1)
        assert r.status_code == 404, (
            f"unknown item must be 404; got {r.status_code}"
        )

    def test_l_create_negative_quantity_rejected(self, demo_auth_headers):
        """Task #210 — POST /api/accounting/inventory with quantity<0 must 422."""
        sku = f"T210_{uuid.uuid4().hex[:10].upper()}"
        payload = {
            "name": f"T210 negative create {sku}",
            "sku": sku,
            "category": "amenity",
            "unit": "piece",
            "quantity": -50,
            "unit_cost": 1.0,
            "reorder_level": 1,
        }
        r = requests.post(
            f"{BASE_URL}/api/accounting/inventory",
            json=payload,
            headers=demo_auth_headers,
            timeout=15,
        )
        if r.status_code in (401, 403):
            pytest.skip(f"demo user lacks inventory create perm (status={r.status_code})")
        assert r.status_code == 422, (
            f"create with negative qty must be 422; got {r.status_code} {r.text[:200]}"
        )

    def test_m_create_zero_quantity_allowed(self, demo_auth_headers):
        item_id = _create_item(demo_auth_headers, 0)
        assert _read_qty(demo_auth_headers, item_id) == 0

    def test_n_create_positive_quantity_allowed(self, demo_auth_headers):
        item_id = _create_item(demo_auth_headers, 25)
        assert _read_qty(demo_auth_headers, item_id) == 25

    def test_o_shadow_create_negative_quantity_rejected(self, demo_auth_headers):
        """Task #210 — shadow handler (query-param form) must also 422 on neg qty."""
        sku = f"T210S_{uuid.uuid4().hex[:10].upper()}"
        params = {
            "name": f"T210 shadow neg {sku}",
            "sku": sku,
            "category": "amenity",
            "unit": "piece",
            "quantity": -10,
            "unit_cost": 1.0,
            "reorder_level": 1,
        }
        r = requests.post(
            f"{BASE_URL}/api/accounting/inventory",
            params=params,
            headers=demo_auth_headers,
            timeout=15,
        )
        if r.status_code in (401, 403):
            pytest.skip(f"demo user lacks inventory create perm (status={r.status_code})")
        assert r.status_code == 422, (
            f"shadow create with negative qty must be 422; got {r.status_code} {r.text[:200]}"
        )

    def test_k_race_two_parallel_out_one_rejected(self, demo_auth_headers):
        """Concurrent out-movements totalling more than stock must reject one."""
        import concurrent.futures

        item_id = _create_item(demo_auth_headers, 10)

        def fire():
            return _movement(demo_auth_headers, item_id, "out", 8)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(fire)
            f2 = ex.submit(fire)
            r1, r2 = f1.result(), f2.result()

        oks = sum(1 for r in (r1, r2) if r.status_code in (200, 201))
        # Race loser MUST be 409 (atomic-guard contract). Any other 4xx
        # would indicate the loser bypassed the atomic update path.
        rejects = sum(1 for r in (r1, r2) if r.status_code == 409)
        assert oks == 1 and rejects == 1, (
            f"expected exactly one OK and one 409; got "
            f"r1={r1.status_code} r2={r2.status_code}"
        )
        qty = _read_qty(demo_auth_headers, item_id)
        assert qty is not None and qty >= 0, (
            f"final qty must never be negative; got {qty}"
        )
        assert qty == 2, f"final qty should be 10-8=2; got {qty}"
