"""
Data Archival System
Archives old bookings (>1 year) to separate collection for performance
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from pymongo import ASCENDING, DESCENDING

logger = logging.getLogger(__name__)

class DataArchivalManager:
    def __init__(self, db):
        self.db = db
        self.bookings = db.bookings
        self.bookings_archive = db.bookings_archive
        self.archive_threshold_days = 365  # 1 year

    async def setup_indexes(self):
        """Setup indexes for archived collection"""
        try:
            # Archive collection indexes
            await self.bookings_archive.create_index([("archived_at", DESCENDING)])
            await self.bookings_archive.create_index([("check_in", DESCENDING)])
            await self.bookings_archive.create_index([("check_out", DESCENDING)])
            await self.bookings_archive.create_index([("guest_id", ASCENDING)])
            await self.bookings_archive.create_index([("status", ASCENDING)])
            await self.bookings_archive.create_index([
                ("guest_id", ASCENDING),
                ("check_in", DESCENDING)
            ])
            logger.info("Archive indexes created successfully")
        except Exception as e:
            logger.error(f"Failed to create archive indexes: {e}")

    async def archive_old_bookings(self, dry_run: bool = True) -> Dict[str, Any]:
        """
        Archive bookings older than threshold

        Args:
            dry_run: If True, only count records without moving them

        Returns:
            dict with archive statistics
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.archive_threshold_days)

            # Find old bookings
            query = {
                "check_out": {"$lt": cutoff_date},
                "status": {"$in": ["checked_out", "cancelled", "no_show"]}
            }

            # Count records to archive
            count = await self.bookings.count_documents(query)

            if dry_run:
                return {
                    "dry_run": True,
                    "records_to_archive": count,
                    "cutoff_date": cutoff_date.isoformat(),
                    "threshold_days": self.archive_threshold_days
                }

            # Archive in batches
            batch_size = 1000
            archived_count = 0

            cursor = self.bookings.find(query).limit(batch_size)
            async for booking in cursor:
                # Add archive metadata
                booking["archived_at"] = datetime.utcnow()
                booking["original_id"] = booking["_id"]

                # Insert to archive
                await self.bookings_archive.insert_one(booking)

                # Delete from main collection
                await self.bookings.delete_one({"_id": booking["_id"]})

                archived_count += 1

                if archived_count % 100 == 0:
                    logger.info(f"Archived {archived_count} bookings...")

            return {
                "dry_run": False,
                "records_archived": archived_count,
                "cutoff_date": cutoff_date.isoformat(),
                "threshold_days": self.archive_threshold_days,
                "success": True
            }

        except Exception as e:
            logger.error(f"Archival failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def query_with_archive(
        self,
        query: Dict[str, Any],
        limit: int = 100,
        skip: int = 0,
        include_archived: bool = False
    ) -> list:
        """
        Query bookings with optional archive inclusion

        Args:
            query: MongoDB query
            limit: Result limit
            skip: Skip records
            include_archived: Include archived records

        Returns:
            List of bookings
        """
        results = []

        # Query active bookings
        cursor = self.bookings.find(query).skip(skip).limit(limit)
        async for doc in cursor:
            results.append(doc)

        # If including archived and limit not reached
        if include_archived and len(results) < limit:
            remaining = limit - len(results)
            archive_cursor = self.bookings_archive.find(query).skip(max(0, skip - await self.bookings.count_documents(query))).limit(remaining)
            async for doc in archive_cursor:
                doc["from_archive"] = True
                results.append(doc)

        return results

    async def get_archive_stats(self) -> Dict[str, Any]:
        """Get archival statistics"""
        try:
            active_count = await self.bookings.count_documents({})
            archived_count = await self.bookings_archive.count_documents({})

            # Get oldest active booking
            oldest_active = await self.bookings.find_one(
                {},
                sort=[("check_in", ASCENDING)]
            )

            # Get newest archived booking
            newest_archived = await self.bookings_archive.find_one(
                {},
                sort=[("archived_at", DESCENDING)]
            )

            return {
                "active_bookings": active_count,
                "archived_bookings": archived_count,
                "total_bookings": active_count + archived_count,
                "archive_percentage": round((archived_count / (active_count + archived_count) * 100), 2) if (active_count + archived_count) > 0 else 0,
                "oldest_active_date": oldest_active.get("check_in") if oldest_active else None,
                "last_archived_at": newest_archived.get("archived_at") if newest_archived else None,
                "threshold_days": self.archive_threshold_days
            }
        except Exception as e:
            logger.error(f"Failed to get archive stats: {e}")
            return {"error": str(e)}
