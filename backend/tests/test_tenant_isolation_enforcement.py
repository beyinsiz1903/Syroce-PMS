"""
TI-003: Tenant Isolation Full Enforcement — Test Suite
======================================================
Tests all 3 layers of tenant isolation:
  Layer 1: DB Proxy (auto-injection)
  Layer 2: Runtime Guard (cross-tenant blocking)
  Layer 3: Static Audit (raw db usage detection)
"""
import asyncio
import os
import sys
import subprocess

import pytest

# Ensure backend is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_tenant_context():
    """Ensure tenant context is cleared before/after each test."""
    from core.tenant_db import clear_tenant_context
    clear_tenant_context()
    yield
    clear_tenant_context()


# ── Layer 1: DB Proxy Tests ──────────────────────────────────

class TestTenantAwareDBProxy:
    """Tests for the transparent TenantAwareDBProxy."""

    def test_proxy_type(self):
        from core.database import db
        from core.tenant_db import TenantAwareDBProxy
        assert isinstance(db, TenantAwareDBProxy)

    def test_raw_db_is_motor(self):
        from core.database import _raw_db
        assert type(_raw_db).__name__ == "LoopAwareDatabaseProxy"

    def test_no_context_returns_raw_collection(self):
        """Without tenant context, proxy returns SchemaOnlyCollection (strict mode)."""
        from core.database import db
        import core.tenant_db as tdb
        original = tdb.STRICT_TENANT_MODE
        try:
            tdb.STRICT_TENANT_MODE = True
            coll = db.bookings
            assert type(coll).__name__ == "SchemaOnlyCollection"
        finally:
            tdb.STRICT_TENANT_MODE = original

    def test_with_context_returns_scoped_collection(self):
        """With tenant context, proxy returns TenantScopedCollection."""
        from core.database import db
        from core.tenant_db import set_tenant_context, TenantScopedCollection
        set_tenant_context("tenant_A")
        coll = db.bookings
        assert isinstance(coll, TenantScopedCollection)
        assert coll._tenant_id == "tenant_A"

    def test_global_collection_always_raw(self):
        """Global collections return raw Motor collection regardless of context."""
        from core.database import db
        from core.tenant_db import set_tenant_context, TenantScopedCollection
        set_tenant_context("tenant_A")
        coll = db.tenants
        assert not isinstance(coll, TenantScopedCollection)

    def test_db_passthrough_methods(self):
        """Database methods (name, client) pass through correctly."""
        from core.database import db
        assert db.name is not None
        assert db.client is not None


# ── Layer 1: TenantScopedCollection Tests ─────────────────────

class TestTenantScopedCollection:
    """Tests for auto-injection and validation in TenantScopedCollection."""

    def _make_coll(self, tenant_id="T1"):
        from core.tenant_db import TenantScopedCollection
        from unittest.mock import MagicMock
        mock = MagicMock()
        return TenantScopedCollection(mock, tenant_id, "test_coll"), mock

    def test_inject_filter_empty(self):
        """Empty filter → tenant_id injected."""
        coll, _ = self._make_coll("T1")
        result = coll._inject_filter({})
        assert result == {"tenant_id": "T1"}

    def test_inject_filter_none(self):
        """None filter → creates filter with tenant_id."""
        coll, _ = self._make_coll("T1")
        result = coll._inject_filter(None)
        assert result == {"tenant_id": "T1"}

    def test_inject_filter_existing_correct(self):
        """Filter with correct tenant_id → passes through."""
        coll, _ = self._make_coll("T1")
        result = coll._inject_filter({"tenant_id": "T1", "status": "active"})
        assert result == {"tenant_id": "T1", "status": "active"}

    def test_inject_filter_cross_tenant_blocked(self):
        """Filter with wrong tenant_id → raises TenantViolationError."""
        from core.tenant_db import TenantViolationError
        coll, _ = self._make_coll("T1")
        with pytest.raises(TenantViolationError, match="Cross-tenant access blocked"):
            coll._inject_filter({"tenant_id": "T2"})

    def test_inject_doc_sets_tenant(self):
        """Insert document gets tenant_id forced."""
        coll, _ = self._make_coll("T1")
        doc = {"name": "test"}
        result = coll._inject_doc(doc)
        assert result["tenant_id"] == "T1"

    def test_inject_doc_correct_tenant_allowed(self):
        """Document with correct tenant_id → allowed."""
        coll, _ = self._make_coll("T1")
        doc = {"name": "test", "tenant_id": "T1"}
        result = coll._inject_doc(doc)
        assert result["tenant_id"] == "T1"

    def test_inject_doc_cross_tenant_blocked(self):
        """Document with wrong tenant_id → raises TenantViolationError."""
        from core.tenant_db import TenantViolationError
        coll, _ = self._make_coll("T1")
        with pytest.raises(TenantViolationError, match="Cannot insert document"):
            coll._inject_doc({"name": "test", "tenant_id": "T2"})


# ── Layer 1: Context Management Tests ─────────────────────────

class TestContextManagement:
    """Tests for contextvars-based tenant context."""

    def test_set_get_clear(self):
        from core.tenant_db import set_tenant_context, get_current_tenant_id, clear_tenant_context
        assert get_current_tenant_id() is None
        set_tenant_context("T1")
        assert get_current_tenant_id() == "T1"
        clear_tenant_context()
        assert get_current_tenant_id() is None

    def test_context_manager(self):
        from core.tenant_db import tenant_context, get_current_tenant_id
        assert get_current_tenant_id() is None
        with tenant_context("T1"):
            assert get_current_tenant_id() == "T1"
        assert get_current_tenant_id() is None

    def test_nested_context(self):
        from core.tenant_db import tenant_context, get_current_tenant_id
        with tenant_context("T1"):
            assert get_current_tenant_id() == "T1"
            with tenant_context("T2"):
                assert get_current_tenant_id() == "T2"
            assert get_current_tenant_id() == "T1"


# ── Layer 1: Explicit API Tests ──────────────────────────────

class TestExplicitAPI:
    """Tests for get_db(), get_db_for_tenant(), get_system_db()."""

    def test_get_db_without_context_raises(self):
        from core.tenant_db import get_db, TenantViolationError
        with pytest.raises(TenantViolationError, match="get_db\\(\\) called without tenant context"):
            get_db()

    def test_get_db_with_context(self):
        from core.tenant_db import get_db, set_tenant_context, TenantScopedDB
        set_tenant_context("T1")
        tdb = get_db()
        assert isinstance(tdb, TenantScopedDB)
        assert tdb.tenant_id == "T1"

    def test_get_db_for_tenant(self):
        from core.tenant_db import get_db_for_tenant, TenantScopedDB
        tdb = get_db_for_tenant("T1")
        assert isinstance(tdb, TenantScopedDB)
        assert tdb.tenant_id == "T1"

    def test_get_db_for_tenant_empty_raises(self):
        from core.tenant_db import get_db_for_tenant
        with pytest.raises(ValueError, match="tenant_id is required"):
            get_db_for_tenant("")

    def test_get_system_db(self):
        from core.tenant_db import get_system_db
        raw = get_system_db()
        assert type(raw).__name__ == "AsyncIOMotorDatabase" or type(raw).__name__ == "_SystemAuditGuardDB"


# ── Layer 1: LazyCollection Descriptor Tests ──────────────────

class TestLazyCollection:
    """Tests for the LazyCollection descriptor used in repositories."""

    def test_descriptor_returns_proxy_collection(self):
        from core.tenant_db import LazyCollection, set_tenant_context, TenantScopedCollection

        class TestRepo:
            coll = LazyCollection("bookings")

        # Without context
        raw_coll = TestRepo.coll
        assert type(raw_coll).__name__ == "SchemaOnlyCollection"

        # With context
        set_tenant_context("T1")
        scoped = TestRepo.coll
        assert isinstance(scoped, TenantScopedCollection)
        assert scoped._tenant_id == "T1"


# ── Layer 2: Cross-Tenant Attack Tests ───────────────────────

class TestCrossTenantBlocking:
    """Verifies that cross-tenant access is impossible."""

    def test_find_cross_tenant_blocked(self):
        from core.tenant_db import get_db_for_tenant, TenantViolationError
        db = get_db_for_tenant("tenant_A")
        with pytest.raises(TenantViolationError):
            db.bookings._inject_filter({"tenant_id": "tenant_B"})

    def test_insert_cross_tenant_blocked(self):
        from core.tenant_db import get_db_for_tenant, TenantViolationError
        db = get_db_for_tenant("tenant_A")
        with pytest.raises(TenantViolationError):
            db.bookings._inject_doc({"tenant_id": "tenant_B", "data": "test"})

    def test_update_cross_tenant_blocked(self):
        from core.tenant_db import get_db_for_tenant, TenantViolationError
        db = get_db_for_tenant("tenant_A")
        with pytest.raises(TenantViolationError):
            db.bookings._inject_filter({"tenant_id": "tenant_B", "status": "x"})


# ── Layer 2: Strict Mode Tests ──────────────────────────────

class TestStrictMode:
    """Tests for STRICT_TENANT_MODE enforcement."""

    def test_strict_mode_blocks_unscoped(self):
        import core.tenant_db as tdb
        original = tdb.STRICT_TENANT_MODE
        try:
            tdb.STRICT_TENANT_MODE = True
            from core.database import db
            coll = db.bookings
            with pytest.raises(tdb.TenantViolationError, match="STRICT_TENANT_MODE"):
                coll.find_one({})

        finally:
            tdb.STRICT_TENANT_MODE = original

    def test_soft_mode_allows_unscoped(self):
        import core.tenant_db as tdb
        original = tdb.STRICT_TENANT_MODE
        try:
            tdb.STRICT_TENANT_MODE = False
            from core.database import db
            coll = db.bookings  # Should not raise
            assert type(coll).__name__ == "AsyncIOMotorCollection"
        finally:
            tdb.STRICT_TENANT_MODE = original


# ── Layer 1: Aggregate Pipeline Injection ─────────────────────

class TestAggregateInjection:
    """Tests that aggregate pipelines get tenant_id injected."""

    def test_aggregate_prepends_match(self):
        from core.tenant_db import TenantScopedCollection
        from unittest.mock import MagicMock
        mock = MagicMock()
        coll = TenantScopedCollection(mock, "T1", "bookings")
        pipeline = [{"$group": {"_id": "$status"}}]
        coll.aggregate(pipeline)
        assert pipeline[0] == {"$match": {"tenant_id": "T1"}}

    def test_aggregate_injects_into_existing_match(self):
        from core.tenant_db import TenantScopedCollection
        from unittest.mock import MagicMock
        mock = MagicMock()
        coll = TenantScopedCollection(mock, "T1", "bookings")
        pipeline = [{"$match": {"status": "active"}}, {"$group": {"_id": "$room"}}]
        coll.aggregate(pipeline)
        assert pipeline[0]["$match"]["tenant_id"] == "T1"
        assert pipeline[0]["$match"]["status"] == "active"


# ── Layer 2: Concurrency Safety Test ─────────────────────────

class TestConcurrencySafety:
    """Verifies that contextvars provide per-task isolation."""

    def test_concurrent_contexts(self):
        import asyncio
        from core.tenant_db import set_tenant_context, get_current_tenant_id, clear_tenant_context

        results = {}

        async def task(name, tenant_id):
            set_tenant_context(tenant_id)
            await asyncio.sleep(0.01)
            results[name] = get_current_tenant_id()
            clear_tenant_context()

        async def run():
            await asyncio.gather(
                task("A", "tenant_A"),
                task("B", "tenant_B"),
            )

        asyncio.run(run())
        assert results["A"] == "tenant_A"
        assert results["B"] == "tenant_B"


# ── Layer 3: Static Audit — CI Enforcement ────────────────────

class TestStaticAudit:
    """Checks that raw db usage is detectable."""

    def test_grep_finds_raw_db_usage(self):
        """Verify the CI check script can detect raw db imports."""
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run(
            ["grep", "-rn", "from core.database import db", "--include=*.py"],
            capture_output=True, text=True, cwd=backend_dir,
        )
        # We expect some matches (legacy code + system files)
        # This test just verifies the detection mechanism works
        assert result.returncode == 0, "grep should find at least some raw db usage"
        lines = result.stdout.strip().split("\n")
        assert len(lines) > 0

    def test_repository_classes_use_lazy_collection(self):
        """Verify key repositories use LazyCollection, not raw db."""
        from core.tenant_db import LazyCollection

        from domains.pms.rooms.repositories.room_repository import RoomRepository
        from domains.pms.folio.repositories.folio_repository import FolioRepository
        from domains.guest.journey.repositories.guest_repository import GuestRepository
        from domains.pms.reservations.repositories.reservation_repository import ReservationRepository

        for repo_cls, attr in [
            (RoomRepository, "collection"),
            (FolioRepository, "collection"),
            (GuestRepository, "collection"),
            (ReservationRepository, "collection"),
        ]:
            desc = repo_cls.__dict__[attr]
            assert isinstance(desc, LazyCollection), (
                f"{repo_cls.__name__}.{attr} should be LazyCollection, got {type(desc)}"
            )


# ── Integration: TenantScopedDB End-to-End ───────────────────

class TestTenantScopedDBEndToEnd:
    """Tests that TenantScopedDB correctly scopes collection access."""

    def test_scoped_db_returns_scoped_collection(self):
        from core.tenant_db import TenantScopedDB, TenantScopedCollection, get_system_db
        raw = get_system_db()
        tdb = TenantScopedDB(raw, "T1")
        coll = tdb.bookings
        assert isinstance(coll, TenantScopedCollection)
        assert coll._tenant_id == "T1"

    def test_scoped_db_global_collection(self):
        from core.tenant_db import TenantScopedDB, TenantScopedCollection, get_system_db
        raw = get_system_db()
        tdb = TenantScopedDB(raw, "T1")
        coll = tdb.tenants
        assert not isinstance(coll, TenantScopedCollection)

    def test_scoped_db_via_getitem(self):
        from core.tenant_db import TenantScopedDB, TenantScopedCollection, get_system_db
        raw = get_system_db()
        tdb = TenantScopedDB(raw, "T1")
        coll = tdb["rooms"]
        assert isinstance(coll, TenantScopedCollection)
        assert coll._tenant_id == "T1"
