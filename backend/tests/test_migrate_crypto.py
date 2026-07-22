import hashlib
import os
import stat
from unittest.mock import AsyncMock, MagicMock, patch, call

import bson
import pytest
from core.crypto.errors import KeyDerivationError
from core.crypto.keys import load_keyring
from scripts.migrate_crypto import (
    MigrationPreflightError,
    RollbackVerificationError,
    _canonical_json,
    create_backup_file,
    execute_migration,
    restore_single_doc,
    run_migration,
    run_restore,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_db(db_name="test_db"):
    mock_db = MagicMock()
    mock_db.name = db_name
    return mock_db


def _make_mock_svc(current_kid="v2", has_previous=False, previous_kid="v1"):
    mock_svc = MagicMock()
    mock_svc._keyring.current_kid = current_kid
    mock_svc._keyring.has_previous = has_previous
    mock_svc._keyring._previous_kid = previous_kid
    return mock_svc


# ---------------------------------------------------------------------------
# 1. Backup file permission (0600)
# ---------------------------------------------------------------------------

def test_backup_mode_0600(tmp_path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        mock_db = _make_mock_db()
        mock_svc = _make_mock_svc()
        records = []
        backup_file = create_backup_file(mock_db, mock_svc, records)
        st = os.stat(backup_file)
        assert stat.S_IMODE(st.st_mode) == 0o600
    finally:
        os.chdir(original_cwd)


# ---------------------------------------------------------------------------
# 2. Backup manifest, BSON safety, and canonical checksum
# ---------------------------------------------------------------------------

def test_bson_backup_manifest_and_checksum(tmp_path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        mock_db = _make_mock_db()
        mock_svc = _make_mock_svc()

        oid = bson.ObjectId()
        records = [{"collection": "test", "doc": {"_id": oid, "date": bson.datetime.datetime.now()}}]
        backup_file = create_backup_file(mock_db, mock_svc, records)

        with open(backup_file, "r") as f:
            read_back = bson.json_util.loads(f.read())

        assert "manifest" in read_back
        manifest = read_back["manifest"]
        assert manifest["db_name"] == "test_db"
        assert manifest["record_count"] == 1
        assert "payload_checksum" in manifest

        # Verify canonical checksum matches
        recomputed = hashlib.sha256(_canonical_json(read_back["records"])).hexdigest()
        assert manifest["payload_checksum"] == recomputed

        assert read_back["records"][0]["doc"]["_id"] == oid
    finally:
        os.chdir(original_cwd)


# ---------------------------------------------------------------------------
# 3. Key / Kid combination errors
# ---------------------------------------------------------------------------

def test_previous_key_without_kid_fails(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "current-master-12345678901234567890")
    monkeypatch.setenv("CM_KEY_VERSION_CURRENT", "v2")
    monkeypatch.setenv("CM_MASTER_KEY_PREVIOUS", "previous-master-123")
    monkeypatch.delenv("CM_KEY_VERSION_PREVIOUS", raising=False)
    with pytest.raises(KeyDerivationError, match="Both CM_MASTER_KEY_PREVIOUS and CM_KEY_VERSION_PREVIOUS must be set together"):
        load_keyring()


def test_previous_kid_without_key_fails(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "current-master-12345678901234567890")
    monkeypatch.setenv("CM_KEY_VERSION_CURRENT", "v2")
    monkeypatch.delenv("CM_MASTER_KEY_PREVIOUS", raising=False)
    monkeypatch.setenv("CM_KEY_VERSION_PREVIOUS", "v1")
    with pytest.raises(KeyDerivationError, match="Both CM_MASTER_KEY_PREVIOUS and CM_KEY_VERSION_PREVIOUS must be set together"):
        load_keyring()


def test_equal_current_previous_kid_fails(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "current-master-12345678901234567890")
    monkeypatch.setenv("CM_KEY_VERSION_CURRENT", "v1")
    monkeypatch.setenv("CM_MASTER_KEY_PREVIOUS", "previous-master-123")
    monkeypatch.setenv("CM_KEY_VERSION_PREVIOUS", "v1")
    with pytest.raises(KeyDerivationError, match="Current and previous key versions \\(kids\\) cannot be identical"):
        load_keyring()


def test_equal_current_previous_master_fails(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "same-master-12345678901234567890")
    monkeypatch.setenv("CM_KEY_VERSION_CURRENT", "v2")
    monkeypatch.setenv("CM_MASTER_KEY_PREVIOUS", "same-master-12345678901234567890")
    monkeypatch.setenv("CM_KEY_VERSION_PREVIOUS", "v1")
    with pytest.raises(KeyDerivationError, match="Current and previous master keys cannot be identical"):
        load_keyring()


# ---------------------------------------------------------------------------
# 4. Production key minimum 32-byte length check
# ---------------------------------------------------------------------------

def test_production_master_key_length_checks(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "too-short")
    monkeypatch.setenv("CM_KEY_VERSION_CURRENT", "v2")
    with pytest.raises(KeyDerivationError, match="CM_MASTER_KEY_CURRENT is too weak for production"):
        load_keyring()


# ---------------------------------------------------------------------------
# 5. Unknown collection → exit 1
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_collection_fails(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CRYPTO_V2_ENABLED", "true")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "current-master-12345678901234567890")

    with patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
        class Args:
            restore_backup = None
            force_v2 = False
            all = False
            collection = "unknown_coll"
            dry_run = False

        with pytest.raises(SystemExit):
            await run_migration(Args())

        mock_exit.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# 6. Preflight: unknown kid prevents backup AND execution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_kid_prevents_backup_and_writes(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CRYPTO_V2_ENABLED", "true")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "current-master-12345678901234567890")

    async def mock_collect(*args, **kwargs):
        from scripts.migrate_crypto import stats
        stats["unknown_kid_records"] += 1
        return [{"collection": "test", "doc": {}}]

    with patch("scripts.migrate_crypto.collect_records", side_effect=mock_collect), \
         patch("scripts.migrate_crypto.create_backup_file") as m_backup, \
         patch("scripts.migrate_crypto.execute_migration") as m_execute:

        class Args:
            restore_backup = None
            force_v2 = False
            all = True
            collection = None
            dry_run = False

        with pytest.raises(MigrationPreflightError, match="Preflight check failed"):
            await run_migration(Args())

        m_backup.assert_not_called()
        m_execute.assert_not_called()


# ---------------------------------------------------------------------------
# 7. Directory fsync failure is FATAL — removes backup and blocks execution
# ---------------------------------------------------------------------------

def test_directory_fsync_failure_prevents_execution(tmp_path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        mock_db = _make_mock_db()
        mock_svc = _make_mock_svc()
        records = []

        real_os_open = os.open
        call_count = [0]

        def fake_os_open(path, flags, mode=0o666):
            call_count[0] += 1
            if call_count[0] == 2:  # second call is directory open
                raise OSError("Simulated dir open failure")
            return real_os_open(path, flags, mode)

        with patch("os.open", side_effect=fake_os_open):
            with pytest.raises(RuntimeError, match="Directory fsync failed"):
                create_backup_file(mock_db, mock_svc, records)

        # Backup file must be removed after dir fsync failure
        remaining = list(tmp_path.glob("migration_backup_*.json"))
        assert len(remaining) == 0, "Backup file must be deleted on directory fsync failure"

    finally:
        os.chdir(original_cwd)


def test_directory_fsync_called(tmp_path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        mock_db = _make_mock_db()
        mock_svc = _make_mock_svc()
        records = []
        with patch("os.fsync") as mock_fsync:
            create_backup_file(mock_db, mock_svc, records)
            # os.fsync must be called at least twice: once for file fd, once for directory fd
            assert mock_fsync.call_count >= 2
    finally:
        os.chdir(original_cwd)


# ---------------------------------------------------------------------------
# 8. Restore validates env and DB (mismatch → exit 1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restore_validates_env_and_db(tmp_path, monkeypatch):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        manifest = {
            "app_env": "production",
            "db_name": "prod_db",
            "record_count": 0,
            "payload_checksum": hashlib.sha256(_canonical_json([])).hexdigest(),
        }
        data = {"manifest": manifest, "records": []}
        backup_file = "test_env_mismatch.json"
        with open(backup_file, "w") as f:
            f.write(bson.json_util.dumps(data))

        mock_db = _make_mock_db("dev_db")
        monkeypatch.setenv("APP_ENV", "development")

        with patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
            with pytest.raises(SystemExit):
                await run_restore(mock_db, backup_file)
            mock_exit.assert_called_once_with(1)
    finally:
        os.chdir(original_cwd)


# ---------------------------------------------------------------------------
# 9. Dry-run performs full in-memory crypto roundtrip verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_performs_crypto_roundtrip_verification():
    mock_db = MagicMock()
    mock_coll = AsyncMock()
    mock_db.__getitem__.return_value = mock_coll

    mock_svc = MagicMock()
    mock_svc.decrypt_dict.return_value = {"secret": "plaintext"}
    mock_svc.encrypt_dict.return_value = "new_ciphertext"

    # Roundtrip verify returns DIFFERENT value to simulate failure
    mock_svc.decrypt_dict.side_effect = [
        {"secret": "plaintext"},   # initial decrypt
        {"secret": "CORRUPTED"},   # roundtrip verify → mismatch
    ]

    records = [
        {"collection": "provider_secrets", "doc": {
            "_id": "1", "tenant_id": "t1", "provider": "p1", "property_id": "prop1",
            "encrypted_payload": {"key": "old_val"},
        }}
    ]

    with pytest.raises(RuntimeError, match="Dry-run in-memory crypto roundtrip verification failed"):
        await execute_migration(mock_db, mock_svc, records, dry_run=True)

    # update_one must NOT have been called in dry-run
    mock_coll.update_one.assert_not_called()


# ---------------------------------------------------------------------------
# 10. restore_single_doc: read-back mismatch raises RollbackVerificationError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restore_readback_mismatch_is_fatal():
    mock_db = MagicMock()
    mock_coll = AsyncMock()
    mock_db.__getitem__.return_value = mock_coll

    mock_coll.replace_one.return_value.matched_count = 1
    # find_one returns a document that differs from what we wanted to restore
    mock_coll.find_one.return_value = {"_id": "1", "tenant_id": "t1", "data": "DIFFERENT"}

    doc = {"_id": "1", "tenant_id": "t1", "provider": "p1", "property_id": "prop1", "data": "ORIGINAL"}

    with pytest.raises(RollbackVerificationError, match="Rollback read-back mismatch"):
        await restore_single_doc(mock_db, "provider_secrets", doc)


# ---------------------------------------------------------------------------
# 11. Rollback chain continues even if first rollback fails
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_first_rollback_failure_does_not_stop_remaining_rollbacks():
    mock_db = MagicMock()
    mock_coll = AsyncMock()
    mock_db.__getitem__.return_value = mock_coll

    # update_one always succeeds
    mock_coll.update_one.return_value.matched_count = 1
    mock_coll.update_one.return_value.modified_count = 1

    # Doc 1 find_one: verify OK
    # Doc 2 find_one: verify fails (triggers rollback)
    # Rollback doc2 (first rollback): replace fails → matched_count=0
    # Rollback doc1 (second rollback): must still be attempted
    find_one_responses = [
        {"id": "doc1", "tenant_id": "t1", "provider": "p1", "property_id": "prop1", "encrypted_payload": "right_payload"},  # doc1 verify
        {"id": "doc2", "tenant_id": "t1", "provider": "p1", "property_id": "prop1", "encrypted_payload": "wrong_payload"},  # doc2 verify fails
    ]
    mock_coll.find_one.side_effect = find_one_responses

    # First replace_one (rollback doc2): matched_count=0 → failure
    # Second replace_one (rollback doc1): matched_count=1 → success, read-back matches
    replace_responses = [
        MagicMock(matched_count=0),  # rollback doc2 fails
        MagicMock(matched_count=1),  # rollback doc1 succeeds
    ]
    mock_coll.replace_one.side_effect = replace_responses

    # After the second replace_one, find_one will be called again for rollback doc1 read-back
    # We extend find_one to also return doc1 correctly for rollback verification
    doc1 = {"id": "doc1", "tenant_id": "t1", "provider": "p1", "property_id": "prop1", "encrypted_payload": "old_payload"}
    mock_coll.find_one.side_effect = [
        # migration verify
        {"id": "doc1", "tenant_id": "t1", "provider": "p1", "property_id": "prop1", "encrypted_payload": "right_payload"},
        {"id": "doc2", "tenant_id": "t1", "provider": "p1", "property_id": "prop1", "encrypted_payload": "wrong_payload"},
        # rollback verify for doc1 (after doc2 rollback fails)
        doc1,
    ]

    mock_svc = MagicMock()

    def fake_decrypt_dict(payload, aad):
        if payload == "wrong_payload":
            return "mismatch"
        return {"decrypted": True}

    mock_svc.decrypt_dict.side_effect = fake_decrypt_dict
    mock_svc.encrypt_dict.return_value = "new_payload"

    records = [
        {"collection": "provider_secrets", "doc": {"_id": "doc1", "tenant_id": "t1", "provider": "p1", "property_id": "prop1", "encrypted_payload": {"k": "v1"}}},
        {"collection": "provider_secrets", "doc": {"_id": "doc2", "tenant_id": "t1", "provider": "p1", "property_id": "prop1", "encrypted_payload": {"k": "v2"}}},
    ]

    with pytest.raises(RuntimeError, match="Aborting migration due to critical error"):
        await execute_migration(mock_db, mock_svc, records, dry_run=False)

    # Both rollback replace_one calls must have happened
    assert mock_coll.replace_one.call_count == 2

    # doc2 rollback was first (in the rollback list)
    first_rb_filter = mock_coll.replace_one.call_args_list[0][0][0]
    assert first_rb_filter["_id"] == "doc2"

    # doc1 rollback was second
    second_rb_filter = mock_coll.replace_one.call_args_list[1][0][0]
    assert second_rb_filter["_id"] == "doc1"
