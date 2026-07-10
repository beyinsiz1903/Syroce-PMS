import json
import os
import stat
from unittest.mock import AsyncMock, MagicMock, patch

import bson
import pytest
from core.crypto.errors import KeyDerivationError
from core.crypto.keys import load_keyring
from scripts.migrate_crypto import (
    create_backup_file,
    execute_migration,
    run_migration,
)

# 1. Backup file permission (0600)
def test_backup_mode_0600(tmp_path):
    # Change working directory so backup is created in tmp_path
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        records = [{"collection": "test", "doc": {"_id": bson.ObjectId()}}]
        backup_file = create_backup_file(records)
        
        st = os.stat(backup_file)
        # Check permissions are exactly 0o600
        assert stat.S_IMODE(st.st_mode) == 0o600
    finally:
        os.chdir(original_cwd)

# 2. BSON serialization
def test_bson_backup_serialization(tmp_path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        oid = bson.ObjectId()
        records = [{"collection": "test", "doc": {"_id": oid, "date": bson.datetime.datetime.now()}}]
        
        backup_file = create_backup_file(records)
        
        with open(backup_file, "r") as f:
            read_back = bson.json_util.loads(f.read())
            
        assert read_back[0]["doc"]["_id"] == oid
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

# 4. Unknown collection
@pytest.mark.asyncio
async def test_unknown_collection_fails(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CRYPTO_V2_ENABLED", "true")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "current-master")
    
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

# 5. Backup failure prevents all writes
@pytest.mark.asyncio
async def test_backup_failure_prevents_all_writes(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CRYPTO_V2_ENABLED", "true")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "current-master")
    
    with patch("scripts.migrate_crypto.collect_records", return_value=[{"collection": "test", "doc": {}}]) as mock_collect, \
         patch("scripts.migrate_crypto.create_backup_file", side_effect=PermissionError("Mock backup fail")) as mock_backup, \
         patch("scripts.migrate_crypto.execute_migration") as mock_execute, \
         patch("sys.exit", side_effect=SystemExit(1)):
        
        class Args:
            restore_backup = None
            force_v2 = False
            all = True
            collection = None
            dry_run = False
    
        with pytest.raises(SystemExit):
            await run_migration(Args())
            
        mock_backup.assert_called_once()
        mock_execute.assert_not_called()

# 6. Backup created before first write
@pytest.mark.asyncio
async def test_backup_created_before_first_write(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CRYPTO_V2_ENABLED", "true")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "current-master")
    
    # Create an ordered list to track call order
    call_order = []
    
    def fake_create_backup(*args, **kwargs):
        call_order.append("backup")
        return "backup.json"
        
    async def fake_execute(*args, **kwargs):
        call_order.append("execute")

    with patch("scripts.migrate_crypto.collect_records", return_value=[{"collection": "test", "doc": {}}]), \
         patch("scripts.migrate_crypto.create_backup_file", side_effect=fake_create_backup), \
         patch("scripts.migrate_crypto.execute_migration", side_effect=fake_execute):
         
        class Args:
            restore_backup = None
            force_v2 = False
            all = True
            collection = None
            dry_run = False
    
        await run_migration(Args())
        
        # Backup must happen before execution
        assert call_order == ["backup", "execute"]

# 7. DB Read-back verification
@pytest.mark.asyncio
async def test_db_readback_verification():
    # Test that execute_migration calls find_one after update_one and verifies
    mock_db = MagicMock()
    mock_coll = AsyncMock()
    mock_db.__getitem__.return_value = mock_coll
    
    mock_coll.update_one.return_value.matched_count = 1
    mock_coll.update_one.return_value.modified_count = 1
    
    # Mock find_one to return the WRONG payload to trigger verification failure
    mock_coll.find_one.return_value = {"encrypted_payload": "wrong_payload"}
    
    mock_svc = MagicMock()
    
    # For verification, decrypt_dict will receive 'wrong_payload' from find_one
    # We make it return something else
    def fake_decrypt(payload, aad):
        if payload == "wrong_payload":
            return {"decrypted": False}  # Mismatch
        return {"decrypted": True}
        
    mock_svc.decrypt_dict.side_effect = fake_decrypt
    mock_svc.encrypt_dict.side_effect = lambda payload, aad: "right_payload"
    
    records = [
        {"collection": "provider_secrets", "doc": {"id": "1", "encrypted_payload": {"secret": "val"}}}
    ]
    
    with pytest.raises(RuntimeError, match="Aborting migration due to critical error on provider_secrets: DB read-back verification failed"):
        await execute_migration(mock_db, mock_svc, records, dry_run=False)
        
    # Verify update_one and find_one were called
    mock_coll.update_one.assert_called_once()
    mock_coll.find_one.assert_called_once()

# 8. Partial failure restores or rolls back (Testing restore mechanics)
@pytest.mark.asyncio
async def test_partial_failure_restores_or_rolls_back(tmp_path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        # Create a mock backup JSON
        doc_data = {"id": "1", "tenant_id": "t1", "provider": "p1", "property_id": "prop1", "val": "old"}
        records = [{"collection": "provider_secrets", "doc": doc_data}]
        
        backup_file = "test_restore.json"
        with open(backup_file, "w") as f:
            f.write(bson.json_util.dumps(records))
            
        mock_db = MagicMock()
        mock_coll = AsyncMock()
        mock_db.__getitem__.return_value = mock_coll
        
        from scripts.migrate_crypto import run_restore
        await run_restore(mock_db, backup_file)
        
        # Expect replace_one to be called with correct filter and doc
        mock_coll.replace_one.assert_called_once_with(
            {"id": "1", "tenant_id": "t1", "provider": "p1", "property_id": "prop1"},
            doc_data
        )
    finally:
        os.chdir(original_cwd)
