from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.integrations import nilvera_gl_automation as automation


def _match(doc: dict, query: dict) -> bool:
    for key, value in query.items():
        if isinstance(value, dict) and "$in" in value:
            if doc.get(key) not in value["$in"]:
                return False
        elif doc.get(key) != value:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, *_args):
        return self

    def limit(self, value):
        self.docs = self.docs[:value]
        return self

    async def to_list(self, length=100):
        return [dict(row) for row in self.docs[:length]]


class _Collection:
    def __init__(self):
        self.docs: list[dict] = []

    async def find_one(self, query, projection=None):
        for row in self.docs:
            if _match(row, query):
                return dict(row)
        return None

    def find(self, query, projection=None):
        return _Cursor(row for row in self.docs if _match(row, query))

    async def update_one(self, query, update, upsert=False):
        row = next((item for item in self.docs if _match(item, query)), None)
        if row is None and upsert:
            row = dict(query)
            row.update(update.get("$setOnInsert", {}))
            self.docs.append(row)
        if row is None:
            return SimpleNamespace(matched_count=0)
        row.update(update.get("$set", {}))
        for key, amount in update.get("$inc", {}).items():
            row[key] = row.get(key, 0) + amount
        for key in update.get("$unset", {}):
            row.pop(key, None)
        return SimpleNamespace(matched_count=1)

    async def find_one_and_update(self, query, update, return_document=None):
        row = next((item for item in self.docs if _match(item, query)), None)
        if row is None:
            return None
        row.update(update.get("$set", {}))
        for key, amount in update.get("$inc", {}).items():
            row[key] = row.get(key, 0) + amount
        for key in update.get("$unset", {}):
            row.pop(key, None)
        return dict(row)


class _DB:
    def __init__(self):
        self.gl_nilvera_settings = _Collection()
        self.gl_nilvera_queue = _Collection()


@pytest.fixture
def fake_db(monkeypatch):
    db = _DB()
    monkeypatch.setattr(automation, "get_db_for_tenant", lambda _tenant: db)
    return db


@pytest.mark.asyncio
async def test_review_mode_creates_pending_item_without_posting(fake_db, monkeypatch):
    post = AsyncMock()
    monkeypatch.setattr(automation, "post_incoming_invoice_to_gl", post)
    item = await automation.enqueue_nilvera_gl_candidate(
        "tenant-1",
        "incoming",
        "invoice-1",
        source_status="synced",
    )
    assert item["status"] == "pending"
    assert item["mode"] == "review"
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_automatic_mode_posts_with_persisted_mapping(fake_db, monkeypatch):
    fake_db.gl_nilvera_settings.docs.append({
        "tenant_id": "tenant-1",
        **automation.DEFAULT_NILVERA_GL_SETTINGS,
        "incoming_mode": "automatic",
        "incoming_purchase_account_code": "740",
    })
    post = AsyncMock(return_value={"id": "je-1", "entry_no": "YEV-1"})
    monkeypatch.setattr(automation, "post_incoming_invoice_to_gl", post)
    item = await automation.enqueue_nilvera_gl_candidate(
        "tenant-1",
        "incoming",
        "invoice-1",
        source_status="synced",
    )
    assert item["status"] == "posted"
    assert item["journal_entry_id"] == "je-1"
    assert post.await_args.kwargs["purchase_account_code"] == "740"


@pytest.mark.asyncio
async def test_failed_automatic_post_stays_in_visible_blocked_queue(fake_db, monkeypatch):
    fake_db.gl_nilvera_settings.docs.append({
        "tenant_id": "tenant-1",
        **automation.DEFAULT_NILVERA_GL_SETTINGS,
        "outgoing_mode": "automatic",
    })
    monkeypatch.setattr(
        automation,
        "post_outgoing_invoice_to_gl",
        AsyncMock(side_effect=automation.InvoiceGLBridgeError("unsupported tax")),
    )
    item = await automation.enqueue_nilvera_gl_candidate(
        "tenant-1",
        "outgoing",
        "invoice-2",
        source_status="accepted",
    )
    assert item["status"] == "blocked"
    assert item["error_code"] == "InvoiceGLBridgeError"
    rows = await automation.list_nilvera_gl_queue("tenant-1", status="blocked")
    assert [row["invoice_id"] for row in rows] == ["invoice-2"]
