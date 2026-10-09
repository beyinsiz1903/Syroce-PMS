from types import SimpleNamespace

import pytest

from routers import cross_property as module


class UpdateCollection:
    def __init__(self, *, document=None, modified=0, matched=1):
        self.document = document
        self.modified = modified
        self.matched = matched
        self.updates = []

    async def find_one(self, query, _projection=None):
        self.find_query = query
        return dict(self.document) if self.document else None

    async def update_many(self, query, update):
        self.updates.append((query, update))
        return SimpleNamespace(modified_count=self.modified)

    async def update_one(self, query, update):
        self.updates.append((query, update))
        return SimpleNamespace(modified_count=self.modified, matched_count=self.matched)


class AsyncRows:
    def __init__(self, rows):
        self.rows = list(rows)

    def __aiter__(self):
        self.iterator = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return next(self.iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    def limit(self, value):
        self.rows = self.rows[:value]
        return self

    async def to_list(self, value):
        return self.rows[:value]


class CandidateGuests:
    def __init__(self):
        self.find_calls = 0

    def aggregate(self, pipeline):
        field = next(key for key in pipeline[0]["$match"] if key.startswith("_hash_"))
        return AsyncRows([{"_id": f"duplicate-{field}"}])

    def find(self, _query, _projection):
        self.find_calls += 1
        if self.find_calls == 1:
            return AsyncRows([
                {"id": "g1", "tenant_id": "a", "email": "same@example.com"},
                {"id": "g2", "tenant_id": "b", "email": "same@example.com"},
            ])
        return AsyncRows([{"id": "g1", "tenant_id": "a", "email": "same@example.com"}])


@pytest.mark.asyncio
async def test_merge_undo_restores_only_tagged_records(monkeypatch):
    operation = {
        "id": "merge-1",
        "tenant_id": "tenant-a",
        "primary_tenant_id": "tenant-a",
        "duplicate_tenant_id": "tenant-b",
        "primary_guest_id": "primary",
        "duplicate_guest_id": "duplicate",
        "duplicate_aliases": ["duplicate", "legacy-duplicate"],
        "override_fields": [],
        "status": "completed",
    }
    merges = UpdateCollection(document=operation, modified=1)
    bookings = UpdateCollection(modified=2)
    folios = UpdateCollection(modified=1)
    guests = UpdateCollection(modified=1, matched=1)
    monkeypatch.setattr(module, "db", SimpleNamespace(guest_profile_merges=merges, bookings=bookings, folios=folios, guests=guests))
    monkeypatch.setattr(module, "require_roles", lambda *_args, **_kwargs: None)

    async def chain_ids(_user):
        return ["tenant-a", "tenant-b"]

    audits = []

    async def audit(*args, **kwargs):
        audits.append((args, kwargs))

    monkeypatch.setattr(module, "_chain_tenant_ids", chain_ids)
    monkeypatch.setattr(module, "log_audit_event", audit)
    user = SimpleNamespace(tenant_id="tenant-a", id="user-1", role="admin")

    result = await module.undo_guest_profile_merge("merge-1", current_user=user, _perm=None)

    assert result == {"ok": True, "merge_id": "merge-1", "bookings_restored": 2, "folios_restored": 1, "guest_restored": True}
    booking_query, booking_update = bookings.updates[0]
    assert booking_query["guest_id"] == "primary"
    assert booking_query["merged_from"] == {"$in": ["duplicate", "legacy-duplicate"]}
    assert booking_update["$set"]["guest_id"] == "duplicate"
    assert "$unset" in booking_update
    assert merges.updates[-1][1]["$set"]["status"] == "undone"
    assert audits[0][1]["action"] == "cross_property.guest_merge_undone"


@pytest.mark.asyncio
async def test_merge_undo_is_idempotency_guarded(monkeypatch):
    operation = {
        "id": "merge-1",
        "tenant_id": "tenant-a",
        "primary_tenant_id": "tenant-a",
        "duplicate_tenant_id": "tenant-a",
        "status": "undone",
    }
    monkeypatch.setattr(module, "db", SimpleNamespace(guest_profile_merges=UpdateCollection(document=operation)))
    monkeypatch.setattr(module, "require_roles", lambda *_args, **_kwargs: None)

    async def chain_ids(_user):
        return ["tenant-a"]

    monkeypatch.setattr(module, "_chain_tenant_ids", chain_ids)
    user = SimpleNamespace(tenant_id="tenant-a", id="user-1", role="admin")

    with pytest.raises(module.HTTPException) as exc:
        await module.undo_guest_profile_merge("merge-1", current_user=user, _perm=None)

    assert exc.value.status_code == 409


def test_restore_snapshot_keeps_only_requested_fields_and_crypto_companions():
    snapshot = module._merge_restore_snapshot(
        {"name": "Ada", "email": "ciphertext", "_hash_email": "hash", "tenant_id": "secret-scope"},
        {"email"},
    )

    assert snapshot == {"email": "ciphertext", "_hash_email": "hash"}


@pytest.mark.asyncio
async def test_duplicate_pool_uses_hash_candidates_and_deduplicates_legacy_overlap(monkeypatch):
    guests = CandidateGuests()
    monkeypatch.setattr(module, "db", SimpleNamespace(guests=guests))

    rows, metadata = await module._duplicate_candidate_pool(["a", "b"])

    assert [row["id"] for row in rows] == ["g1", "g2"]
    assert metadata["strategy"] == "blind_index_candidates_with_legacy_fallback"
    assert metadata["repeated_email_hashes"] == 1
    assert metadata["repeated_phone_hashes"] == 1
    assert metadata["legacy_scan_truncated"] is False
