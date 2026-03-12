"""
Bootstrap: Dependency Container
Centralizes all shared dependencies (db, cache, auth, config) for the application.
server.py should only import from this module for shared state.
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

# ── Database ────────────────────────────────────────────────────────
_mongo_url = os.environ.get('MONGO_URL')
_db_name = os.environ.get('DB_NAME')

if not _mongo_url:
    raise RuntimeError("MONGO_URL environment variable is required")
if not _db_name:
    raise RuntimeError("DB_NAME environment variable is required")

mongo_client = AsyncIOMotorClient(
    _mongo_url,
    maxPoolSize=500,
    minPoolSize=50,
    maxIdleTimeMS=45000,
    serverSelectionTimeoutMS=3000,
    connectTimeoutMS=5000,
    socketTimeoutMS=20000,
    retryWrites=True,
    retryReads=True,
    maxConnecting=10,
)
db = mongo_client[_db_name]

# ── JWT Config ──────────────────────────────────────────────────────
JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    import secrets as _s
    JWT_SECRET = _s.token_urlsafe(64)
    print("⚠️  JWT_SECRET not set – using ephemeral secret")

JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 168  # 7 days


def get_db():
    """Return the database instance. Use this in routers via Depends or direct import."""
    return db
