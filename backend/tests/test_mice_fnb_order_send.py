"""
MICE F&B Order Send Tests
=========================
Task "MICE F&B order send yüzeyi" doğrulaması:
  - POST /api/mice/events/{id}/fnb-order/send (tenant scope + RBAC + idempotency)
  - GET  /api/mice/events/{id}/fnb-orders

Lifecycle hard-assert (BEO → kitchen order):
  - tentative event + F&B (type='fb') resource line → 200, status=sent, line snapshot
  - listed order persisted + readable
  - same Idempotency-Key replays the same order (no duplicate)
  - lead event → 409 status guard
  - tentative event with no F&B line → 422

Integration stilinde — gerçek backend'e HTTP ile bağlanır
(conftest.py:demo_auth_headers).
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set — integration tests require a running server",
)


def _event_payload(*, name: str, status: str, with_fb: bool) -> dict:
    today = date.today()
    payload = {
        "name": name,
        "client_name": "FNB Test Müşteri",
        "event_type": "meeting",
        "status": status,
        "expected_pax": 25,
        "start_date": today.isoformat(),
        "end_date": (today + timedelta(days=1)).isoformat(),
        "space_bookings": [],
        "resources": [],
        "agenda": [],
        "payment_schedule": [],
        "notes": "F&B order send test",
    }
    if with_fb:
        payload["resources"] = [
            {
                "name": "Açık Büfe Öğle Yemeği",
                "type": "fb",
                "quantity": 25,
                "unit": "pax",
                "unit_price": 950.0,
            },
            {
                "name": "AV Paketi",
                "type": "av",
                "quantity": 1,
                "unit": "unit",
                "unit_price": 4500.0,
            },
        ]
    return payload


def _create(headers: dict, payload: dict) -> dict:
    r = requests.post(f"{BASE_URL}/api/mice/events", json=payload, headers=headers)
    assert r.status_code == 200, f"create failed: {r.status_code} {r.text}"
    return r.json()


def _delete(headers: dict, event_id: str) -> None:
    requests.delete(f"{BASE_URL}/api/mice/events/{event_id}", headers=headers)


class TestMiceFnbOrderSend:

    def test_send_and_list_lifecycle(self, demo_auth_headers):
        created = _create(
            demo_auth_headers,
            _event_payload(name="FNB-Send-OK", status="tentative", with_fb=True),
        )
        event_id = created["id"]
        try:
            r = requests.post(
                f"{BASE_URL}/api/mice/events/{event_id}/fnb-order/send",
                json={"target": "kitchen", "note": "test order"},
                headers={**demo_auth_headers,
                         "Idempotency-Key": str(uuid.uuid4())},
            )
            assert r.status_code == 200, r.text
            order = r.json()
            assert order["id"]
            assert order["tenant_id"]
            assert order["event_id"] == event_id
            assert order["status"] == "sent"
            assert order["target"] == "kitchen"
            # Only the F&B (type='fb') line is snapshotted, not the AV line.
            assert len(order["lines"]) == 1
            assert order["lines"][0]["name"] == "Açık Büfe Öğle Yemeği"
            assert order["total"] == pytest.approx(25 * 950.0)

            lst = requests.get(
                f"{BASE_URL}/api/mice/events/{event_id}/fnb-orders",
                headers=demo_auth_headers,
            )
            assert lst.status_code == 200, lst.text
            orders = lst.json().get("orders", [])
            assert any(o["id"] == order["id"] for o in orders)
        finally:
            _delete(demo_auth_headers, event_id)

    def test_idempotency_same_key_replays(self, demo_auth_headers):
        created = _create(
            demo_auth_headers,
            _event_payload(name="FNB-Idem", status="tentative", with_fb=True),
        )
        event_id = created["id"]
        key = str(uuid.uuid4())
        try:
            first = requests.post(
                f"{BASE_URL}/api/mice/events/{event_id}/fnb-order/send",
                json={"target": "kitchen"},
                headers={**demo_auth_headers, "Idempotency-Key": key},
            )
            assert first.status_code == 200, first.text
            second = requests.post(
                f"{BASE_URL}/api/mice/events/{event_id}/fnb-order/send",
                json={"target": "kitchen"},
                headers={**demo_auth_headers, "Idempotency-Key": key},
            )
            assert second.status_code == 200, second.text
            assert first.json()["id"] == second.json()["id"]

            lst = requests.get(
                f"{BASE_URL}/api/mice/events/{event_id}/fnb-orders",
                headers=demo_auth_headers,
            ).json().get("orders", [])
            dup = [o for o in lst if o["id"] == first.json()["id"]]
            assert len(dup) == 1
        finally:
            _delete(demo_auth_headers, event_id)

    def test_lead_status_rejected_409(self, demo_auth_headers):
        created = _create(
            demo_auth_headers,
            _event_payload(name="FNB-Lead", status="lead", with_fb=True),
        )
        event_id = created["id"]
        try:
            r = requests.post(
                f"{BASE_URL}/api/mice/events/{event_id}/fnb-order/send",
                json={"target": "kitchen"},
                headers={**demo_auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
            assert r.status_code == 409, r.text
        finally:
            _delete(demo_auth_headers, event_id)

    def test_no_fb_line_rejected_422(self, demo_auth_headers):
        created = _create(
            demo_auth_headers,
            _event_payload(name="FNB-NoLine", status="tentative", with_fb=False),
        )
        event_id = created["id"]
        try:
            r = requests.post(
                f"{BASE_URL}/api/mice/events/{event_id}/fnb-order/send",
                json={"target": "kitchen"},
                headers={**demo_auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
            assert r.status_code == 422, r.text
        finally:
            _delete(demo_auth_headers, event_id)

    def test_cross_tenant_event_404(self, demo_auth_headers):
        bogus = f"cross-tenant-{uuid.uuid4()}"
        r = requests.post(
            f"{BASE_URL}/api/mice/events/{bogus}/fnb-order/send",
            json={"target": "kitchen"},
            headers={**demo_auth_headers, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 404, r.text
        lst = requests.get(
            f"{BASE_URL}/api/mice/events/{bogus}/fnb-orders",
            headers=demo_auth_headers,
        )
        assert lst.status_code == 404, lst.text


class TestMiceFnbOrderTransition:
    """Lifecycle: sent → acknowledged → completed (kitchen ack + close-out)."""

    def _send(self, headers: dict, event_id: str) -> dict:
        r = requests.post(
            f"{BASE_URL}/api/mice/events/{event_id}/fnb-order/send",
            json={"target": "kitchen"},
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 200, r.text
        return r.json()

    def test_full_lifecycle_sent_ack_completed(self, demo_auth_headers):
        created = _create(
            demo_auth_headers,
            _event_payload(name="FNB-Lifecycle", status="tentative",
                           with_fb=True),
        )
        event_id = created["id"]
        try:
            order = self._send(demo_auth_headers, event_id)
            order_id = order["id"]
            assert order["status"] == "sent"

            ack = requests.post(
                f"{BASE_URL}/api/mice/events/{event_id}"
                f"/fnb-orders/{order_id}/transition",
                json={"status": "acknowledged", "note": "mutfak aldı"},
                headers=demo_auth_headers,
            )
            assert ack.status_code == 200, ack.text
            ack_body = ack.json()
            assert ack_body["status"] == "acknowledged"
            assert ack_body["acknowledged_at"]
            assert ack_body["acknowledged_by"]

            done = requests.post(
                f"{BASE_URL}/api/mice/events/{event_id}"
                f"/fnb-orders/{order_id}/transition",
                json={"status": "completed"},
                headers=demo_auth_headers,
            )
            assert done.status_code == 200, done.text
            done_body = done.json()
            assert done_body["status"] == "completed"
            assert done_body["completed_at"]
            assert done_body["completed_by"]

            # List reflects the terminal status.
            lst = requests.get(
                f"{BASE_URL}/api/mice/events/{event_id}/fnb-orders",
                headers=demo_auth_headers,
            ).json().get("orders", [])
            match = [o for o in lst if o["id"] == order_id]
            assert len(match) == 1
            assert match[0]["status"] == "completed"
        finally:
            _delete(demo_auth_headers, event_id)

    def test_skip_ahead_rejected_409(self, demo_auth_headers):
        created = _create(
            demo_auth_headers,
            _event_payload(name="FNB-Skip", status="tentative", with_fb=True),
        )
        event_id = created["id"]
        try:
            order = self._send(demo_auth_headers, event_id)
            r = requests.post(
                f"{BASE_URL}/api/mice/events/{event_id}"
                f"/fnb-orders/{order['id']}/transition",
                json={"status": "completed"},  # skip acknowledged
                headers=demo_auth_headers,
            )
            assert r.status_code == 409, r.text
        finally:
            _delete(demo_auth_headers, event_id)

    def test_transition_out_of_terminal_rejected_409(self, demo_auth_headers):
        created = _create(
            demo_auth_headers,
            _event_payload(name="FNB-Terminal", status="tentative",
                           with_fb=True),
        )
        event_id = created["id"]
        try:
            order = self._send(demo_auth_headers, event_id)
            order_id = order["id"]
            for target in ("acknowledged", "completed"):
                ok = requests.post(
                    f"{BASE_URL}/api/mice/events/{event_id}"
                    f"/fnb-orders/{order_id}/transition",
                    json={"status": target},
                    headers=demo_auth_headers,
                )
                assert ok.status_code == 200, ok.text
            # Already completed → no further transition allowed.
            r = requests.post(
                f"{BASE_URL}/api/mice/events/{event_id}"
                f"/fnb-orders/{order_id}/transition",
                json={"status": "completed"},
                headers=demo_auth_headers,
            )
            assert r.status_code == 409, r.text
        finally:
            _delete(demo_auth_headers, event_id)

    def test_unknown_order_404(self, demo_auth_headers):
        created = _create(
            demo_auth_headers,
            _event_payload(name="FNB-NoOrder", status="tentative",
                           with_fb=True),
        )
        event_id = created["id"]
        try:
            r = requests.post(
                f"{BASE_URL}/api/mice/events/{event_id}"
                f"/fnb-orders/{uuid.uuid4()}/transition",
                json={"status": "acknowledged"},
                headers=demo_auth_headers,
            )
            assert r.status_code == 404, r.text
        finally:
            _delete(demo_auth_headers, event_id)

    def test_cross_tenant_event_404(self, demo_auth_headers):
        bogus = f"cross-tenant-{uuid.uuid4()}"
        r = requests.post(
            f"{BASE_URL}/api/mice/events/{bogus}"
            f"/fnb-orders/{uuid.uuid4()}/transition",
            json={"status": "acknowledged"},
            headers=demo_auth_headers,
        )
        assert r.status_code == 404, r.text
