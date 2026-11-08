"""Destructive-source regressions on UUID-scoped local Mongo fixtures only."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pymongo.errors import OperationFailure

from routers import mice
from tests.test_mice_mongo_acceptance import USER, wired  # noqa: F401
from tests.test_report_ledger_mongo_acceptance import ledger_db  # noqa: F401


async def seed_event(db, **extra):
    existing = set(await db.list_collection_names())
    for name in ("mice_events", "mice_locks", "audit_logs", "audit_chain_state", "folio_charges", "folio_postings", "payments", "gl_journal_entries"):
        if name not in existing:
            await db.create_collection(name)
    await db.mice_locks.create_index([("tenant_id", 1), ("kind", 1), ("resource_id", 1)], unique=True)
    event = {"id": "event", "tenant_id": "A", "name": "Synthetic event", "status": "lead", **extra}
    await db.mice_events.insert_one(event)
    return event


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "unknown-legacy-state"])
async def test_terminal_or_unknown_source_cannot_be_deleted(wired, status):  # noqa: F811
    await seed_event(wired, status=status)
    with pytest.raises(HTTPException) as error:
        await mice.delete_event("event", USER)
    assert error.value.status_code == 409
    assert await wired.mice_events.count_documents({"tenant_id": "A", "id": "event"}) == 1
    mice.release_quota.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("history", [
    {"last_kitchen_dispatch_at": "2026-11-08T07:00:00Z"},
    {"folio_charge_id": "legacy-charge"},
    {"finance_pending": {"payment_id": "pending"}},
])
async def test_header_history_preserves_source(wired, history):  # noqa: F811
    await seed_event(wired, **history)
    with pytest.raises(HTTPException) as error:
        await mice.delete_event("event", USER)
    assert error.value.status_code == 409
    assert await wired.mice_events.count_documents({"id": "event"}) == 1
    mice.release_quota.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_transaction_support_fails_closed(wired, monkeypatch):  # noqa: F811
    await seed_event(wired)
    monkeypatch.setattr(mice, "with_resource_locks", AsyncMock(side_effect=OperationFailure("Transaction numbers are only allowed on a replica set", code=20)))
    with pytest.raises(HTTPException) as error:
        await mice.delete_event("event", USER)
    assert error.value.status_code == 503
    assert await wired.mice_events.count_documents({"id": "event"}) == 1
    mice.release_quota.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["lead", "tentative", "definite", "confirmed", "cancelled"])
async def test_clean_draft_deletion_is_chained_and_quota_released_only_after_commit(wired, monkeypatch, status):  # noqa: F811
    from core import audit, audit_chain

    await seed_event(wired, status=status, client_request_id="request-key")
    monkeypatch.setattr(mice, "log_audit_event", audit.log_audit_event)
    monkeypatch.setattr(audit_chain, "_system_db", lambda: wired)
    assert await mice.delete_event("event", USER) == {"ok": True}
    assert await wired.mice_events.count_documents({"tenant_id": "A", "id": "event"}) == 0
    entry = await wired.audit_logs.find_one({"entity_id": "event", "action": "delete"})
    assert entry["record_hash"] and entry["seq"] == 1
    assert entry["before_value"]["status"] == status and entry["after_value"] is None
    if status in mice.ACTIVE_QUOTA_STATUSES:
        mice.release_quota.assert_awaited_once_with("A", "mice", "concurrent_events", "request-key")
    else:
        mice.release_quota.assert_not_awaited()


@pytest.mark.asyncio
async def test_foreign_ledger_references_do_not_block_own_clean_draft(wired):  # noqa: F811
    await seed_event(wired)
    await wired.folio_charges.insert_one({"tenant_id": "B", "source_mice_event_id": "event"})
    await wired.payments.insert_one({"tenant_id": "B", "mice_event_id": "event"})
    await mice.delete_event("event", USER)
    assert await wired.folio_charges.count_documents({"tenant_id": "B"}) == 1
    assert await wired.payments.count_documents({"tenant_id": "B"}) == 1


@pytest.mark.asyncio
async def test_missing_tenant_or_role_cannot_delete_source(wired):  # noqa: F811
    await seed_event(wired)
    for actor, code in [(SimpleNamespace(**{**vars(USER), "tenant_id": "B"}), 404),
                        (SimpleNamespace(**{**vars(USER), "role": "housekeeping", "roles": ["housekeeping"]}), 403)]:
        with pytest.raises(HTTPException) as error:
            await mice.delete_event("event", actor)
        assert error.value.status_code == code
    assert await wired.mice_events.count_documents({"id": "event"}) == 1


@pytest.mark.asyncio
async def test_concurrent_completion_and_delete_cannot_erase_completed_source(wired):  # noqa: F811
    await seed_event(wired, status="confirmed", space_bookings=[], resources=[])
    # Prime lock rows outside the race; exercise transaction/event CAS behavior.
    await wired.mice_locks.insert_many([{"tenant_id": "A", "kind": kind, "resource_id": "event"} for kind in ("event", "finance")])
    result = await asyncio.gather(mice.delete_event("event", USER), mice.change_status("event", mice.StatusUpdate(status="completed"), USER), return_exceptions=True)
    assert sum(isinstance(value, dict) for value in result) == 1, result
    assert all(isinstance(value, dict) or isinstance(value, HTTPException) and value.status_code in {404, 409} for value in result), result
    event = await wired.mice_events.find_one({"id": "event"})
    if isinstance(result[1], dict):
        assert event["status"] == "completed"
    else:
        assert event is None


@pytest.mark.asyncio
@pytest.mark.parametrize("collection,reference", [
    ("folio_charges", {"source_mice_event_id": "event", "voided": True}),
    ("folio_charges", {"mice_event_id": "event"}),
    ("folio_postings", {"source": "mice_module", "reference": "event"}),
    ("payments", {"mice_event_id": "event", "status": "refunded"}),
    ("gl_journal_entries", {"source": "mice_settlement", "source_ref": "event", "reversal_status": "reversed"}),
])
async def test_actual_ledger_reference_preserves_stale_unlinked_header(wired, collection, reference):  # noqa: F811
    await seed_event(wired)
    await wired[collection].insert_one({"tenant_id": "A", "id": "history", **reference})
    with pytest.raises(HTTPException) as error:
        await mice.delete_event("event", USER)
    assert error.value.status_code == 409
    assert await wired.mice_events.count_documents({"tenant_id": "A", "id": "event"}) == 1
    assert await wired[collection].count_documents({"tenant_id": "A", "id": "history"}) == 1


@pytest.mark.asyncio
async def test_deletion_audit_failure_rolls_back_source_and_does_not_release_quota(wired, monkeypatch):  # noqa: F811
    await seed_event(wired, status="confirmed")
    monkeypatch.setattr(mice, "log_audit_event", AsyncMock(side_effect=RuntimeError("audit unavailable")))
    with pytest.raises(RuntimeError, match="audit unavailable"):
        await mice.delete_event("event", USER)
    assert await wired.mice_events.count_documents({"tenant_id": "A", "id": "event"}) == 1
    mice.release_quota.assert_not_awaited()
