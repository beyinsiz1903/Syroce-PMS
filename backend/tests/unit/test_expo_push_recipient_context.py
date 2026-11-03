from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_push_deep_links_are_bound_to_each_real_recipient_not_caller_supplied_ids(monkeypatch):
    from services import expo_push

    monkeypatch.setattr(expo_push, "_push_disabled", lambda: False)
    monkeypatch.setattr(expo_push, "_collect_expo_tokens", AsyncMock(return_value=[
        {"push_token": "ExponentPushToken[local-a]", "device_id": "device-a", "user_id": "staff-a"},
        {"push_token": "ExponentPushToken[local-b]", "device_id": "device-b", "user_id": "staff-b"},
    ]))
    post = AsyncMock(return_value=[{"status": "ok"}, {"status": "ok"}])
    monkeypatch.setattr(expo_push, "_post_expo_batch", post)
    monkeypatch.setattr(expo_push, "db", SimpleNamespace(expo_push_logs=SimpleNamespace(insert_one=AsyncMock())))
    original = {"type": "housekeeping_task", "tenant_id": "untrusted-tenant", "user_id": "untrusted-user"}

    result = await expo_push.send_expo_push("hotel-a", title="Synthetic task", body="Local test only", data=original)

    assert result["sent"] == 2
    messages = post.await_args.args[0]
    assert [m["data"]["user_id"] for m in messages] == ["staff-a", "staff-b"]
    assert all(m["data"]["tenant_id"] == "hotel-a" for m in messages)
    assert [m["data"]["device_id"] for m in messages] == ["device-a", "device-b"]
    assert original["tenant_id"] == "untrusted-tenant"
