from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.pms.mobile_router import hub


class _Cursor:
    def sort(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def __aiter__(self):
        async def _rows():
            if False:
                yield None

        return _rows()


class _Notifications:
    def __init__(self):
        self.find_query = None
        self.count_queries = []
        self.update_query = None

    def find(self, query):
        self.find_query = query
        return _Cursor()

    async def count_documents(self, query):
        self.count_queries.append(query)
        return 0

    async def update_one(self, query, _patch):
        self.update_query = query
        return SimpleNamespace(matched_count=1)


class _Alerts:
    def find(self, _query):
        return _Cursor()

    async def count_documents(self, _query):
        return 0


@pytest.mark.asyncio
async def test_feed_scopes_personal_notifications_to_the_current_tenant(monkeypatch):
    notifications = _Notifications()
    user = SimpleNamespace(id="user-a", tenant_id="tenant-a", name="Ada", username="ada")
    monkeypatch.setattr(hub, "db", SimpleNamespace(notifications=notifications, alerts=_Alerts()))
    monkeypatch.setattr(hub, "get_current_user", AsyncMock(return_value=user))

    await hub.get_unified_feed(credentials=None)

    assert notifications.find_query == {
        "tenant_id": "tenant-a",
        "$or": [{"user_id": "user-a"}, {"user_id": None}],
    }
    assert notifications.count_queries == [{**notifications.find_query, "read": False}]


@pytest.mark.asyncio
async def test_marking_a_feed_notification_cannot_touch_another_users_row(monkeypatch):
    notifications = _Notifications()
    user = SimpleNamespace(id="user-a", tenant_id="tenant-a")
    monkeypatch.setattr(hub, "db", SimpleNamespace(notifications=notifications, alerts=_Alerts()))
    monkeypatch.setattr(hub, "get_current_user", AsyncMock(return_value=user))

    await hub.mark_feed_item_read(hub.FeedMarkReadRequest(source="notification", id="notice-1"), credentials=None)

    assert notifications.update_query == {
        "id": "notice-1",
        "tenant_id": "tenant-a",
        "$or": [{"user_id": "user-a"}, {"user_id": None}],
    }
