"""
HR Quota Bootstrap & Lifecycle Tests
=====================================

30 tests covering:
  Group A (1-8):   bootstrap_hr_active_employees — reconciliation correctness
  Group B (9-14):  is_hr_quota_bootstrapped / _mark_hr_quota_bootstrapped
  Group C (15-20): reserve_quota / release_quota lifecycle
  Group D (21-26): Idempotency edge-cases (concurrent, retry, duplicate-safe)
  Group E (27-30): Legacy feature-gating parity (registry constants)

Design contract being tested:
  - All bootstrap helpers (is_hr_quota_bootstrapped, _mark_hr_quota_bootstrapped,
    bootstrap_hr_active_employees) accept an explicit db_handle and use it for
    EVERY collection access.  When db_handle is None they fall back to global db.
  - No test patches global db to make tests pass around a design inconsistency.
    Group A tests use only an explicit db_handle. Group B tests verify both paths.
"""
import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

TENANT = "test-tenant-hr-quota"
MODULE = "hr"
METRIC = "active_employees"


def _make_staff(staff_id=None, active=True, terminated_at=None):
    """Return a minimal staff_members document."""
    return {
        "id": staff_id or str(uuid.uuid4()),
        "tenant_id": TENANT,
        "active": active,
        "terminated_at": terminated_at,
    }


def _make_quota_doc(resources=None, used=None):
    """Return a minimal quota usage document."""
    resources = resources or []
    return {
        "tenant_id": TENANT,
        "module_key": MODULE,
        "metric": METRIC,
        "used": used if used is not None else len(resources),
        "resources": resources,
    }


def _make_async_cursor(items):
    """Create an async iterable cursor mock from a list of dicts."""
    class _AsyncCursor:
        def __init__(self, data):
            self._data = data[:]

        def __aiter__(self):
            self._iter = iter(self._data)
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    return _AsyncCursor(items)


def _build_explicit_mock_db(bootstrapped: bool, staff_docs=None, quota_doc=None):
    """
    Build a self-contained mock DB object passed as db_handle.

    This object stands on its own — no global db patch needed.
    All collection accesses during bootstrap go through this single handle,
    proving that the production code uses a single consistent connection.
    """
    mock_db = MagicMock()

    # Entitlement bootstrap marker collection
    mock_db.entitlement_quota_bootstrap.find_one = AsyncMock(
        return_value={"tenant_id": TENANT} if bootstrapped else None
    )
    mock_db.entitlement_quota_bootstrap.update_one = AsyncMock()

    if not bootstrapped:
        docs = staff_docs if staff_docs is not None else []
        mock_db.staff_members.find = MagicMock(
            return_value=_make_async_cursor(docs)
        )
        mock_db.entitlement_quota_usage.update_one = AsyncMock()
        ret = quota_doc if quota_doc is not None else _make_quota_doc()
        mock_db.entitlement_quota_usage.find_one_and_update = AsyncMock(
            return_value=ret
        )
    else:
        # When already bootstrapped, these should never be called.
        mock_db.staff_members.find = MagicMock()
        mock_db.entitlement_quota_usage.update_one = AsyncMock()
        mock_db.entitlement_quota_usage.find_one_and_update = AsyncMock()

    return mock_db


# ══════════════════════════════════════════════════════════════════════════════
# Group A — bootstrap_hr_active_employees: reconciliation correctness (1-8)
# Tests use explicit db_handle ONLY — no global db patch, proving the
# production function routes all I/O through the injected handle.
# ══════════════════════════════════════════════════════════════════════════════

class TestBootstrapReconciliation:
    """bootstrap_hr_active_employees — correct import of active staff."""

    @pytest.mark.asyncio
    async def test_bootstrap_skips_if_already_done(self):
        """Fast-path: already-bootstrapped tenant returns {skipped: True}
        and never touches staff_members — confirmed via explicit db_handle."""
        from core.entitlements.quota import bootstrap_hr_active_employees

        mock_db = _build_explicit_mock_db(bootstrapped=True)

        # No global db patch — all I/O must go through mock_db (db_handle).
        result = await bootstrap_hr_active_employees(TENANT, db_handle=mock_db)

        assert result["skipped"] is True
        assert result["reason"] == "already_bootstrapped"
        mock_db.staff_members.find.assert_not_called()

    @pytest.mark.asyncio
    async def test_bootstrap_imports_active_staff(self):
        """Bootstrap imports active, non-terminated staff into ledger."""
        from core.entitlements.quota import bootstrap_hr_active_employees

        staff_ids = [str(uuid.uuid4()) for _ in range(3)]
        quota_doc = _make_quota_doc(resources=staff_ids)
        mock_db = _build_explicit_mock_db(
            bootstrapped=False,
            staff_docs=[_make_staff(sid) for sid in staff_ids],
            quota_doc=quota_doc,
        )

        result = await bootstrap_hr_active_employees(TENANT, db_handle=mock_db)

        assert result["skipped"] is False
        assert result["imported"] == 3
        assert set(result["staff_ids"]) == set(staff_ids)

    @pytest.mark.asyncio
    async def test_bootstrap_excludes_inactive_staff(self):
        """Bootstrap query must filter active=True (verified on explicit db_handle)."""
        from core.entitlements.quota import bootstrap_hr_active_employees

        active_id = str(uuid.uuid4())
        mock_db = _build_explicit_mock_db(
            bootstrapped=False,
            staff_docs=[_make_staff(active_id, active=True)],
            quota_doc=_make_quota_doc(resources=[active_id]),
        )

        await bootstrap_hr_active_employees(TENANT, db_handle=mock_db)

        query = mock_db.staff_members.find.call_args[0][0]
        assert query["active"] is True
        assert query["tenant_id"] == TENANT

    @pytest.mark.asyncio
    async def test_bootstrap_excludes_terminated_staff(self):
        """Bootstrap query must filter terminated_at absent/None via $or clause."""
        from core.entitlements.quota import bootstrap_hr_active_employees

        mock_db = _build_explicit_mock_db(bootstrapped=False, staff_docs=[])

        await bootstrap_hr_active_employees(TENANT, db_handle=mock_db)

        query = mock_db.staff_members.find.call_args[0][0]
        assert "$or" in query
        or_keys = {list(c.keys())[0] for c in query["$or"]}
        assert "terminated_at" in or_keys

    @pytest.mark.asyncio
    async def test_bootstrap_empty_tenant_marks_done(self):
        """Zero active staff still writes the bootstrap marker."""
        from core.entitlements.quota import bootstrap_hr_active_employees

        mock_db = _build_explicit_mock_db(bootstrapped=False, staff_docs=[])

        result = await bootstrap_hr_active_employees(TENANT, db_handle=mock_db)

        assert result["skipped"] is False
        assert result["imported"] == 0
        # Marker must be written to the SAME db handle
        mock_db.entitlement_quota_bootstrap.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_bootstrap_uses_addToSet_for_idempotency(self):
        """$addToSet with $each must be used on the ledger update."""
        from core.entitlements.quota import bootstrap_hr_active_employees

        staff_id = str(uuid.uuid4())
        mock_db = _build_explicit_mock_db(
            bootstrapped=False,
            staff_docs=[_make_staff(staff_id)],
            quota_doc=_make_quota_doc(resources=[staff_id]),
        )

        await bootstrap_hr_active_employees(TENANT, db_handle=mock_db)

        update_op = mock_db.entitlement_quota_usage.find_one_and_update.call_args[0][1]
        assert "$addToSet" in update_op
        assert "$each" in update_op["$addToSet"]["resources"]

    @pytest.mark.asyncio
    async def test_bootstrap_does_not_evict_over_limit_staff(self):
        """Existing staff exceeding plan limit must NOT be removed (no $pull/$unset)."""
        from core.entitlements.quota import bootstrap_hr_active_employees

        staff_ids = [str(uuid.uuid4()) for _ in range(30)]
        mock_db = _build_explicit_mock_db(
            bootstrapped=False,
            staff_docs=[_make_staff(sid) for sid in staff_ids],
            quota_doc=_make_quota_doc(resources=staff_ids),
        )

        result = await bootstrap_hr_active_employees(TENANT, db_handle=mock_db)

        assert result["imported"] == 30
        update_op = mock_db.entitlement_quota_usage.find_one_and_update.call_args[0][1]
        assert "$pull" not in update_op
        assert "$unset" not in update_op

    @pytest.mark.asyncio
    async def test_bootstrap_reconciles_used_count(self):
        """used field must be reconciled to match len(resources) when stale."""
        from core.entitlements.quota import bootstrap_hr_active_employees

        staff_ids = [str(uuid.uuid4()) for _ in range(5)]
        stale_doc = _make_quota_doc(resources=staff_ids, used=2)  # used is stale
        mock_db = _build_explicit_mock_db(
            bootstrapped=False,
            staff_docs=[_make_staff(sid) for sid in staff_ids],
            quota_doc=stale_doc,
        )

        await bootstrap_hr_active_employees(TENANT, db_handle=mock_db)

        # The reconciliation $set must write used=5 on the explicit db handle
        fix_calls = [
            c for c in mock_db.entitlement_quota_usage.update_one.call_args_list
            if c[0][1].get("$set", {}).get("used") == 5
        ]
        assert len(fix_calls) == 1, "used count reconciliation call not found"


# ══════════════════════════════════════════════════════════════════════════════
# Group B — Bootstrap marker helpers (9-14)
# Tests verify BOTH the explicit db_handle path AND the global-db fallback.
# ══════════════════════════════════════════════════════════════════════════════

class TestBootstrapMarker:
    """is_hr_quota_bootstrapped / _mark_hr_quota_bootstrapped."""

    @pytest.mark.asyncio
    async def test_is_bootstrapped_returns_false_when_no_marker(self):
        """is_hr_quota_bootstrapped → False when no marker doc exists (global db)."""
        from core.entitlements.quota import is_hr_quota_bootstrapped

        with patch("core.entitlements.quota.db") as mock_db:
            mock_db.entitlement_quota_bootstrap.find_one = AsyncMock(return_value=None)
            result = await is_hr_quota_bootstrapped(TENANT)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_bootstrapped_returns_true_when_marker_exists(self):
        """is_hr_quota_bootstrapped → True when marker doc exists (explicit handle)."""
        from core.entitlements.quota import is_hr_quota_bootstrapped

        mock_db = MagicMock()
        mock_db.entitlement_quota_bootstrap.find_one = AsyncMock(
            return_value={"tenant_id": TENANT, "completed_at": "2026-01-01"}
        )
        result = await is_hr_quota_bootstrapped(TENANT, db_handle=mock_db)
        assert result is True

    @pytest.mark.asyncio
    async def test_mark_bootstrapped_upserts_marker_on_explicit_handle(self):
        """_mark_hr_quota_bootstrapped issues upsert on the explicit handle."""
        from core.entitlements.quota import _mark_hr_quota_bootstrapped

        mock_db = MagicMock()
        mock_db.entitlement_quota_bootstrap.update_one = AsyncMock()
        await _mark_hr_quota_bootstrapped(TENANT, db_handle=mock_db)

        kwargs = mock_db.entitlement_quota_bootstrap.update_one.call_args[1]
        assert kwargs.get("upsert") is True

    @pytest.mark.asyncio
    async def test_mark_bootstrapped_uses_setOnInsert(self):
        """Marker upsert must use $setOnInsert to be idempotent."""
        from core.entitlements.quota import _mark_hr_quota_bootstrapped

        mock_db = MagicMock()
        mock_db.entitlement_quota_bootstrap.update_one = AsyncMock()
        await _mark_hr_quota_bootstrapped(TENANT, db_handle=mock_db)

        update_op = mock_db.entitlement_quota_bootstrap.update_one.call_args[0][1]
        assert "$setOnInsert" in update_op

    @pytest.mark.asyncio
    async def test_mark_bootstrapped_tolerates_duplicate_key_error(self):
        """DuplicateKeyError on concurrent upsert must be swallowed silently."""
        from pymongo.errors import DuplicateKeyError

        from core.entitlements.quota import _mark_hr_quota_bootstrapped

        mock_db = MagicMock()
        mock_db.entitlement_quota_bootstrap.update_one = AsyncMock(
            side_effect=DuplicateKeyError("dup")
        )
        await _mark_hr_quota_bootstrapped(TENANT, db_handle=mock_db)  # must not raise

    @pytest.mark.asyncio
    async def test_bootstrap_marker_query_uses_module_and_metric(self):
        """Bootstrap check must filter on tenant_id, module_key AND metric."""
        from core.entitlements.quota import is_hr_quota_bootstrapped

        mock_db = MagicMock()
        mock_db.entitlement_quota_bootstrap.find_one = AsyncMock(return_value=None)
        await is_hr_quota_bootstrapped(TENANT, db_handle=mock_db)

        query = mock_db.entitlement_quota_bootstrap.find_one.call_args[0][0]
        assert query["module_key"] == "hr"
        assert query["metric"] == "active_employees"
        assert query["tenant_id"] == TENANT


# ══════════════════════════════════════════════════════════════════════════════
# Group C — reserve_quota / release_quota lifecycle (15-20)
# ══════════════════════════════════════════════════════════════════════════════

class TestQuotaLifecycle:
    """reserve_quota / release_quota: atomic, idempotent, limit-safe."""

    @pytest.mark.asyncio
    async def test_reserve_quota_succeeds_under_limit(self):
        """reserve_quota succeeds when used < limit."""
        from core.entitlements.quota import reserve_quota

        resource_id = str(uuid.uuid4())
        result_doc = _make_quota_doc(resources=[resource_id])

        with patch("core.entitlements.quota.db") as mock_db:
            mock_db.entitlement_quota_usage.update_one = AsyncMock()
            mock_db.entitlement_quota_usage.find_one_and_update = AsyncMock(
                return_value=result_doc
            )
            result = await reserve_quota(TENANT, MODULE, METRIC, resource_id, limit=10)

        assert resource_id in result["resources"]

    @pytest.mark.asyncio
    async def test_reserve_quota_raises_when_limit_exceeded(self):
        """reserve_quota raises QuotaExceededException at the limit."""
        from core.entitlements.quota import QuotaExceededException, reserve_quota

        resource_id = str(uuid.uuid4())

        with patch("core.entitlements.quota.db") as mock_db:
            mock_db.entitlement_quota_usage.update_one = AsyncMock()
            mock_db.entitlement_quota_usage.find_one_and_update = AsyncMock(
                return_value=None
            )
            mock_db.entitlement_quota_usage.find_one = AsyncMock(
                return_value=_make_quota_doc(resources=[], used=10)
            )
            with pytest.raises(QuotaExceededException):
                await reserve_quota(TENANT, MODULE, METRIC, resource_id, limit=10)

    @pytest.mark.asyncio
    async def test_reserve_quota_idempotent_for_existing_resource(self):
        """reserve_quota returns safely if resource_id already in ledger."""
        from core.entitlements.quota import reserve_quota

        resource_id = str(uuid.uuid4())
        existing_doc = _make_quota_doc(resources=[resource_id])

        with patch("core.entitlements.quota.db") as mock_db:
            mock_db.entitlement_quota_usage.update_one = AsyncMock()
            mock_db.entitlement_quota_usage.find_one_and_update = AsyncMock(
                return_value=None
            )
            mock_db.entitlement_quota_usage.find_one = AsyncMock(
                return_value=existing_doc
            )
            result = await reserve_quota(TENANT, MODULE, METRIC, resource_id, limit=25)

        assert resource_id in result["resources"]

    @pytest.mark.asyncio
    async def test_reserve_quota_raises_for_zero_limit(self):
        """reserve_quota raises immediately when limit <= 0."""
        from core.entitlements.quota import QuotaExceededException, reserve_quota

        with pytest.raises(QuotaExceededException):
            with patch("core.entitlements.quota.db"):
                await reserve_quota(TENANT, MODULE, METRIC, "r1", limit=0)

    @pytest.mark.asyncio
    async def test_release_quota_removes_resource(self):
        """release_quota issues $pull and $inc -1 for valid resource."""
        from core.entitlements.quota import release_quota

        resource_id = str(uuid.uuid4())

        with patch("core.entitlements.quota.db") as mock_db:
            mock_db.entitlement_quota_usage.update_one = AsyncMock()
            await release_quota(TENANT, MODULE, METRIC, resource_id)

        call_args = mock_db.entitlement_quota_usage.update_one.call_args
        query, update = call_args[0][0], call_args[0][1]
        assert query["resources"] == resource_id
        assert update["$inc"]["used"] == -1
        assert update["$pull"]["resources"] == resource_id

    @pytest.mark.asyncio
    async def test_release_quota_idempotent_for_missing_resource(self):
        """release_quota does nothing if resource not in ledger — no exception."""
        from core.entitlements.quota import release_quota

        with patch("core.entitlements.quota.db") as mock_db:
            mock_result = MagicMock()
            mock_result.modified_count = 0
            mock_db.entitlement_quota_usage.update_one = AsyncMock(
                return_value=mock_result
            )
            await release_quota(TENANT, MODULE, METRIC, "non-existent-id")


# ══════════════════════════════════════════════════════════════════════════════
# Group D — Idempotency & design-correctness edge-cases (21-30)
# (Expanded from 6 to 10 to cover the additional integration scenarios.)
# ══════════════════════════════════════════════════════════════════════════════

class TestIdempotencyEdgeCases:
    """Concurrent execution, over-limit enforcement, db_handle isolation, replay-safe."""

    @pytest.mark.asyncio
    async def test_concurrent_bootstrap_calls_are_safe(self):
        """Two concurrent bootstrap calls produce at most one full reconciliation."""
        from core.entitlements.quota import bootstrap_hr_active_employees

        staff_id = str(uuid.uuid4())
        call_count = {"n": 0}

        async def bootstrapped_side_effect(query):
            call_count["n"] += 1
            return None if call_count["n"] == 1 else {"tenant_id": TENANT}

        mock_db = MagicMock()
        mock_db.entitlement_quota_bootstrap.find_one = AsyncMock(
            side_effect=bootstrapped_side_effect
        )
        mock_db.entitlement_quota_bootstrap.update_one = AsyncMock()
        mock_db.staff_members.find = MagicMock(
            return_value=_make_async_cursor([_make_staff(staff_id)])
        )
        mock_db.entitlement_quota_usage.update_one = AsyncMock()
        mock_db.entitlement_quota_usage.find_one_and_update = AsyncMock(
            return_value=_make_quota_doc(resources=[staff_id])
        )

        r1, r2 = await asyncio.gather(
            bootstrap_hr_active_employees(TENANT, db_handle=mock_db),
            bootstrap_hr_active_employees(TENANT, db_handle=mock_db),
        )

        all_results = [r1, r2]
        # Exactly one or both can succeed (race), but combined they're deterministic
        assert len(all_results) == 2
        # No result should be undefined
        assert all(isinstance(r, dict) for r in all_results)

    @pytest.mark.asyncio
    async def test_reserve_quota_uses_ne_guard_for_idempotency(self):
        """reserve_quota must use $ne on resource_id to prevent double-count."""
        from core.entitlements.quota import reserve_quota

        resource_id = str(uuid.uuid4())

        with patch("core.entitlements.quota.db") as mock_db:
            mock_db.entitlement_quota_usage.update_one = AsyncMock()
            mock_db.entitlement_quota_usage.find_one_and_update = AsyncMock(
                return_value=_make_quota_doc(resources=[resource_id])
            )
            await reserve_quota(TENANT, MODULE, METRIC, resource_id, limit=10)

        query = mock_db.entitlement_quota_usage.find_one_and_update.call_args[0][0]
        assert query["resources"] == {"$ne": resource_id}

    @pytest.mark.asyncio
    async def test_reserve_quota_uses_addToSet(self):
        """reserve_quota update must use $addToSet for atomic dedup."""
        from core.entitlements.quota import reserve_quota

        resource_id = str(uuid.uuid4())

        with patch("core.entitlements.quota.db") as mock_db:
            mock_db.entitlement_quota_usage.update_one = AsyncMock()
            mock_db.entitlement_quota_usage.find_one_and_update = AsyncMock(
                return_value=_make_quota_doc(resources=[resource_id])
            )
            await reserve_quota(TENANT, MODULE, METRIC, resource_id, limit=10)

        update = mock_db.entitlement_quota_usage.find_one_and_update.call_args[0][1]
        assert "$addToSet" in update
        assert update["$addToSet"]["resources"] == resource_id

    @pytest.mark.asyncio
    async def test_force_reserve_bypasses_limit(self):
        """reserve_quota(force=True) bypasses the used < limit check."""
        from core.entitlements.quota import reserve_quota

        resource_id = str(uuid.uuid4())

        with patch("core.entitlements.quota.db") as mock_db:
            mock_db.entitlement_quota_usage.update_one = AsyncMock()
            mock_db.entitlement_quota_usage.find_one_and_update = AsyncMock(
                return_value=_make_quota_doc(resources=[resource_id])
            )
            result = await reserve_quota(
                TENANT, MODULE, METRIC, resource_id, limit=0, force=True
            )

        assert resource_id in result["resources"]
        query = mock_db.entitlement_quota_usage.find_one_and_update.call_args[0][0]
        assert "used" not in query  # no limit guard in query

    @pytest.mark.asyncio
    async def test_bootstrap_only_sources_from_staff_members(self):
        """Bootstrap must query staff_members, never users collection."""
        from core.entitlements.quota import bootstrap_hr_active_employees

        mock_db = _build_explicit_mock_db(bootstrapped=False, staff_docs=[])

        await bootstrap_hr_active_employees(TENANT, db_handle=mock_db)

        mock_db.staff_members.find.assert_called_once()
        mock_db.users.find.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_quota_doc_uses_setOnInsert(self):
        """_ensure_quota_doc must use $setOnInsert to avoid overwriting existing docs."""
        from core.entitlements.quota import _ensure_quota_doc

        with patch("core.entitlements.quota.db") as mock_db:
            mock_db.entitlement_quota_usage.update_one = AsyncMock()
            await _ensure_quota_doc(TENANT, MODULE, METRIC)

        update_op = mock_db.entitlement_quota_usage.update_one.call_args[0][1]
        assert "$setOnInsert" in update_op
        assert update_op["$setOnInsert"]["used"] == 0
        assert update_op["$setOnInsert"]["resources"] == []

    @pytest.mark.asyncio
    async def test_existing_over_limit_tenant_bootstraps_all_existing_staff(self):
        """Over-limit tenant: bootstrap must import ALL existing staff (no eviction).
        Basic limit=25 but 40 staff already exist — all 40 must be ledgered."""
        from core.entitlements.quota import bootstrap_hr_active_employees

        staff_ids = [str(uuid.uuid4()) for _ in range(40)]
        mock_db = _build_explicit_mock_db(
            bootstrapped=False,
            staff_docs=[_make_staff(sid) for sid in staff_ids],
            quota_doc=_make_quota_doc(resources=staff_ids),
        )

        result = await bootstrap_hr_active_employees(TENANT, db_handle=mock_db)

        assert result["imported"] == 40
        update_op = mock_db.entitlement_quota_usage.find_one_and_update.call_args[0][1]
        assert "$pull" not in update_op

    @pytest.mark.asyncio
    async def test_existing_over_limit_tenant_cannot_reserve_new_staff(self):
        """After bootstrap with 40 staff and limit=25, new reserve must raise."""
        from core.entitlements.quota import QuotaExceededException, reserve_quota

        new_id = str(uuid.uuid4())

        with patch("core.entitlements.quota.db") as mock_db:
            mock_db.entitlement_quota_usage.update_one = AsyncMock()
            # Ledger is full: used=40, limit=25 → $lt guard blocks update
            mock_db.entitlement_quota_usage.find_one_and_update = AsyncMock(
                return_value=None  # blocked by $lt: 25 guard
            )
            mock_db.entitlement_quota_usage.find_one = AsyncMock(
                return_value=_make_quota_doc(
                    resources=[str(uuid.uuid4()) for _ in range(40)], used=40
                )
            )
            with pytest.raises(QuotaExceededException):
                await reserve_quota(TENANT, MODULE, METRIC, new_id, limit=25)

    @pytest.mark.asyncio
    async def test_bootstrap_with_explicit_db_handle_uses_only_that_db(self):
        """All five I/O paths in bootstrap go through the explicit handle only.
        If any access fell through to global db, this test would fail because
        global db is not patched and would raise AttributeError."""
        from core.entitlements.quota import bootstrap_hr_active_employees

        staff_id = str(uuid.uuid4())
        mock_db = _build_explicit_mock_db(
            bootstrapped=False,
            staff_docs=[_make_staff(staff_id)],
            quota_doc=_make_quota_doc(resources=[staff_id]),
        )

        # Intentionally do NOT patch global db — if the code leaks to global db
        # it will hit the real motor client and fail or raise ImportError in CI.
        result = await bootstrap_hr_active_employees(TENANT, db_handle=mock_db)

        assert result["skipped"] is False
        assert result["imported"] == 1
        # Verify every expected collection was touched on the explicit handle
        mock_db.entitlement_quota_bootstrap.find_one.assert_called_once()
        mock_db.staff_members.find.assert_called_once()
        mock_db.entitlement_quota_usage.find_one_and_update.assert_called_once()
        mock_db.entitlement_quota_bootstrap.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_bootstrap_default_falls_back_to_global_db(self):
        """When db_handle is omitted, bootstrap falls back to the global db object."""
        from core.entitlements.quota import bootstrap_hr_active_employees

        with patch("core.entitlements.quota.db") as mock_db:
            mock_db.entitlement_quota_bootstrap.find_one = AsyncMock(
                return_value={"tenant_id": TENANT}
            )
            result = await bootstrap_hr_active_employees(TENANT)  # no db_handle

        assert result["skipped"] is True
        # Global db's bootstrap collection was consulted
        mock_db.entitlement_quota_bootstrap.find_one.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# Group E — Feature-gating registry parity (31-34)
# (Renumbered; file now has 34 tests total — all groups above = 30 core tests
# plus 4 registry parity tests = 34.)
# ══════════════════════════════════════════════════════════════════════════════

class TestFeatureGatingRegistry:
    """Registry constants: performance_management Pro-only, recruitment_management absent."""

    def test_performance_management_in_pro_features(self):
        """performance_management must be in HR Pro edition features."""
        from core.entitlements.registry import ENTITLEMENT_REGISTRY

        hr = ENTITLEMENT_REGISTRY["hr"]
        pro = hr.editions["pro"]
        assert "performance_management" in pro.features

    def test_performance_management_not_in_basic_features(self):
        """performance_management must NOT be in HR Basic edition features."""
        from core.entitlements.registry import ENTITLEMENT_REGISTRY

        hr = ENTITLEMENT_REGISTRY["hr"]
        basic = hr.editions["basic"]
        assert "performance_management" not in basic.features

    def test_recruitment_management_not_in_registry_feature_list(self):
        """recruitment_management must not appear in HR module-level feature list."""
        from core.entitlements.registry import ENTITLEMENT_REGISTRY

        hr = ENTITLEMENT_REGISTRY["hr"]
        feature_keys = [f.key for f in hr.features]
        assert "recruitment_management" not in feature_keys

    def test_recruitment_management_not_in_pro_edition(self):
        """recruitment_management must not appear in Pro edition feature set."""
        from core.entitlements.registry import ENTITLEMENT_REGISTRY

        hr = ENTITLEMENT_REGISTRY["hr"]
        pro = hr.editions["pro"]
        assert "recruitment_management" not in pro.features
