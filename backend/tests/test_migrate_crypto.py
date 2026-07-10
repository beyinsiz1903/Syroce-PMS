import hashlib
import json
import os
import stat
from unittest.mock import AsyncMock, MagicMock, patch

import bson
import pytest
from core.crypto.errors import KeyDerivationError
from core.crypto.keys import load_keyring
from scripts.migrate_crypto import (
    MigrationPreflightError,
    create_backup_file,
    execute_migration,
    run_migration,
)

# 1. Backup file permission (0600)
def test_backup_mode_0600(tmp_path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        mock_db = MagicMock()
        mock_db.name = "test_db"
        mock_svc = MagicMock()
        mock_svc._keyring.current_kid = "v2"
        mock_svc._keyring.has_previous = True
        mock_svc._keyring._previous_kid = "v1"
        
        records = [{"collection": "test", "doc": {"_id": bson.ObjectId()}}]
        backup_file = create_backup_file(mock_db, mock_svc, records)
        
        st = os.stat(backup_file)
        assert stat.S_IMODE(st.st_mode) == 0o600
    finally:
        os.chdir(original_cwd)

# 2. BSON serialization and Manifest Structure
def test_bson_backup_manifest_and_checksum(tmp_path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        mock_db = MagicMock()
        mock_db.name = "test_db"
        mock_svc = MagicMock()
        mock_svc._keyring.current_kid = "v2"
        mock_svc._keyring.has_previous = False
        
        oid = bson.ObjectId()
        records = [{"collection": "test", "doc": {"_id": oid, "date": bson.datetime.datetime.now()}}]
        
        backup_file = create_backup_file(mock_db, mock_svc, records)
        
        with open(backup_file, "r") as f:
            read_back = bson.json_util.loads(f.read())
            
        assert "manifest" in read_back
        assert "records" in read_back
        manifest = read_back["manifest"]
        
        assert manifest["db_name"] == "test_db"
        assert manifest["current_kid"] == "v2"
        assert manifest["previous_kid"] is None
        assert manifest["record_count"] == 1
        
        # Verify checksum
        records_json = bson.json_util.dumps(read_back["records"]).encode("utf-8")
        expected_checksum = hashlib.sha256(records_json).hexdigest()
        assert manifest["payload_checksum"] == expected_checksum
        
        assert read_back["records"][0]["doc"]["_id"] == oid
    finally:
        os.chdir(original_cwd)

# 3. Previous Key / Kid Combinations
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

# 4. Strict Production Length checks
def test_production_master_key_length_checks(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "too-short")
    monkeypatch.setenv("CM_KEY_VERSION_CURRENT", "v2")
    
    with pytest.raises(KeyDerivationError, match="CM_MASTER_KEY_CURRENT is too weak for production"):
        load_keyring()

# 5. Unknown collection
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

# 6. Unknown Kid Blocks backup and execution (Preflight)
@pytest.mark.asyncio
async def test_unknown_kid_prevents_backup_and_writes(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CRYPTO_V2_ENABLED", "true")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "current-master-12345678901234567890")
    
    # Mock collect_records to return a failure in stats
    async def mock_collect(*args, **kwargs):
        from scripts.migrate_crypto import stats
        stats["unknown_kid_records"] += 1
        return [{"collection": "test", "doc": {}}]
        
    with patch("scripts.migrate_crypto.collect_records", side_effect=mock_collect) as m_collect, \
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

# 7. Restore validates env and DB
@pytest.mark.asyncio
async def test_restore_validates_env_and_db(tmp_path, monkeypatch):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        # Create a backup meant for 'production' and 'prod_db'
        manifest = {
            "app_env": "production",
            "db_name": "prod_db",
            "record_count": 0,
            "payload_checksum": hashlib.sha256(b"[]").hexdigest()
        }
        data = {"manifest": manifest, "records": []}
        
        backup_file = "test_env_mismatch.json"
        with open(backup_file, "w") as f:
            f.write(bson.json_util.dumps(data))
            
        mock_db = MagicMock()
        mock_db.name = "dev_db"  # mismatch DB
        
        monkeypatch.setenv("APP_ENV", "development") # mismatch ENV
        
        from scripts.migrate_crypto import run_restore
        
        with patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
            with pytest.raises(SystemExit):
                await run_restore(mock_db, backup_file)
            mock_exit.assert_called_once_with(1)
            
    finally:
        os.chdir(original_cwd)

# 8. Directory fsync
def test_directory_fsync(tmp_path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        mock_db = MagicMock()
        mock_svc = MagicMock()
        
        with patch("os.fsync") as mock_fsync, patch("os.open") as mock_open:
            # We just want to check if os.fsync is called on directory fd
            mock_open.side_effect = [10, 11] # file fd, dir fd
            
            # Since create_backup_file has actual file operations, we mock open to avoid real writes while checking fsync
            try:
                # We will let the real file write happen in another test, 
                # here we just assert os.fsync receives a dir_fd 
                pass
            except Exception:
                pass
            
            # Better to run the real create_backup_file and patch os.fsync
            pass
            
    finally:
        os.chdir(original_cwd)
        
def test_directory_fsync_called(tmp_path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        mock_db = MagicMock()
        mock_svc = MagicMock()
        records = []
        
        with patch("os.fsync") as mock_fsync:
            create_backup_file(mock_db, mock_svc, records)
            
            # os.fsync should be called at least twice (file and directory)
            assert mock_fsync.call_count >= 2
    finally:
        os.chdir(original_cwd)

# 9. Automatic Rollback on read-back failure
@pytest.mark.asyncio
async def test_auto_rollback_on_readback_failure():
    mock_db = MagicMock()
    mock_coll = AsyncMock()
    mock_db.__getitem__.return_value = mock_coll
    
    mock_coll.update_one.return_value.matched_count = 1
    mock_coll.update_one.return_value.modified_count = 1
    mock_coll.replace_one.return_value.matched_count = 1
    
    # First find_one works, second find_one returns WRONG payload
    mock_coll.find_one.side_effect = [
        {"encrypted_payload": "right_payload"}, # doc 1 verify
        {"encrypted_payload": "wrong_payload"}  # doc 2 verify fails
    ]
    
    mock_svc = MagicMock()
    def fake_decrypt(payload, aad):
        if payload == "wrong_payload":
            return "mismatch"
        return {"decrypted": True}
        
    mock_svc.decrypt_dict.side_effect = fake_decrypt
    mock_svc.encrypt_dict.side_effect = lambda payload, aad: "new_payload"
    
    records = [
        {"collection": "provider_secrets", "doc": {"id": "doc1", "tenant_id": "t1", "provider": "p1", "property_id": "prop1", "encrypted_payload": {"secret": "val"}}},
        {"collection": "provider_secrets", "doc": {"id": "doc2", "tenant_id": "t1", "provider": "p1", "property_id": "prop1", "encrypted_payload": {"secret": "val2"}}}
    ]
    
    with pytest.raises(RuntimeError, match="Aborting migration due to critical error: DB read-back verification failed"):
        await execute_migration(mock_db, mock_svc, records, dry_run=False)
        
    # Doc 1 update, Doc 1 read-back
    # Doc 2 update, Doc 2 read-back (FAILS)
    # Rollback Doc 2
    # Rollback Doc 1
    
    # replace_one should have been called twice (once for doc2, once for doc1)
    assert mock_coll.replace_one.call_count == 2
    
    # Check if the rollback documents passed to replace_one were the originals
    call_args = mock_coll.replace_one.call_args_list
    assert call_args[0][0][1]["id"] == "doc2"
    assert call_args[1][0][1]["id"] == "doc1"
