import pytest
from unittest.mock import patch, MagicMock

from core.database import get_motor_database
from domains.hr.router import _get_hr_docs_bucket
from motor.motor_asyncio import AsyncIOMotorDatabase


def test_get_motor_database_returns_correct_type():
    """Verify that get_motor_database returns the underlying AsyncIOMotorDatabase."""
    db_instance = get_motor_database()
    assert isinstance(db_instance, AsyncIOMotorDatabase), "get_motor_database should return an AsyncIOMotorDatabase instance"


@patch('domains.hr.router.AsyncIOMotorGridFSBucket')
def test_get_hr_docs_bucket_avoids_typeerror(mock_gridfs_bucket):
    """Verify that _get_hr_docs_bucket passes the correct type to AsyncIOMotorGridFSBucket."""
    # Since AsyncIOMotorGridFSBucket requires an AsyncIOMotorDatabase, passing a proxy
    # would normally raise TypeError. Here we ensure we pass what get_motor_database returns.
    
    bucket = _get_hr_docs_bucket()
    
    # Assert that the constructor was called with the actual Motor database object
    mock_gridfs_bucket.assert_called_once()
    args, kwargs = mock_gridfs_bucket.call_args
    passed_db = args[0]
    
    assert isinstance(passed_db, AsyncIOMotorDatabase), "AsyncIOMotorGridFSBucket should be initialized with AsyncIOMotorDatabase"
    assert kwargs.get("bucket_name") == "staff_docs"
