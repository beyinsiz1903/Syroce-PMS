import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017") # I don't have the prod URI, wait...
    # I can use core.tenant_db.get_system_db if I run this in the backend env.
