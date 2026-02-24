"""
Syroce PMS - Database Connection
Centralized MongoDB connection management.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017/hotel_pms')
db_name = os.environ.get('DB_NAME', 'hotel_pms')

# Optimized connection pool for high concurrency (550 rooms, 300+ daily transactions)
client = AsyncIOMotorClient(
    mongo_url,
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

db = client[db_name]
