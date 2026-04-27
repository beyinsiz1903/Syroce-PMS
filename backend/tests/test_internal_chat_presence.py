"""
Tests: Internal Chat WebSocket presence (task #25)

Validates the in-memory presence tracker that powers the "Sadece
çevrimiçi" filter on the New Message compose dialog:

- A user is "online" while they have at least one active sid.
- Multi-tab / multi-device connections are sid-counted: closing one
  tab does not flip the user offline if another tab is still open.
- Tenant isolation: the same user_id under two different tenants is
  tracked independently and never leaks across the boundary.
- The HTTP endpoint scopes results to the caller's tenant via
  `current_user.tenant_id` and degrades gracefully (empty list, not
  500) if the in-memory map cannot be read.

The presence map is process-local so we use direct sync-state probes
(`get_online_user_ids` / `is_user_online`) rather than spinning up a
real Socket.IO client.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Same guard pattern as test_internal_message_edit.py — Motor's event-
# loop usage conflicts with the CI runner's loop policy.
if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
    pytest.skip("Motor event loop conflict in CI", allow_module_level=True)

import websocket_server as ws  # noqa: E402
from models.enums import UserRole  # noqa: E402
from models.schemas import User  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_presence():
    """Reset the in-memory presence map before AND after every test so
    state from one test never bleeds into another. Belt-and-braces:
    some failure modes leave the dict mid-mutation."""
    ws._user_presence.clear()
    yield
    ws._user_presence.clear()


# ─────────────────────────────────────────────────────────────────────
# Unit tests for the presence helpers
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_single_connect_marks_user_online():
    """Baseline: one connect → user appears in the online list."""
    await ws._record_user_connect("tenant-A", "user-1")

    online = ws.get_online_user_ids("tenant-A")
    assert online == ["user-1"]
    assert ws.is_user_online("tenant-A", "user-1") is True


@pytest.mark.asyncio
async def test_multi_tab_keeps_user_online_until_last_tab_closes():
    """Two tabs (sids) for the same user. Closing one must NOT flip
    them offline — they are still reachable via the other tab. Only
    the second disconnect ends presence."""
    await ws._record_user_connect("tenant-A", "user-1")  # tab #1
    await ws._record_user_connect("tenant-A", "user-1")  # tab #2
    assert ws.is_user_online("tenant-A", "user-1") is True

    await ws._record_user_disconnect("tenant-A", "user-1")  # close tab #1
    assert ws.is_user_online("tenant-A", "user-1") is True, (
        "user must still be online while another tab is open"
    )

    await ws._record_user_disconnect("tenant-A", "user-1")  # close tab #2
    assert ws.is_user_online("tenant-A", "user-1") is False
    assert ws.get_online_user_ids("tenant-A") == []


@pytest.mark.asyncio
async def test_double_disconnect_does_not_underflow():
    """A duplicate disconnect (e.g. socket teardown ran twice) must not
    drive the counter negative or corrupt the dict."""
    await ws._record_user_connect("tenant-A", "user-1")
    await ws._record_user_disconnect("tenant-A", "user-1")
    # Extra disconnect — should be a silent no-op.
    await ws._record_user_disconnect("tenant-A", "user-1")
    await ws._record_user_disconnect("tenant-A", "user-1")

    # Reconnect must restore presence cleanly.
    await ws._record_user_connect("tenant-A", "user-1")
    assert ws.is_user_online("tenant-A", "user-1") is True


@pytest.mark.asyncio
async def test_multiple_users_in_same_tenant_listed():
    """Three users in the same tenant should all surface in the list,
    in any order."""
    await ws._record_user_connect("tenant-A", "user-1")
    await ws._record_user_connect("tenant-A", "user-2")
    await ws._record_user_connect("tenant-A", "user-3")

    online = set(ws.get_online_user_ids("tenant-A"))
    assert online == {"user-1", "user-2", "user-3"}


@pytest.mark.asyncio
async def test_tenant_isolation_same_user_id():
    """Same user_id string under two different tenants must be tracked
    independently — disconnecting from tenant-A must NOT pull the
    user offline for tenant-B."""
    await ws._record_user_connect("tenant-A", "shared-id")
    await ws._record_user_connect("tenant-B", "shared-id")

    assert ws.is_user_online("tenant-A", "shared-id") is True
    assert ws.is_user_online("tenant-B", "shared-id") is True

    await ws._record_user_disconnect("tenant-A", "shared-id")
    assert ws.is_user_online("tenant-A", "shared-id") is False, (
        "tenant-A should be offline after its sole disconnect"
    )
    assert ws.is_user_online("tenant-B", "shared-id") is True, (
        "tenant-B must NOT be affected by tenant-A's disconnect"
    )

    # Tenant-A's bucket should be pruned entirely (no orphan keys).
    assert "tenant-A" not in ws._user_presence


@pytest.mark.asyncio
async def test_helpers_handle_falsy_inputs():
    """Empty tenant_id / user_id must be a silent no-op — we never
    want presence bookkeeping to crash a real WS connection."""
    await ws._record_user_connect("", "user-1")
    await ws._record_user_connect("tenant-A", "")
    await ws._record_user_disconnect("", "user-1")
    await ws._record_user_disconnect("tenant-A", "")

    assert ws.get_online_user_ids("") == []
    assert ws.is_user_online("", "user-1") is False
    assert ws.is_user_online("tenant-A", "") is False
    # And the dict must be untouched.
    assert dict(ws._user_presence) == {}


@pytest.mark.asyncio
async def test_unknown_tenant_returns_empty_list():
    """Reading a tenant that has never connected anyone must return
    [] (NOT raise, NOT auto-create the bucket)."""
    assert ws.get_online_user_ids("ghost-tenant") == []
    assert "ghost-tenant" not in ws._user_presence


# ─────────────────────────────────────────────────────────────────────
# HTTP endpoint tests
# ─────────────────────────────────────────────────────────────────────

def _make_user(tenant_id: str = "tenant-A", user_id: str = "user-self") -> User:
    """Lightweight authenticated User for endpoint tests."""
    return User(
        id=user_id,
        tenant_id=tenant_id,
        email="self@example.com",
        username="self",
        name="Self",
        role=UserRole.FRONT_DESK,
    )


@pytest.mark.asyncio
async def test_endpoint_returns_only_callers_tenant():
    """Endpoint must filter by `current_user.tenant_id` and never
    expose presence from other tenants."""
    from domains.guest.messaging import router as messaging_router

    await ws._record_user_connect("tenant-A", "u-A1")
    await ws._record_user_connect("tenant-A", "u-A2")
    await ws._record_user_connect("tenant-B", "u-B1")

    caller = _make_user(tenant_id="tenant-A")
    result = await messaging_router.get_internal_presence_online(current_user=caller)

    assert set(result["user_ids"]) == {"u-A1", "u-A2"}
    assert result["count"] == 2
    assert "u-B1" not in result["user_ids"], (
        "endpoint must NOT leak other tenants' presence"
    )


@pytest.mark.asyncio
async def test_endpoint_includes_caller_in_their_own_tenant():
    """If the caller themselves is connected, their id is returned —
    the frontend already filters self out before rendering, so the
    endpoint stays simple and predictable."""
    from domains.guest.messaging import router as messaging_router

    await ws._record_user_connect("tenant-A", "user-self")
    await ws._record_user_connect("tenant-A", "user-other")

    caller = _make_user(tenant_id="tenant-A", user_id="user-self")
    result = await messaging_router.get_internal_presence_online(current_user=caller)

    assert "user-self" in result["user_ids"]
    assert "user-other" in result["user_ids"]


@pytest.mark.asyncio
async def test_endpoint_returns_empty_list_when_nobody_online():
    """Quiet hours: nobody connected → [] and count=0, not a 404."""
    from domains.guest.messaging import router as messaging_router

    caller = _make_user(tenant_id="tenant-A")
    result = await messaging_router.get_internal_presence_online(current_user=caller)
    assert result == {"user_ids": [], "count": 0}


@pytest.mark.asyncio
async def test_endpoint_degrades_to_empty_when_helper_raises():
    """Presence is a UX hint, not a security boundary. If the
    in-memory helper somehow raises, the endpoint must return an
    empty list rather than 500 — otherwise the compose dialog
    loses its primary user picker the moment something glitches."""
    from domains.guest.messaging import router as messaging_router

    caller = _make_user(tenant_id="tenant-A")
    # Patch on the websocket_server module since the endpoint imports
    # the helper inside the function body.
    with patch.object(ws, "get_online_user_ids", side_effect=RuntimeError("boom")):
        result = await messaging_router.get_internal_presence_online(current_user=caller)

    assert result == {"user_ids": [], "count": 0}
