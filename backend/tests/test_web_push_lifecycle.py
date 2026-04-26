"""
Web Push subscription lifecycle tests.

Validates that ``dispatch_internal_message_push``:
  * counts successful deliveries (``sent``),
  * counts transient (5xx) errors as ``failed`` without pruning,
  * prunes (deletes) subscriptions when the push service returns 404/410,
  * short-circuits cleanly when there are no subscriptions to deliver to.

The real ``pywebpush`` package is an optional dependency and may not be
installed in the test environment; we install a lightweight stub into
``sys.modules`` for the duration of each test so the production import
path inside ``dispatch_internal_message_push`` picks it up.

Mongo is mocked out via monkeypatching ``web_push.db`` — these tests do
not require a running database.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

# These tests fully mock both Mongo (via monkeypatched ``web_push.db``)
# and ``pywebpush`` (via ``sys.modules``), so they do not require a
# running database or a real event-loop-bound Motor client and can run
# safely in CI.
from domains.guest.messaging import web_push


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_sub(user_id: str, endpoint: str) -> dict:
    """Build a minimal subscription row matching what Mongo would return."""
    return {
        "tenant_id": "t1",
        "user_id": user_id,
        "department": None,
        "endpoint": endpoint,
        "p256dh": "p256dh-test",
        "auth": "auth-test",
    }


class _FakePywebpush:
    """Drop-in replacement for the ``pywebpush`` module.

    ``plan`` is a list of ``(action, status)`` tuples consumed in order
    by successive calls to ``webpush(...)``:

    * ``("ok", None)``   → returns successfully,
    * ``("http", 410)``  → raises ``WebPushException`` whose
                            ``response.status_code`` is 410.
    """

    class WebPushException(Exception):
        def __init__(self, msg: str = "", response=None):
            super().__init__(msg)
            self.response = response

    def __init__(self, plan: list[tuple[str, int | None]]):
        self._plan = list(plan)
        self._idx = 0
        self.calls: list[dict] = []

    def webpush(self, **kwargs):
        self.calls.append(kwargs)
        if self._idx >= len(self._plan):
            raise AssertionError(
                f"webpush called more times ({self._idx + 1}) than planned "
                f"({len(self._plan)})"
            )
        action, status = self._plan[self._idx]
        self._idx += 1
        if action == "ok":
            return MagicMock()
        if action == "http":
            resp = MagicMock()
            resp.status_code = status
            raise self.WebPushException(f"http {status}", response=resp)
        raise AssertionError(f"unknown action: {action!r}")

    def install(self) -> types.ModuleType:
        mod = types.ModuleType("pywebpush")
        mod.webpush = self.webpush
        mod.WebPushException = self.WebPushException
        sys.modules["pywebpush"] = mod
        return mod


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def fake_db(monkeypatch):
    """Replace ``web_push.db`` with a fully mocked Mongo handle."""
    db_mock = MagicMock()
    db_mock.web_push_subscriptions = MagicMock()
    db_mock.web_push_subscriptions.delete_one = AsyncMock()
    monkeypatch.setattr(web_push, "db", db_mock)
    return db_mock


@pytest.fixture(autouse=True)
def stable_vapid_keys(monkeypatch):
    """Pin VAPID keys via env vars so ``get_vapid_keys`` skips Mongo."""
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "test-pub")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-priv")
    # Reset the in-process cache so the env vars are actually re-read.
    monkeypatch.setattr(web_push, "_VAPID_CACHE", None, raising=False)
    yield
    monkeypatch.setattr(web_push, "_VAPID_CACHE", None, raising=False)


@pytest.fixture
def restore_pywebpush():
    """Restore (or remove) ``sys.modules['pywebpush']`` after the test."""
    saved = sys.modules.get("pywebpush")
    yield
    if saved is None:
        sys.modules.pop("pywebpush", None)
    else:
        sys.modules["pywebpush"] = saved


def _set_subscriptions(db_mock, rows: list[dict]) -> None:
    """Wire ``db.web_push_subscriptions.find(...).to_list(...)`` to ``rows``."""
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=rows)
    db_mock.web_push_subscriptions.find = MagicMock(return_value=cursor)


# ── Tests ─────────────────────────────────────────────────────────────────

async def test_dispatch_prunes_410_subscription(fake_db, restore_pywebpush):
    """A 410 Gone response must delete the offending subscription row."""
    rows = [
        _make_sub("u1", "https://push.example/alive"),
        _make_sub("u1", "https://push.example/dead"),
    ]
    _set_subscriptions(fake_db, rows)

    fake = _FakePywebpush([("ok", None), ("http", 410)])
    fake.install()

    result = await web_push.dispatch_internal_message_push(
        tenant_id="t1",
        payload={"title": "hi", "body": "there"},
        to_user_id="u1",
    )

    assert result == {"attempted": 2, "sent": 1, "failed": 0, "pruned": 1}
    fake_db.web_push_subscriptions.delete_one.assert_awaited_once_with({
        "tenant_id": "t1",
        "user_id": "u1",
        "endpoint": "https://push.example/dead",
    })


async def test_dispatch_prunes_404_subscription(fake_db, restore_pywebpush):
    """404 Not Found also prunes (browser unsubscribed on its own)."""
    rows = [_make_sub("u2", "https://push.example/gone")]
    _set_subscriptions(fake_db, rows)

    fake = _FakePywebpush([("http", 404)])
    fake.install()

    result = await web_push.dispatch_internal_message_push(
        tenant_id="t1",
        payload={"title": "x"},
        to_user_id="u2",
    )

    assert result == {"attempted": 1, "sent": 0, "failed": 0, "pruned": 1}
    fake_db.web_push_subscriptions.delete_one.assert_awaited_once_with({
        "tenant_id": "t1",
        "user_id": "u2",
        "endpoint": "https://push.example/gone",
    })


async def test_dispatch_5xx_counts_failed_without_pruning(fake_db, restore_pywebpush):
    """Transient errors (5xx) increment ``failed`` but never delete the row."""
    rows = [_make_sub("u3", "https://push.example/transient")]
    _set_subscriptions(fake_db, rows)

    fake = _FakePywebpush([("http", 503)])
    fake.install()

    result = await web_push.dispatch_internal_message_push(
        tenant_id="t1",
        payload={"title": "y"},
        to_user_id="u3",
    )

    assert result == {"attempted": 1, "sent": 0, "failed": 1, "pruned": 0}
    fake_db.web_push_subscriptions.delete_one.assert_not_awaited()


async def test_dispatch_counts_mixed_outcomes(fake_db, restore_pywebpush):
    """``sent`` / ``failed`` / ``pruned`` add up correctly over a mixed batch."""
    rows = [
        _make_sub("u4", "https://push.example/a"),
        _make_sub("u4", "https://push.example/b"),
        _make_sub("u4", "https://push.example/c"),
        _make_sub("u4", "https://push.example/d"),
    ]
    _set_subscriptions(fake_db, rows)

    fake = _FakePywebpush([
        ("ok", None),     # a → sent
        ("http", 500),    # b → failed (5xx, kept)
        ("http", 410),    # c → pruned
        ("ok", None),     # d → sent
    ])
    fake.install()

    result = await web_push.dispatch_internal_message_push(
        tenant_id="t1",
        payload={"title": "z"},
        to_user_id="u4",
    )

    assert result == {"attempted": 4, "sent": 2, "failed": 1, "pruned": 1}
    fake_db.web_push_subscriptions.delete_one.assert_awaited_once_with({
        "tenant_id": "t1",
        "user_id": "u4",
        "endpoint": "https://push.example/c",
    })


async def test_dispatch_no_subscriptions_short_circuits(fake_db, restore_pywebpush):
    """No subscriptions → all counters zero, no webpush calls, no deletes."""
    _set_subscriptions(fake_db, [])

    fake = _FakePywebpush([])  # webpush() must never be invoked
    fake.install()

    result = await web_push.dispatch_internal_message_push(
        tenant_id="t1",
        payload={"title": "noop"},
        to_user_id="ghost",
    )

    assert result == {"attempted": 0, "sent": 0, "failed": 0, "pruned": 0}
    assert fake.calls == []
    fake_db.web_push_subscriptions.delete_one.assert_not_awaited()


async def test_dispatch_returns_zero_when_pywebpush_missing(fake_db, restore_pywebpush):
    """If pywebpush isn't installed, dispatch is a no-op (all counters zero)."""
    # Force the import inside dispatch_internal_message_push to fail.
    sys.modules.pop("pywebpush", None)
    sys.modules["pywebpush"] = None  # type: ignore[assignment]

    # Make sure that even if subscriptions exist, nothing is touched.
    _set_subscriptions(fake_db, [_make_sub("u5", "https://push.example/x")])

    result = await web_push.dispatch_internal_message_push(
        tenant_id="t1",
        payload={"title": "noop"},
        to_user_id="u5",
    )

    assert result == {"attempted": 0, "sent": 0, "failed": 0, "pruned": 0}
    fake_db.web_push_subscriptions.delete_one.assert_not_awaited()
