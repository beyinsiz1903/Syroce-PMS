"""Task #629 — live proof Academy certificate issuance is race-safe against a
real Mongo unique index.

Task #628's ``tests/test_academy_security.py`` exercises the
``DuplicateKeyError`` resolution path with an *in-memory fake* collection that
only SIMULATES the unique index. That is fast and hermetic, but it never proves
the real backstop exists: the engine's idempotency relies entirely on the
DB-level ``uniq_academy_cert_tenant_user_course`` unique index (see
``backend/bootstrap/phases/d_perf.py``), because the engine's
``find_one`` + ``insert_one`` guard in ``core.academy._issue_certificate`` is
NOT atomic under a concurrent double-submit.

This module proves the backstop end to end against a live Mongo (CI mongod /
Atlas):

  1. ``ensure_academy_indexes`` — the SAME production code path phase-D runs at
     boot — actually builds all three academy indexes, and the certificate /
     progress indexes are really ``unique=True`` (asserted via
     ``index_information()``; a missing/non-unique index would leave the race
     window open and must fail, never fake-green).
  2. Two TRULY concurrent passing ``_issue_certificate`` calls (``asyncio.gather``
     over the real engine, sharing one event loop and one Mongo connection)
     yield exactly ONE certificate row; the loser's insert hits the unique
     index, raises ``DuplicateKeyError``, and the engine resolves to the winning
     row so both callers receive the same certificate id.
  3. A sequential re-issue (replay) returns the original row, never a second.

Integration style — requires a reachable Mongo (``MONGO_URL`` /
``MONGO_ATLAS_URI``); the engine's ``_db()`` already binds to it at import.
Skips cleanly when unreachable so a missing DB can never silently fake-green.
Every row is written under a throwaway, randomly-suffixed tenant id and purged
in ``finally`` — net-zero drift, never touches the pilot tenant.

LOCAL run convention — a forked mongod is reaped between bash tool calls, so
start mongod and run pytest in ONE shell command:

    mkdir -p /tmp/acad && mongod --dbpath /tmp/acad --port 27017 --fork \\
        --logpath /tmp/acad/mongod.log
    MONGO_URL=mongodb://localhost:27017 DB_NAME=syroce_test \\
        python -m pytest tests/integration/test_academy_cert_race_live.py -rs -v
    mongod --dbpath /tmp/acad --shutdown

Confirm with ``-rs`` that the cases actually RAN (skips here mean Mongo was
unreachable, which turns a green suite into an all-skipped no-op).
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest

from core import academy
from bootstrap.phases.d_perf import ensure_academy_indexes

COURSE_ID = "reception-temelleri"


def _mongo_reachable() -> bool:
    """Ping the same Mongo the engine binds to; skip when unreachable."""
    if not (os.environ.get("MONGO_URL") or os.environ.get("MONGO_ATLAS_URI")):
        return False
    try:
        from pymongo import MongoClient

        url = os.environ.get("MONGO_URL") or os.environ.get("MONGO_ATLAS_URI")
        client = MongoClient(url, serverSelectionTimeoutMS=3000)
        try:
            client.admin.command("ping")
            return True
        finally:
            client.close()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _mongo_reachable(),
    reason="Live academy race test needs a reachable Mongo (MONGO_URL/MONGO_ATLAS_URI)",
)


def _tenant() -> str:
    """A throwaway tenant id so the test never collides with real data."""
    return f"t-acad-race-{uuid.uuid4().hex[:12]}"


async def _purge(tenant_id: str) -> None:
    """Remove every academy row this test wrote for ``tenant_id``.

    Runs even when the safeguard FAILS (both inserts succeed), so a regression
    can never leak duplicate certificate rows.
    """
    db = academy._db()
    flt = {"tenant_id": tenant_id}
    await db.academy_certificates.delete_many(flt)
    await db.academy_progress.delete_many(flt)
    await db.academy_attempts.delete_many(flt)


# ── 1. The production index builder really makes the indexes unique ───────


@pytest.mark.asyncio
async def test_academy_indexes_are_built_unique():
    """phase-D's ``ensure_academy_indexes`` builds the cert/progress indexes as
    ``unique=True`` — the DB-level backstop the engine's idempotency relies on."""
    db = academy._db()
    # Run the SAME code path phase-D runs at boot (idempotent — safe to repeat).
    await ensure_academy_indexes(db)

    cert_info = await db.academy_certificates.index_information()
    assert "uniq_academy_cert_tenant_user_course" in cert_info, (
        "certificate unique index missing — the race backstop is NOT enforced; "
        f"present indexes: {sorted(cert_info)}")
    assert cert_info["uniq_academy_cert_tenant_user_course"].get("unique") is True, (
        "uniq_academy_cert_tenant_user_course exists but is NOT unique — the "
        "concurrent-submit race window is open")
    # Key shape must match the engine's read/insert filter.
    assert cert_info["uniq_academy_cert_tenant_user_course"]["key"] == [
        ("tenant_id", 1), ("user_id", 1), ("course_id", 1)]

    prog_info = await db.academy_progress.index_information()
    assert prog_info.get(
        "uniq_academy_progress_tenant_user_course", {}).get("unique") is True, (
        "uniq_academy_progress_tenant_user_course must be unique to guard "
        "against duplicate per-user progress rows")


# ── 2. Concurrent issuance → exactly one certificate (real index race) ────


@pytest.mark.asyncio
async def test_concurrent_certificate_issuance_one_row_real_mongo():
    """Two simultaneous passing issuances against real Mongo → exactly ONE row.

    The losing insert collides with the real unique index, raises
    ``DuplicateKeyError``, and the engine resolves both callers to the single
    winning certificate. This is the invariant the fake-collection unit test can
    only simulate.
    """
    db = academy._db()
    await ensure_academy_indexes(db)
    course = academy.get_course_raw(COURSE_ID)
    assert course is not None, f"course {COURSE_ID} must exist in the catalog"

    tenant_id = _tenant()
    user_id = "u-race-1"
    try:
        cert_a, cert_b = await asyncio.gather(
            academy._issue_certificate(tenant_id, user_id, "Race User", course, 100),
            academy._issue_certificate(tenant_id, user_id, "Race User", course, 100),
        )
        # Exactly one persisted row; both callers see the same certificate.
        count = await db.academy_certificates.count_documents(
            {"tenant_id": tenant_id, "user_id": user_id, "course_id": COURSE_ID})
        assert count == 1, (
            f"expected exactly 1 certificate after a concurrent double-issue, "
            f"got {count} — the unique-index race backstop did NOT hold")
        assert cert_a["id"] == cert_b["id"], (
            "concurrent callers must resolve to the SAME certificate id")
    finally:
        await _purge(tenant_id)


# ── 3. Sequential replay returns the original certificate ─────────────────


@pytest.mark.asyncio
async def test_certificate_reissue_is_idempotent_real_mongo():
    """A later (higher-score) re-pass returns the original cert, never a new one."""
    db = academy._db()
    await ensure_academy_indexes(db)
    course = academy.get_course_raw(COURSE_ID)
    assert course is not None

    tenant_id = _tenant()
    user_id = "u-replay-1"
    try:
        first = await academy._issue_certificate(
            tenant_id, user_id, "Replay User", course, 80)
        second = await academy._issue_certificate(
            tenant_id, user_id, "Replay User", course, 95)
        assert first["id"] == second["id"]
        # Original score is preserved — a later pass does not overwrite it.
        assert second["score"] == 80
        count = await db.academy_certificates.count_documents(
            {"tenant_id": tenant_id, "user_id": user_id, "course_id": COURSE_ID})
        assert count == 1
    finally:
        await _purge(tenant_id)
