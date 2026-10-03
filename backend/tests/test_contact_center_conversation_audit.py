from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.contact_center import router as contact_center


class _ConversationCollection:
    def __init__(self):
        self.calls = []

    async def update_one(self, query, update):
        self.calls.append((query, update))
        return SimpleNamespace(matched_count=1)


@pytest.fixture
def context(monkeypatch):
    conversations = _ConversationCollection()
    audit = AsyncMock()
    monkeypatch.setattr(contact_center, "db", SimpleNamespace(contact_center_conversations=conversations))
    monkeypatch.setattr(contact_center, "create_audit_log", audit)
    return conversations, audit, SimpleNamespace(tenant_id="tenant-a", id="user-a")


@pytest.mark.asyncio
async def test_assign_conversation_writes_pii_minimized_audit_entry(context):
    conversations, audit, user = context

    result = await contact_center.assign_conversation(
        "conversation-a",
        contact_center.AssignConversationPayload(agent_id="agent-b"),
        current_user=user,
        _mod=None,
        _perm=None,
    )

    assert result == {"success": True}
    assert conversations.calls[0][0] == {"id": "conversation-a", "tenant_id": "tenant-a"}
    audit.assert_awaited_once_with(
        "tenant-a",
        user,
        "contact_center_conversation_assigned",
        "contact_center_conversation",
        "conversation-a",
        {"assigned": True},
    )


@pytest.mark.asyncio
async def test_close_and_link_conversation_write_pii_minimized_audit_entries(context):
    _conversations, audit, user = context

    await contact_center.close_conversation("conversation-a", current_user=user, _mod=None, _perm=None)
    await contact_center.link_conversation(
        "conversation-a",
        contact_center.LinkConversationPayload(guest_id="guest-a"),
        current_user=user,
        _mod=None,
        _perm=None,
    )

    assert audit.await_args_list[0].args == (
        "tenant-a",
        user,
        "contact_center_conversation_closed",
        "contact_center_conversation",
        "conversation-a",
    )
    assert audit.await_args_list[1].args == (
        "tenant-a",
        user,
        "contact_center_conversation_linked",
        "contact_center_conversation",
        "conversation-a",
        {"guest_linked": True, "booking_linked": False},
    )
