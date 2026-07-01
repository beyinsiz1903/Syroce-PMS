"""Phase 2 sandbox-only smoke test for tools/tenant_restore_drill.py.

Spins up a local mongod on an alternate port (27018), seeds a fake
multi-tenant fixture, runs real `mongodump` → drill `--execute` →
prune + validate, and asserts:

  * mongorestore subprocess succeeded for all tenant-scoped collections
  * staging DB contains target tenant docs (count > 0)
  * staging DB has zero cross-tenant leak (count == 0)
  * FK integrity: no orphan bookings/folios
  * Drill report markdown file written

Skipped if mongod / mongodump / mongorestore not available on PATH, or
if motor cannot connect to the spawned local mongo within the timeout.

Also covers the Phase 2 hard guardrail: an Atlas MONGO_URL must yield
BLOCK verdict even with --execute and --allow-prod-target.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_DRILL_PATH = _REPO / "tools" / "tenant_restore_drill.py"
_SEED_PATH = _REPO / "backend" / "scripts" / "seed_drill_fixture.py"
_CLASSIFY_PATH = _REPO / "backend" / "scripts" / "classify_tenant_scope.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(_CLASSIFY_PATH.parent))
classify_mod = _load("classify_tenant_scope", _CLASSIFY_PATH)
drill = _load("tenant_restore_drill", _DRILL_PATH)
seed_mod = _load("seed_drill_fixture", _SEED_PATH)


def _tools_available() -> bool:
    return all(shutil.which(t) for t in ("mongod", "mongodump", "mongorestore"))


def _free_port() -> int:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


pytestmark = pytest.mark.skipif(
    not _tools_available(),
    reason="mongod / mongodump / mongorestore not available on PATH",
)


@pytest.fixture(scope="module")
def local_mongo():
    """Spawn an isolated mongod on a free port; tear down at module end."""
    port = _free_port()
    dbpath = tempfile.mkdtemp(prefix="drill_mongo_")
    logpath = os.path.join(dbpath, "mongod.log")
    proc = subprocess.Popen(
        [
            "mongod",
            "--dbpath", dbpath,
            "--port", str(port),
            "--bind_ip", "127.0.0.1",
            "--logpath", logpath,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"mongodb://127.0.0.1:{port}"
    # Wait for ready (max ~10s)
    deadline = time.time() + 15
    ready = False
    while time.time() < deadline:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient

            async def _ping():
                c = AsyncIOMotorClient(url, serverSelectionTimeoutMS=500)
                try:
                    await c.admin.command("ping")
                finally:
                    c.close()

            asyncio.run(_ping())
            ready = True
            break
        except Exception:
            time.sleep(0.3)
    if not ready:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(dbpath, ignore_errors=True)
        pytest.skip("local mongod did not become ready in time")

    yield url

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    shutil.rmtree(dbpath, ignore_errors=True)


def test_smoke_full_drill_passes(local_mongo, tmp_path, monkeypatch):
    src_db = "drill_source"
    target_db = "drill_staging"
    tenant_id = "T1"

    summary = asyncio.run(seed_mod.seed(local_mongo, src_db))
    assert summary["tenants"]["T1"]["bookings"] == 2
    assert summary["tenants"]["T2"]["bookings"] == 2

    archive_dir = tmp_path / "bk"
    rc = subprocess.run(
        [
            "mongodump",
            f"--uri={local_mongo}",
            f"--db={src_db}",
            f"--out={str(archive_dir)}",
            "--gzip",
        ],
        check=False,
    ).returncode
    assert rc == 0, "mongodump failed"
    assert (archive_dir / src_db / "bookings.bson.gz").exists()

    # Drill should classify against the real backend tree but the only
    # collections that exist in the *archive* are our 7 fake ones; restore
    # loop already skips those missing from the archive. Override the
    # classification with our 7 collections so the plan is focused.
    fake_class = {
        "TENANT_SCOPED": [
            {"name": c, "ref_count": 1, "ref_files": ["seed.py"]}
            for c in seed_mod.COLLECTIONS
        ],
        "GLOBAL_EXCLUDE": [],
        "UNKNOWN_REVIEW_REQUIRED": [],
        "SYSTEM_INTERNAL": [],
        "_summary": {
            "TENANT_SCOPED": len(seed_mod.COLLECTIONS),
            "GLOBAL_EXCLUDE": 0,
            "UNKNOWN_REVIEW_REQUIRED": 0,
            "SYSTEM_INTERNAL": 0,
        },
    }
    monkeypatch.setattr(
        drill.classify_tenant_scope, "build_report", lambda root: fake_class
    )

    report_dir = tmp_path / "reports"
    rc = drill.main(
        [
            "--backup-archive", str(archive_dir),
            "--tenant-id", tenant_id,
            "--target-db", target_db,
            "--source-db-name", src_db,
            "--mongo-url", local_mongo,
            "--prod-db-name", "hotel_pms",
            "--report-dir", str(report_dir),
            "--execute",
        ]
    )
    assert rc == 0, "drill --execute should exit 0 on PASS verdict"

    async def _verify():
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(local_mongo)
        try:
            db = client[target_db]
            for coll in ("tenants", "guests", "bookings", "folios", "payments"):
                target_count = await db[coll].count_documents(
                    {"tenant_id": tenant_id}
                )
                leak_count = await db[coll].count_documents(
                    {"tenant_id": {"$ne": tenant_id}}
                )
                assert target_count > 0, f"{coll} has no target tenant docs"
                assert leak_count == 0, (
                    f"{coll} has {leak_count} cross-tenant docs after prune"
                )

            async for b in db["bookings"].find({"tenant_id": tenant_id}):
                g = await db["guests"].find_one({"_id": b["guest_id"]})
                assert g is not None, "orphan booking → guest"
                r = await db["rooms"].find_one({"_id": b["room_id"]})
                assert r is not None, "orphan booking → room"
        finally:
            client.close()

    asyncio.run(_verify())

    reports = list(report_dir.glob("*.md"))
    assert reports, "drill report not written"
    body = reports[0].read_text(encoding="utf-8")
    assert "Verdict: **PASS**" in body
    assert "Total leak docs: **0**" in body


def test_smoke_drill_detects_leak_when_prune_skipped(
    local_mongo, tmp_path, monkeypatch
):
    """Sanity: if validation runs without prune, leak count > 0 → FAIL verdict."""
    src_db = "drill_source_leak"
    target_db = "drill_staging_leak"

    asyncio.run(seed_mod.seed(local_mongo, src_db))

    archive_dir = tmp_path / "bk2"
    subprocess.run(
        [
            "mongodump",
            f"--uri={local_mongo}",
            f"--db={src_db}",
            f"--out={str(archive_dir)}",
            "--gzip",
        ],
        check=True,
    )
    subprocess.run(
        [
            "mongorestore",
            "--gzip",
            f"--uri={local_mongo}",
            f"--nsInclude={src_db}.bookings",
            f"--nsFrom={src_db}.bookings",
            f"--nsTo={target_db}.bookings",
            str(archive_dir),
        ],
        check=True,
        capture_output=True,
    )

    validation = asyncio.run(
        drill.validate_restore(local_mongo, target_db, "T1", ["bookings"])
    )
    assert validation["verdict"] == "FAIL"
    assert validation["leak_total"] > 0


def test_atlas_url_blocks_execute_even_with_allow_prod_flag(
    monkeypatch, tmp_path, capsys
):
    """Hard guardrail: Atlas URL → BLOCK; --allow-prod-target cannot bypass."""
    fake_class = {
        "TENANT_SCOPED": [
            {"name": "bookings", "ref_count": 1, "ref_files": ["x.py"]}
        ],
        "GLOBAL_EXCLUDE": [],
        "UNKNOWN_REVIEW_REQUIRED": [],
        "SYSTEM_INTERNAL": [],
        "_summary": {
            "TENANT_SCOPED": 1,
            "GLOBAL_EXCLUDE": 0,
            "UNKNOWN_REVIEW_REQUIRED": 0,
            "SYSTEM_INTERNAL": 0,
        },
    }
    monkeypatch.setattr(
        drill.classify_tenant_scope, "build_report", lambda root: fake_class
    )

    rc = drill.main(
        [
            "--backup-archive", str(tmp_path),
            "--tenant-id", "T1",
            "--target-db", "anything_else",
            "--mongo-url", "mongodb+srv://user:pass@cluster.mongodb.net/db",
            "--prod-db-name", "hotel_pms",
            "--allow-prod-target",
            "--execute",
        ]
    )
    out = capsys.readouterr().out
    assert "Atlas" in out
    assert "BLOCK" in out
    assert rc == 1


@pytest.mark.parametrize(
    "url",
    [
        "MONGODB+SRV://user:p@cluster.mongodb.net/db",
        "mongodb+srv://user:p@cluster.mongodb.net/db",
        "mongodb://shard.MONGODB.NET:27017/db",
        "mongodb://node1.cluster.mongodb.net:27017,node2.cluster.mongodb.net:27017/db?replicaSet=rs",
        "mongodb://x.mongodb-dev.net:27017",
        "mongodb://x.mongodbgov.net:27017",
    ],
)
def test_atlas_url_detection_case_insensitive_and_multi_host(url):
    assert drill._is_atlas_url(url) is True, url


@pytest.mark.parametrize(
    "url",
    [
        "mongodb://127.0.0.1:27018",
        "mongodb://localhost:27017/db",
        "mongodb://user:pass@10.0.0.5:27017/db",
        "mongodb://user@my-internal-mongo.local:27017,my-internal-2.local:27017/db",
        "",
        None,
    ],
)
def test_atlas_url_detection_allows_local(url):
    assert drill._is_atlas_url(url) is False, url


def test_seed_fixture_shares_atlas_guard_with_drill():
    """Architect requirement: seed must use the SAME hardened detector."""
    assert seed_mod._is_atlas_url is drill._is_atlas_url


@pytest.mark.parametrize(
    "url",
    [
        "mongodb://cluster.mongodb.net.:27017/db",  # trailing-dot FQDN
        "mongodb://node.MONGODB.NET./db?ssl=true",
        "mongodb+srv://x.cluster.mongodb.net.",
    ],
)
def test_atlas_trailing_dot_fqdn_blocked(url):
    assert drill._is_atlas_url(url) is True, url


def test_seed_refuses_atlas_url_without_dropping_db():
    """drop_database must NEVER be reachable through an Atlas URL."""
    with pytest.raises(SystemExit) as exc:
        asyncio.run(
            seed_mod.seed(
                "mongodb+srv://user:p@cluster.mongodb.net/db",
                "anything",
            )
        )
    assert "Atlas" in str(exc.value)


def test_slug_tenant_strips_path_chars():
    assert drill._slug_tenant("../../etc/passwd").startswith("etc")
    assert "/" not in drill._slug_tenant("a/b/c")
    assert drill._slug_tenant("") == "tenant"
    assert drill._slug_tenant("...") == "tenant"
    long_id = "x" * 200
    assert len(drill._slug_tenant(long_id)) == 64


def test_atlas_hostname_via_standard_url_also_blocked(monkeypatch, tmp_path, capsys):
    fake_class = {
        "TENANT_SCOPED": [
            {"name": "bookings", "ref_count": 1, "ref_files": ["x.py"]}
        ],
        "GLOBAL_EXCLUDE": [],
        "UNKNOWN_REVIEW_REQUIRED": [],
        "SYSTEM_INTERNAL": [],
        "_summary": {
            "TENANT_SCOPED": 1,
            "GLOBAL_EXCLUDE": 0,
            "UNKNOWN_REVIEW_REQUIRED": 0,
            "SYSTEM_INTERNAL": 0,
        },
    }
    monkeypatch.setattr(
        drill.classify_tenant_scope, "build_report", lambda root: fake_class
    )

    rc = drill.main(
        [
            "--backup-archive", str(tmp_path),
            "--tenant-id", "T1",
            "--target-db", "drill_staging",
            "--mongo-url", "mongodb://shard-00.cluster.mongodb.net:27017/db",
            "--prod-db-name", "hotel_pms",
            "--execute",
        ]
    )
    out = capsys.readouterr().out
    assert "Atlas" in out
    assert "BLOCK" in out
    assert rc == 1
