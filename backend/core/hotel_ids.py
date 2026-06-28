"""Shared utility for allocating unique 6-digit hotel_id values for tenants."""

import random

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase


async def generate_unique_hotel_id(db: AsyncIOMotorDatabase) -> str:
    """Generate a 6-digit unique hotel_id, retrying on collision."""
    for _ in range(50):
        cand = f"{random.randint(100000, 999999)}"
        if not await db.tenants.find_one({"hotel_id": cand}):
            return cand
    raise HTTPException(status_code=500, detail="Could not allocate hotel_id")
