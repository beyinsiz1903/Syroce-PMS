"""
channel_event_dedup atomic claim — concurrency regression tests (#649)
======================================================================

`unified_repository.claim_provider_event` closes the read-then-insert race in
the HotelRunner webhook path. OTA channels deliver at-least-once, so two
concurrent identical redeliveries can both pass the `check_provider_event_recorded`
read-guard and double-insert. The atomic `insert_one` into `channel_event_dedup`
(keyed by sha256(tenant:provider:provider_event_id)) lets exactly ONE concurrent
caller win.

These tests pin:
  1. Under N concurrent claims of the same (tenant, provider, provider_event_id),
     exactly one returns True; the rest return False (no-op duplicates).
  2. A post-insert claim is a no-op duplicate (False).
  3. Distinct provider_event_ids each win independently.
  4. Fail-open: an empty provider_event_id returns True and writes nothing.

Test isolation: each test uses a unique tenant_id and cleans its own ledger rows.
Talks to the same MongoDB the backend uses (conftest.py). asyncio_mode="auto".
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid

from core.database import db
from domains.channel_manager import unified_repository as repo
from domains.channel_manager.data_model import COLL_CHANNEL_EVENT_DEDUP


def _key(tenant_id: str, provider: str, peid: str) -> str:
    return hashlib.sha256(f"{tenant_id}:{provider}:{peid}".encode()).hexdigest()


async def _cleanup(tenant_id: str) -> None:
    await db[COLL_CHANNEL_EVENT_DEDUP].delete_many({"tenant_id": tenant_id})


async def test_concurrent_claim_single_winner():
    tenant_id = f"t-dedup-{uuid.uuid4().hex[:12]}"
    provider = "hotelrunner"
    peid = f"evt-{uuid.uuid4().hex[:12]}"
    try:
        results = await asyncio.gather(
            *[repo.claim_provider_event(tenant_id, provider, peid) for _ in range(12)]
        )
        assert sum(1 for r in results if r is True) == 1, results
        assert sum(1 for r in results if r is False) == 11, results

        stored = await db[COLL_CHANNEL_EVENT_DEDUP].find_one(
            {"_id": _key(tenant_id, provider, peid)},
        )
        assert stored is not None
        assert stored["tenant_id"] == tenant_id
        assert stored["provider"] == provider
        assert stored["provider_event_id"] == peid
        assert "expires_at" in stored

        # A subsequent (post-insert) claim is a no-op duplicate.
        assert await repo.claim_provider_event(tenant_id, provider, peid) is False
    finally:
        await _cleanup(tenant_id)


async def test_distinct_events_each_win():
    tenant_id = f"t-dedup-{uuid.uuid4().hex[:12]}"
    provider = "hotelrunner"
    try:
        peids = [f"evt-{uuid.uuid4().hex[:8]}" for _ in range(5)]
        results = await asyncio.gather(
            *[repo.claim_provider_event(tenant_id, provider, p) for p in peids]
        )
        assert all(r is True for r in results), results
    finally:
        await _cleanup(tenant_id)


async def test_empty_provider_event_id_fail_open():
    tenant_id = f"t-dedup-{uuid.uuid4().hex[:12]}"
    try:
        assert await repo.claim_provider_event(tenant_id, "hotelrunner", "") is True
        cnt = await db[COLL_CHANNEL_EVENT_DEDUP].count_documents({"tenant_id": tenant_id})
        assert cnt == 0
    finally:
        await _cleanup(tenant_id)
