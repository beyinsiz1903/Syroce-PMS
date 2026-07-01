"""MongoDB connection + collection handles for Quick-ID."""
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "quick_id_reader")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

guests_col = db["guests"]
scans_col = db["scans"]
audit_col = db["audit_logs"]
users_col = db["users"]
