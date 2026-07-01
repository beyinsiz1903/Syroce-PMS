"""Sprint 32 — catalog cache invalidation hardening tests.

Covers:
1. `safe_invalidate` tenant-id charset validation (rejects glob meta).
2. Mutation-time invalidation wipes ALL cached query variants
   (e.g. ?q=foo, ?active_only=false, plain).
3. Failure path bumps the invalidation_failures counter and emits a
   warning log instead of silently passing.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cache_manager import cache, cached  # noqa: E402


class _FakeUser:
    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        self.username = "test"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TenantIdValidationTests(unittest.TestCase):
    """Charset guard: only [A-Za-z0-9._-] allowed."""

    def test_uuid_accepted(self):
        self.assertTrue(cache._is_safe_tenant_id(
            "57986e4f-7977-44c9-bed9-05aadf38853b"))

    def test_alphanumeric_accepted(self):
        self.assertTrue(cache._is_safe_tenant_id("tenant_42.prod"))

    def test_glob_metacharacters_rejected(self):
        for bad in ("*", "tenant*", "?", "[abc]", "a\\b", "a:b"):
            with self.subTest(value=bad):
                self.assertFalse(cache._is_safe_tenant_id(bad))

    def test_empty_or_none_rejected(self):
        self.assertFalse(cache._is_safe_tenant_id(""))
        self.assertFalse(cache._is_safe_tenant_id(None))  # type: ignore[arg-type]

    def test_overlong_rejected(self):
        self.assertFalse(cache._is_safe_tenant_id("a" * 200))

    def test_non_ascii_rejected(self):
        # Unicode alphanumerics must NOT pass — strict ASCII only
        for bad in ("tenantü", "тенант", "ｔｅｎａｎｔ", "tenant\u200b"):
            with self.subTest(value=bad):
                self.assertFalse(cache._is_safe_tenant_id(bad))

    def test_reject_path_does_not_call_delete_pattern(self):
        with patch.object(cache, "delete_pattern") as dp:
            ok = cache.safe_invalidate("evil*tenant", "good_prefix")
            self.assertFalse(ok)
            dp.assert_not_called()
            ok2 = cache.safe_invalidate("good_tenant", "bad*prefix")
            self.assertFalse(ok2)
            dp.assert_not_called()

    def test_unsafe_prefix_rejected(self):
        before = cache.invalidation_failures.get("evil*", 0)
        ok = cache.safe_invalidate("good_tenant", "evil*")
        self.assertFalse(ok)
        self.assertGreater(
            cache.invalidation_failures.get("evil*", 0), before)


class CachedVariantInvalidationTests(unittest.TestCase):
    """Mutation must wipe all query-param variants for the tenant."""

    def setUp(self):
        if not cache.enabled:
            self.skipTest("cache disabled in this env")

    def test_all_variants_invalidated_after_mutation(self):
        tenant = "tenant-variant-test-001"
        # Invalidate any leftovers from prior runs
        cache.safe_invalidate(tenant, "test_widgets")

        call_count = {"n": 0}

        @cached(ttl=60, key_prefix="test_widgets")
        async def list_widgets(active_only: bool = True,
                               q: str | None = None,
                               current_user: _FakeUser | None = None):
            call_count["n"] += 1
            return {"hit": call_count["n"], "active_only": active_only,
                    "q": q}

        user = _FakeUser(tenant)

        # 3 distinct variants — should populate 3 separate cache keys
        a1 = _run(list_widgets(active_only=True, q=None, current_user=user))
        a2 = _run(list_widgets(active_only=False, q=None, current_user=user))
        a3 = _run(list_widgets(active_only=True, q="foo", current_user=user))
        self.assertEqual(call_count["n"], 3)

        # Re-run: should all be cache hits (counter must NOT advance)
        b1 = _run(list_widgets(active_only=True, q=None, current_user=user))
        b2 = _run(list_widgets(active_only=False, q=None, current_user=user))
        b3 = _run(list_widgets(active_only=True, q="foo", current_user=user))
        self.assertEqual(call_count["n"], 3, "all 3 variants must be cached")
        self.assertEqual((a1, a2, a3), (b1, b2, b3))

        # Mutation → wipe ALL variants
        ok = cache.safe_invalidate(tenant, "test_widgets")
        self.assertTrue(ok)

        # All 3 must miss now (counter advances by 3)
        _run(list_widgets(active_only=True, q=None, current_user=user))
        _run(list_widgets(active_only=False, q=None, current_user=user))
        _run(list_widgets(active_only=True, q="foo", current_user=user))
        self.assertEqual(call_count["n"], 6,
                         "all 3 cached variants must be re-fetched")

    def test_invalidation_does_not_cross_tenants(self):
        t_a, t_b = "tenant-iso-A", "tenant-iso-B"
        cache.safe_invalidate(t_a, "test_iso")
        cache.safe_invalidate(t_b, "test_iso")

        n = {"a": 0, "b": 0}

        @cached(ttl=60, key_prefix="test_iso")
        async def get_thing(current_user: _FakeUser | None = None):
            n[current_user.tenant_id[-1].lower()] += 1
            return {"tenant": current_user.tenant_id}

        ua, ub = _FakeUser(t_a), _FakeUser(t_b)
        _run(get_thing(current_user=ua))
        _run(get_thing(current_user=ub))
        self.assertEqual((n["a"], n["b"]), (1, 1))

        # Wipe only A
        cache.safe_invalidate(t_a, "test_iso")
        _run(get_thing(current_user=ua))  # miss
        _run(get_thing(current_user=ub))  # still HIT
        self.assertEqual((n["a"], n["b"]), (2, 1),
                         "B's cache must survive A's invalidation")


class LegacyHelperGuardrailTests(unittest.TestCase):
    """Sprint 32 round 2: central guard in delete_pattern protects ALL
    legacy invalidation helpers from accidental cross-tenant wipe."""

    def test_dashboard_cache_invalidate_rejects_unsafe_tenant(self):
        from cache_manager import DashboardCache
        with patch.object(cache.client, "keys") as kk, \
             patch.object(cache.client, "delete") as dd:
            DashboardCache.invalidate("evil*tenant")
            kk.assert_not_called()
            dd.assert_not_called()

    def test_dashboard_cache_rejects_colon_skew_payload(self):
        """`a:b*c` would skew naive split-based validation; the strict
        full-pattern regex must still reject it."""
        from cache_manager import (
            DashboardCache, RoomCache, BookingCache, GuestCache,
        )
        for helper in (
            lambda: DashboardCache.invalidate("a:b*c"),
            lambda: RoomCache.invalidate("a:b*c"),
            lambda: BookingCache.invalidate("a:b*c"),
            lambda: GuestCache.invalidate("a:b*c"),
        ):
            with self.subTest(helper=helper):
                with patch.object(cache.client, "keys") as kk, \
                     patch.object(cache.client, "delete") as dd:
                    helper()
                    kk.assert_not_called()
                    dd.assert_not_called()

    def test_invalidate_tenant_cache_rejects_unsafe_tenant(self):
        with patch.object(cache.client, "keys") as kk, \
             patch.object(cache.client, "delete") as dd:
            ok = cache.invalidate_tenant_cache("a:b*c", "rooms")
            self.assertFalse(ok)
            kk.assert_not_called()
            dd.assert_not_called()

    def test_invalidate_tenant_cache_passes_safe_tenant(self):
        if not cache.enabled:
            self.skipTest("cache disabled in this env")
        with patch.object(cache.client, "keys",
                          return_value=[]) as kk:
            ok = cache.invalidate_tenant_cache(
                "57986e4f-7977-44c9-bed9-05aadf38853b", "dashboard")
            self.assertTrue(ok)
            kk.assert_called_once()

    def test_known_safe_legacy_paths_still_work(self):
        """Regression: the hardening must NOT block legitimate callers.
        Each helper with a safe tenant_id (and optional sub-id) must
        actually reach the backend."""
        if not cache.enabled:
            self.skipTest("cache disabled in this env")
        from cache_manager import (
            DashboardCache, RoomCache, BookingCache, GuestCache,
            ReportCache,
        )
        safe_tenant = "57986e4f-7977-44c9-bed9-05aadf38853b"
        cases = [
            # name, callable, expects_keys (pattern), expects_delete (single key)
            ("Dashboard.invalidate",
             lambda: DashboardCache.invalidate(safe_tenant), True, False),
            ("Room.invalidate (no id)",
             lambda: RoomCache.invalidate(safe_tenant), True, False),
            ("Room.invalidate (with id)",
             lambda: RoomCache.invalidate(safe_tenant, "room-101"),
             False, True),
            ("Booking.invalidate (no id)",
             lambda: BookingCache.invalidate(safe_tenant), True, False),
            ("Booking.invalidate (with id)",
             lambda: BookingCache.invalidate(safe_tenant, "bk-7"),
             True, True),
            ("Guest.invalidate (with id)",
             lambda: GuestCache.invalidate(safe_tenant, "g1"),
             True, False),
            ("Guest.invalidate (no id)",
             lambda: GuestCache.invalidate(safe_tenant), True, False),
            ("Report.invalidate_all",
             lambda: ReportCache.invalidate_all(safe_tenant), True, False),
        ]
        for name, fn, expect_keys, expect_delete in cases:
            with self.subTest(case=name):
                with patch.object(cache.client, "keys",
                                  return_value=["x"]) as kk, \
                     patch.object(cache.client, "delete") as dd:
                    fn()
                    if expect_keys:
                        self.assertTrue(
                            kk.called,
                            f"{name}: keys() must be invoked (not blocked)")
                    if expect_delete:
                        self.assertTrue(
                            dd.called,
                            f"{name}: delete() must be invoked")


class FailureMetricsTests(unittest.TestCase):
    """Failure path bumps counter + emits WARNING (no silent pass)."""

    def test_unsafe_tenant_logs_warning_and_counts(self):
        before_fail = cache.invalidation_failures.get("anything", 0)
        with self.assertLogs("cache_manager", level="WARNING") as cm:
            ok = cache.safe_invalidate("evil*tenant", "anything")
        self.assertFalse(ok)
        self.assertTrue(any("REJECTED unsafe tenant_id" in m
                            for m in cm.output))
        self.assertEqual(
            cache.invalidation_failures.get("anything", 0),
            before_fail + 1)

    def test_backend_failure_logs_and_counts(self):
        if not cache.enabled:
            self.skipTest("cache disabled in this env")
        before_fail = cache.invalidation_failures.get("test_be_fail", 0)
        with patch.object(cache, "delete_pattern", return_value=False):
            with self.assertLogs("cache_manager", level="WARNING") as cm:
                ok = cache.safe_invalidate("good_tenant",
                                           "test_be_fail")
        self.assertFalse(ok)
        self.assertTrue(any("FAILED pattern=" in m for m in cm.output))
        self.assertEqual(
            cache.invalidation_failures.get("test_be_fail", 0),
            before_fail + 1)


if __name__ == "__main__":
    unittest.main()
