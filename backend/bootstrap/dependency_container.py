"""
Bootstrap: Dependency Container
Centralizes all shared dependencies (db, cache, auth, config) for the application.
Re-exports from core.database to provide a single canonical DB connection.
"""
from core.database import db, client as mongo_client, mongo_url, db_name
from core.security import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_HOURS


def get_db():
    """Return the database instance. Use this in routers via Depends or direct import."""
    return db
