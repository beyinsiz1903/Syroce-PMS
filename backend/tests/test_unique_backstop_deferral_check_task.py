"""Task #242 — Alert ops by email when a duplicate-prevention safeguard is off.

Direct-call tests for `_unique_backstop_deferral_check_async` (the async body of
the `celery_tasks.unique_backstop_deferral_check_task` beat job). The job touches
the lazy index builders to self-heal, reads `index_backstops.list_status()`,
tracks per-backstop deferral duration in Mongo, and dispatches a high-severity
alert (which the shared dispatcher emails to ops) once a backstop stays deferred
past the grace window.

Skips automatically when MongoDB is not reachable (conftest fixture binds Motor
to the session event loop).
"""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest


pytestmark = pytest.mark.asyncio


_COLL = "unique_backstop_alert_state"


async def _reset_state() -> None:
    from core.database import db
    await db[_COLL].delete_many({})


def _patch_ensure_and_status(status):
    """Patch the lazy builders to no-op and force a controlled status list."""
    return (
        patch("routers.mice._ensure_indexes", new=AsyncMock(return_value=None)),
        patch(
            "domains.revenue.rms_router.sales._ensure_contract_indexes",
            new=AsyncMock(return_value=None),
        ),
        patch("shared_kernel.index_backstops.list_status", return_value=status),
    )


async def _run():
    from celery_tasks import _unique_backstop_deferral_check_async
    return await _unique_backstop_deferral_check_async()


_DEFERRED = {
    "name": "uniq_mice_acc_client_taxno",
    "collection": "mice_accounts",
    "fields": ["tenant_id", "tax_no"],
    "status": "deferred",
}
_ACTIVE = {
    "name": "uniq_mice_acc_client_taxno",
    "collection": "mice_accounts",
    "fields": ["tenant_id", "tax_no"],
    "status": "active",
}


async def test_all_active_no_alert():
    """No noise while all backstops are active."""
    await _reset_state()
    p_mice, p_sales, p_status = _patch_ensure_and_status([_ACTIVE])
    try:
        with p_mice, p_sales, p_status, patch(
            "domains.channel_manager.monitoring.alert_dispatch.dispatch_alert",
            new=AsyncMock(return_value={"dashboard": True}),
        ) as mock_dispatch:
            r = await _run()
            assert r["alert_sent"] is False
            assert r["reason"] == "all_active"
            assert mock_dispatch.await_count == 0
    finally:
        await _reset_state()


async def test_deferred_within_grace_stamps_no_alert():
    """First sighting of a deferred backstop stamps first_deferred_at and does
    NOT alert until the grace window elapses."""
    from core.database import db

    await _reset_state()
    p_mice, p_sales, p_status = _patch_ensure_and_status([_DEFERRED])
    try:
        with p_mice, p_sales, p_status, patch(
            "domains.channel_manager.monitoring.alert_dispatch.dispatch_alert",
            new=AsyncMock(return_value={"dashboard": True}),
        ) as mock_dispatch:
            r = await _run()
            assert r["alert_sent"] is False
            assert r["reason"] == "within_grace_or_suppressed"
            assert mock_dispatch.await_count == 0

        st = await db[_COLL].find_one({"backstop": _DEFERRED["name"]}, {"_id": 0})
        assert st is not None
        assert "first_deferred_at" in st
        assert st["collection"] == "mice_accounts"
    finally:
        await _reset_state()


async def test_deferred_past_grace_dispatches_high_alert():
    """A backstop deferred longer than the grace window dispatches a
    high-severity alert that names the backstop and collection."""
    from core.database import db

    await _reset_state()
    # Pre-stamp an old first_deferred_at so the grace window is already exceeded.
    old = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
    await db[_COLL].update_one(
        {"backstop": _DEFERRED["name"]},
        {"$set": {
            "backstop": _DEFERRED["name"],
            "collection": "mice_accounts",
            "fields": _DEFERRED["fields"],
            "first_deferred_at": old,
        }},
        upsert=True,
    )

    captured = {}

    async def _fake_dispatch(payload, tenant_id="system"):
        captured["payload"] = payload
        captured["tenant_id"] = tenant_id
        return {"dashboard": True, "email": True}

    p_mice, p_sales, p_status = _patch_ensure_and_status([_DEFERRED])
    try:
        with p_mice, p_sales, p_status, patch(
            "domains.channel_manager.monitoring.alert_dispatch.dispatch_alert",
            new=AsyncMock(side_effect=_fake_dispatch),
        ):
            r = await _run()
            assert r["alert_sent"] is True
            assert _DEFERRED["name"] in r["alerted"]

        payload = captured["payload"]
        assert payload["severity"] == "high"
        assert payload["alert_type"] == "unique_index_backstop_deferred"
        # Names the backstop + collection + remediation.
        assert _DEFERRED["name"] in payload["message"]
        assert "mice_accounts" in payload["message"]
        assert "self-heal" in payload["message"].lower()
        assert payload["runbook_hint"]
        ctx_names = [
            b["backstop"] for b in payload["context"]["deferred_backstops"]
        ]
        assert _DEFERRED["name"] in ctx_names

        # last_alert_at recorded for suppression.
        st = await db[_COLL].find_one({"backstop": _DEFERRED["name"]}, {"_id": 0})
        assert st.get("last_alert_at") is not None
    finally:
        await _reset_state()


async def test_recent_alert_is_suppressed():
    """A ripe deferral re-alerted within the suppression window does NOT page
    again."""
    from core.database import db

    await _reset_state()
    old = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
    recent_alert = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    await db[_COLL].update_one(
        {"backstop": _DEFERRED["name"]},
        {"$set": {
            "backstop": _DEFERRED["name"],
            "collection": "mice_accounts",
            "fields": _DEFERRED["fields"],
            "first_deferred_at": old,
            "last_alert_at": recent_alert,
        }},
        upsert=True,
    )
    p_mice, p_sales, p_status = _patch_ensure_and_status([_DEFERRED])
    try:
        with p_mice, p_sales, p_status, patch(
            "domains.channel_manager.monitoring.alert_dispatch.dispatch_alert",
            new=AsyncMock(return_value={"dashboard": True, "email": True}),
        ) as mock_dispatch:
            r = await _run()
            assert r["alert_sent"] is False
            assert r["reason"] == "within_grace_or_suppressed"
            assert mock_dispatch.await_count == 0
    finally:
        await _reset_state()


async def test_self_heal_clears_state():
    """When a previously-deferred backstop becomes active again, its persisted
    state is cleared so a future deferral starts a fresh grace window."""
    from core.database import db

    await _reset_state()
    old = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
    await db[_COLL].update_one(
        {"backstop": _ACTIVE["name"]},
        {"$set": {
            "backstop": _ACTIVE["name"],
            "collection": "mice_accounts",
            "fields": _ACTIVE["fields"],
            "first_deferred_at": old,
        }},
        upsert=True,
    )
    p_mice, p_sales, p_status = _patch_ensure_and_status([_ACTIVE])
    try:
        with p_mice, p_sales, p_status, patch(
            "domains.channel_manager.monitoring.alert_dispatch.dispatch_alert",
            new=AsyncMock(return_value={"dashboard": True}),
        ) as mock_dispatch:
            r = await _run()
            assert r["alert_sent"] is False
            assert r["reason"] == "all_active"
            assert _ACTIVE["name"] in r["cleared"]
            assert mock_dispatch.await_count == 0

        st = await db[_COLL].find_one({"backstop": _ACTIVE["name"]}, {"_id": 0})
        assert st is None
    finally:
        await _reset_state()


async def test_dispatch_failure_does_not_advance_suppression():
    """If delivery fails, last_alert_at must NOT be stamped so the next check
    retries the alert."""
    from core.database import db

    await _reset_state()
    old = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
    await db[_COLL].update_one(
        {"backstop": _DEFERRED["name"]},
        {"$set": {
            "backstop": _DEFERRED["name"],
            "collection": "mice_accounts",
            "fields": _DEFERRED["fields"],
            "first_deferred_at": old,
        }},
        upsert=True,
    )
    p_mice, p_sales, p_status = _patch_ensure_and_status([_DEFERRED])
    try:
        with p_mice, p_sales, p_status, patch(
            "domains.channel_manager.monitoring.alert_dispatch.dispatch_alert",
            new=AsyncMock(return_value={
                "dashboard": False, "slack": False, "email": False}),
        ):
            r = await _run()
            assert r["alert_sent"] is False
            assert r["reason"] == "dispatch_failed"

        st = await db[_COLL].find_one({"backstop": _DEFERRED["name"]}, {"_id": 0})
        assert st.get("last_alert_at") is None
    finally:
        await _reset_state()
