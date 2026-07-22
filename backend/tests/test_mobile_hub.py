"""
Test: Mobile Hub aggregation API (Task #327 — Faz 0 Mobil Ortak Omurga)
=======================================================================

Pinned regression for `domains.pms.mobile_router.hub`:
  GET  /api/mobile/hub/feed            — unified notifications + alerts feed
  POST /api/mobile/hub/feed/mark-read  — route read-state to origin collection
  GET  /api/mobile/hub/my-tasks        — housekeeping + maintenance by person
  GET  /api/mobile/hub/today           — personal daily digest
  GET  /api/mobile/hub/approvals       — finance + HR approvals (permission-gated)

These endpoints introduce NO new data — they merge existing collections into
the person-centric views the common mobile shell renders. The test seeds rows
directly (mirroring the production writers), probes the live API, asserts the
merge/read-state/gating behaviour, then cleans up its own seed.
"""
import os
import uuid
from datetime import UTC, datetime

import httpx
import pytest

from core.database import db
from core.tenant_db import tenant_context

pytestmark = pytest.mark.asyncio

API = os.environ.get("VITE_BACKEND_URL", "http://localhost:8000").rstrip("/")
LOGIN = f"{API}/api/auth/login"
HUB = f"{API}/api/mobile/hub"


async def _login() -> tuple[dict, dict]:
    """Return (auth headers, user dict) for the demo admin tenant."""
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.post(LOGIN, json={"email": "demo@hotel.com", "password": "demo123"})
    if resp.status_code != 200:
        pytest.skip(f"Demo login unavailable ({resp.status_code})")
    body = resp.json()
    token = body.get("access_token") or body.get("token")
    return {"Authorization": f"Bearer {token}"}, body["user"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


@pytest.fixture
async def seeded():
    """Seed one notification, one alert, one HK task; yield ids; clean up."""
    _, user = await _login()
    tid = user["tenant_id"]
    name = user.get("name") or user.get("username")

    notif_id = f"hub-test-notif-{uuid.uuid4().hex[:10]}"
    alert_id = f"hub-test-alert-{uuid.uuid4().hex[:10]}"
    task_id = f"hub-test-task-{uuid.uuid4().hex[:10]}"

    with tenant_context(tid):
        with tenant_context(tid):
            with tenant_context(tid):
                await db.notifications.insert_one({
                "id": notif_id, "tenant_id": tid, "user_id": user["id"],
                "type": "info", "title": "Hub test notif", "message": "merge me",
                "priority": "normal", "read": False, "created_at": _now(),
                })
    with tenant_context(tid):
        with tenant_context(tid):
            with tenant_context(tid):
                await db.alerts.insert_one({
                "id": alert_id, "tenant_id": tid, "assigned_to": None,
                "alert_type": "system", "priority": "high", "title": "Hub test alert",
                "description": "merge me too", "status": "unread", "created_at": _now(),
                })
    with tenant_context(tid):
        with tenant_context(tid):
            with tenant_context(tid):
                await db.housekeeping_tasks.insert_one({
                "id": task_id, "tenant_id": tid, "room_id": "r-test",
                "room_number": "999", "task_type": "cleaning", "assigned_to": name,
                "priority": "urgent", "status": "pending", "created_at": _now(),
                })

    yield {"tenant_id": tid, "name": name, "notif_id": notif_id,
           "alert_id": alert_id, "task_id": task_id}

    with tenant_context(tenant_id):
        with tenant_context(tenant_id):
            with tenant_context(tenant_id):
                await db.notifications.delete_one({"id": notif_id})
    with tenant_context(tenant_id):
        with tenant_context(tenant_id):
            with tenant_context(tenant_id):
                await db.alerts.delete_one({"id": alert_id})
    with tenant_context(tenant_id):
        with tenant_context(tenant_id):
            with tenant_context(tenant_id):
                await db.housekeeping_tasks.delete_one({"id": task_id})


async def test_feed_merges_notifications_and_alerts(seeded):
    headers, _ = await _login()
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{HUB}/feed", headers=headers, params={"limit": 100})
    assert r.status_code == 200, r.text
    body = r.json()
    ids = {it["id"] for it in body["items"]}
    sources = {it["source"] for it in body["items"]}
    assert seeded["notif_id"] in ids
    assert seeded["alert_id"] in ids
    assert "notification" in sources and "alert" in sources
    assert body["unread_count"] >= 2


async def test_feed_mark_read_routes_by_source(seeded):
    headers, _ = await _login()
    async with httpx.AsyncClient(timeout=15) as c:
        rn = await c.post(f"{HUB}/feed/mark-read", headers=headers,
                          json={"source": "notification", "id": seeded["notif_id"]})
        ra = await c.post(f"{HUB}/feed/mark-read", headers=headers,
                          json={"source": "alert", "id": seeded["alert_id"]})
    assert rn.status_code == 200, rn.text
    assert ra.status_code == 200, ra.text
    with tenant_context(tenant_id):
        with tenant_context(tenant_id):
            with tenant_context(tenant_id):
                notif = await db.notifications.find_one({"id": seeded["notif_id"]}, {"_id": 0})
    with tenant_context(tenant_id):
        with tenant_context(tenant_id):
            with tenant_context(tenant_id):
                alert = await db.alerts.find_one({"id": seeded["alert_id"]}, {"_id": 0})
    assert notif["read"] is True
    assert alert["status"] == "read"


async def test_feed_mark_read_unknown_source_400():
    headers, _ = await _login()
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{HUB}/feed/mark-read", headers=headers,
                         json={"source": "bogus", "id": "x"})
    assert r.status_code == 400


async def test_my_tasks_returns_assigned_housekeeping(seeded):
    headers, _ = await _login()
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{HUB}/my-tasks", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    ids = {t["id"] for t in body["tasks"]}
    assert seeded["task_id"] in ids
    hk = next(t for t in body["tasks"] if t["id"] == seeded["task_id"])
    assert hk["kind"] == "housekeeping"
    assert hk["room_number"] == "999"


async def test_today_digest_shape(seeded):
    headers, _ = await _login()
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{HUB}/today", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("date", "open_tasks", "urgent_tasks", "unread_feed",
                "pending_approvals", "tasks_preview"):
        assert key in body
    assert body["open_tasks"] >= 1
    assert body["urgent_tasks"] >= 1


async def test_approvals_visible_for_admin():
    """Demo admin holds manage_approvals + view_hr → both categories present."""
    headers, _ = await _login()
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{HUB}/approvals", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    keys = {cat["key"] for cat in body["categories"]}
    assert "finance" in keys
    assert "hr" in keys
    assert isinstance(body["total"], int)


@pytest.fixture
async def seeded_pr():
    """Seed one submitted purchase request; yield ids; clean up.

    Demo admin is in PROCUREMENT_ROLES, so the procurement approval category
    must surface this PR with kind "pr_status".
    """
    _, user = await _login()
    tid = user["tenant_id"]
    pr_id = f"hub-test-pr-{uuid.uuid4().hex[:10]}"
    with tenant_context(tid):
        with tenant_context(tid):
            with tenant_context(tid):
                await db.proc_purchase_requests.insert_one({
                "id": pr_id, "tenant_id": tid, "pr_no": "PR-HUBTEST",
                "status": "submitted", "department": "kitchen",
                "requester": "hub tester", "lines": [], "lines_total": 1234.0,
                "created_at": _now(),
                })
    yield {"tenant_id": tid, "pr_id": pr_id}
    with tenant_context(tenant_id):
        with tenant_context(tenant_id):
            with tenant_context(tenant_id):
                await db.proc_purchase_requests.delete_one({"id": pr_id})


async def test_approvals_includes_submitted_procurement(seeded_pr):
    """A submitted PR surfaces in the procurement category as kind pr_status."""
    headers, _ = await _login()
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{HUB}/approvals", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    proc = next((cat for cat in body["categories"] if cat["key"] == "procurement"), None)
    assert proc is not None, "procurement category missing for procurement-capable user"
    item = next((it for it in proc["items"] if it["id"] == seeded_pr["pr_id"]), None)
    assert item is not None, "seeded submitted PR not surfaced in procurement approvals"
    assert item["kind"] == "pr_status"
    assert item["status"] == "submitted"


async def test_today_digest_counts_submitted_pr(seeded_pr):
    """Pending-approval count includes submitted PRs for procurement roles."""
    headers, _ = await _login()
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{HUB}/today", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["pending_approvals"] >= 1
