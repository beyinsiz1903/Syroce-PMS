"""Regression for Sentry E8 using an isolated, disposable local MongoDB.

Never reads deployment credentials or connects to the application's database.
"""
import os
import shutil
import socket
import subprocess
import time
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from shared_kernel import pos_idem
from shared_kernel.gl_posting import ensure_gl_idem_index


@pytest.fixture
def mongo_uri(tmp_path):
    executable = shutil.which("mongod")
    if not executable:
        # GitHub service containers expose Mongo on localhost but do not place
        # a `mongod` executable in the runner.  An explicit opt-in lets hard
        # gates reuse that disposable service without ever falling back to a
        # developer or production database implicitly.
        service_uri = os.environ.get("MONGO_TEST_URI", "").strip()
        parsed = urlparse(service_uri)
        if not service_uri or parsed.hostname not in {"localhost", "127.0.0.1"}:
            pytest.skip("Local mongod or explicit localhost MONGO_TEST_URI required")

        client = MongoClient(service_uri, serverSelectionTimeoutMS=2000)
        disposable_databases = (
            "salary_agreement_qa",
            "sequence_regression",
            "hr_release_audit",
            "payroll_atomic_test",
        )
        try:
            client.admin.command("ping")
            for name in disposable_databases:
                client.drop_database(name)
            yield service_uri
        finally:
            for name in disposable_databases:
                client.drop_database(name)
            client.close()
        return
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    uri = f"mongodb://127.0.0.1:{port}"
    process = subprocess.Popen([
        executable, "--dbpath", str(tmp_path), "--bind_ip", "127.0.0.1",
        "--replSet", "qaAudit",
        "--port", str(port), "--logpath", str(tmp_path / "mongod.log"),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = MongoClient(uri, serverSelectionTimeoutMS=200, directConnection=True)
    try:
        deadline = time.monotonic() + 15
        while True:
            try:
                client.admin.command("ping")
                break
            except Exception:
                if process.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail("Disposable MongoDB failed to start")
        client.admin.command("replSetInitiate", {"_id": "qaAudit", "members": [{"_id": 0, "host": f"127.0.0.1:{port}"}]})
        deadline = time.monotonic() + 20
        while not client.admin.command("hello").get("isWritablePrimary"):
            if time.monotonic() >= deadline:
                pytest.fail("Disposable replica set did not elect a primary")
            time.sleep(0.05)
        yield uri + "?replicaSet=qaAudit"
    finally:
        client.close()
        process.terminate()
        process.wait(timeout=10)


@pytest.mark.asyncio
async def test_legacy_null_sequences_preserved_and_real_duplicates_rejected(mongo_uri, monkeypatch):
    monkeypatch.setattr(pos_idem, "_INDEXES_READY", set())
    client = AsyncIOMotorClient(mongo_uri)
    collection = client.sequence_regression.gl_journal_entries
    db = SimpleNamespace(gl_journal_entries=collection)
    try:
        legacy = [
            {"tenant_id": "qa", "entry_no": "old-1"},
            {"tenant_id": "qa", "entry_no": "old-2", "fiscal_year": None, "posting_sequence": None},
            {"tenant_id": "qa", "entry_no": "old-3", "fiscal_year": None, "posting_sequence": None},
        ]
        await collection.insert_many(legacy)
        before = await collection.find().to_list(None)
        # Reproduce the production E11000 before verifying the corrected index.
        with pytest.raises(DuplicateKeyError):
            await collection.create_index(
                [("tenant_id", 1), ("fiscal_year", 1), ("posting_sequence", 1)],
                unique=True, name="ux_gl_journal_sequence",
            )
        await ensure_gl_idem_index(db)
        assert await collection.find().to_list(None) == before
        index = (await collection.index_information())["ux_gl_journal_sequence"]
        assert index["unique"] is True
        await collection.insert_one({"tenant_id": "qa", "entry_no": "new-1", "fiscal_year": 2026, "posting_sequence": 1})
        with pytest.raises(DuplicateKeyError):
            await collection.insert_one({"tenant_id": "qa", "entry_no": "new-2", "fiscal_year": 2026, "posting_sequence": 1})
        await collection.insert_one({"tenant_id": "qa", "entry_no": "next-year", "fiscal_year": 2027, "posting_sequence": 1})
        await collection.insert_one({"tenant_id": "other", "entry_no": "new-1", "fiscal_year": 2026, "posting_sequence": 1})
        await ensure_gl_idem_index(db)
    finally:
        client.close()


@pytest.mark.asyncio
async def test_existing_real_duplicate_sequences_still_fail_closed(mongo_uri, monkeypatch):
    monkeypatch.setattr(pos_idem, "_INDEXES_READY", set())
    client = AsyncIOMotorClient(mongo_uri)
    collection = client.sequence_regression.gl_journal_entries
    try:
        await collection.insert_many([
            {"tenant_id": "qa", "entry_no": f"entry-{i}", "fiscal_year": 2026, "posting_sequence": 1}
            for i in range(2)
        ])
        with pytest.raises(DuplicateKeyError):
            await ensure_gl_idem_index(SimpleNamespace(gl_journal_entries=collection))
        assert await collection.count_documents({}) == 2
    finally:
        client.close()
