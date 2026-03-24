"""
Database Optimization & Index Management
Ensures all collections have proper indexes for performance
"""
import logging
from datetime import datetime

from pymongo import ASCENDING, DESCENDING, TEXT

logger = logging.getLogger(__name__)

class DatabaseOptimizer:
    def __init__(self, db):
        self.db = db

    async def create_all_indexes(self):
        """Create all necessary indexes for optimal performance"""
        results = {}

        try:
            # Bookings Collection
            results['bookings'] = await self.create_booking_indexes()

            # Guests Collection
            results['guests'] = await self.create_guest_indexes()

            # Rooms Collection
            results['rooms'] = await self.create_room_indexes()

            # Folios Collection
            results['folios'] = await self.create_folio_indexes()

            # Users Collection
            results['users'] = await self.create_user_indexes()

            # Tasks/Housekeeping
            results['tasks'] = await self.create_task_indexes()

            # Audit Logs
            results['audit_logs'] = await self.create_audit_log_indexes()

            # Performance Reports
            results['reports'] = await self.create_report_indexes()

            logger.info(f"✅ All indexes created successfully: {results}")
            return results

        except Exception as e:
            logger.error(f"❌ Failed to create indexes: {e}")
            return {"error": str(e)}

    async def create_booking_indexes(self):
        """Bookings collection indexes"""
        bookings = self.db.bookings

        indexes = [
            # Single field indexes
            ([("guest_id", ASCENDING)], {}),
            ([("room_id", ASCENDING)], {}),
            ([("status", ASCENDING)], {}),
            ([("check_in", DESCENDING)], {}),
            ([("check_out", DESCENDING)], {}),
            ([("created_at", DESCENDING)], {}),
            ([("channel", ASCENDING)], {}),

            # Compound indexes for common queries
            ([("status", ASCENDING), ("check_in", DESCENDING)], {}),
            ([("status", ASCENDING), ("check_out", DESCENDING)], {}),
            ([("guest_id", ASCENDING), ("check_in", DESCENDING)], {}),
            ([("room_id", ASCENDING), ("check_in", DESCENDING)], {}),
            ([("check_in", ASCENDING), ("check_out", ASCENDING)], {}),

            # Date range queries
            ([("created_at", DESCENDING), ("status", ASCENDING)], {}),
            ([("check_in", DESCENDING), ("status", ASCENDING)], {}),

            # Text search
            ([("guest_name", TEXT)], {}),
        ]

        created = []
        for index_spec, options in indexes:
            try:
                result = await bookings.create_index(index_spec, **options)
                created.append(result)
            except Exception as e:
                logger.warning(f"Index creation warning for bookings: {e}")

        return {"created": len(created), "indexes": created}

    async def create_guest_indexes(self):
        """Guests collection indexes"""
        guests = self.db.guests

        indexes = [
            ([("email", ASCENDING)], {"unique": True}),
            ([("phone", ASCENDING)], {}),
            ([("id_number", ASCENDING)], {}),
            ([("tags", ASCENDING)], {}),
            ([("created_at", DESCENDING)], {}),
            ([("name", TEXT)], {}),
            # NOTE: MongoDB allows only ONE text index per collection.
            # "name" text index already covers text search needs.
            # Removed duplicate "email" TEXT index that caused IndexOptionsConflict.
        ]

        created = []
        for index_spec, options in indexes:
            try:
                result = await guests.create_index(index_spec, **options)
                created.append(result)
            except Exception as e:
                logger.warning(f"Index creation warning for guests: {e}")

        return {"created": len(created), "indexes": created}

    async def create_room_indexes(self):
        """Rooms collection indexes"""
        rooms = self.db.rooms

        indexes = [
            ([("room_number", ASCENDING)], {}),
            ([("status", ASCENDING)], {}),
            ([("room_type", ASCENDING)], {}),
            ([("floor", ASCENDING)], {}),
            ([("status", ASCENDING), ("room_type", ASCENDING)], {}),
        ]

        created = []
        for index_spec, options in indexes:
            try:
                result = await rooms.create_index(index_spec, **options)
                created.append(result)
            except Exception as e:
                logger.warning(f"Index creation warning for rooms: {e}")

        return {"created": len(created), "indexes": created}

    async def create_folio_indexes(self):
        """Folios collection indexes"""
        folios = self.db.folios

        indexes = [
            ([("booking_id", ASCENDING)], {}),
            ([("guest_id", ASCENDING)], {}),
            ([("status", ASCENDING)], {}),
            ([("created_at", DESCENDING)], {}),
            ([("folio_type", ASCENDING)], {}),
            ([("booking_id", ASCENDING), ("folio_type", ASCENDING)], {}),
        ]

        created = []
        for index_spec, options in indexes:
            try:
                result = await folios.create_index(index_spec, **options)
                created.append(result)
            except Exception as e:
                logger.warning(f"Index creation warning for folios: {e}")

        return {"created": len(created), "indexes": created}

    async def create_user_indexes(self):
        """Users collection indexes"""
        users = self.db.users

        indexes = [
            ([("email", ASCENDING)], {"unique": True}),
            ([("role", ASCENDING)], {}),
            ([("tenant_id", ASCENDING)], {}),
        ]

        created = []
        for index_spec, options in indexes:
            try:
                result = await users.create_index(index_spec, **options)
                created.append(result)
            except Exception as e:
                logger.warning(f"Index creation warning for users: {e}")

        return {"created": len(created), "indexes": created}

    async def create_task_indexes(self):
        """Tasks/Housekeeping collection indexes"""
        tasks = self.db.housekeeping_tasks

        indexes = [
            ([("room_id", ASCENDING)], {}),
            ([("status", ASCENDING)], {}),
            ([("assigned_to", ASCENDING)], {}),
            ([("created_at", DESCENDING)], {}),
            ([("task_type", ASCENDING)], {}),
            ([("status", ASCENDING), ("created_at", DESCENDING)], {}),
        ]

        created = []
        for index_spec, options in indexes:
            try:
                result = await tasks.create_index(index_spec, **options)
                created.append(result)
            except Exception as e:
                logger.warning(f"Index creation warning for tasks: {e}")

        return {"created": len(created), "indexes": created}

    async def create_audit_log_indexes(self):
        """Audit logs collection indexes"""
        audit_logs = self.db.audit_logs

        indexes = [
            ([("user_id", ASCENDING)], {}),
            ([("action", ASCENDING)], {}),
            ([("timestamp", DESCENDING)], {}),
            ([("resource_type", ASCENDING)], {}),
            ([("timestamp", DESCENDING), ("user_id", ASCENDING)], {}),
            # TTL index - auto-delete logs older than 90 days
            ([("timestamp", ASCENDING)], {"expireAfterSeconds": 90 * 24 * 60 * 60}),
        ]

        created = []
        for index_spec, options in indexes:
            try:
                result = await audit_logs.create_index(index_spec, **options)
                created.append(result)
            except Exception as e:
                logger.warning(f"Index creation warning for audit_logs: {e}")

        return {"created": len(created), "indexes": created}

    async def create_report_indexes(self):
        """Performance reports collection indexes"""
        reports = self.db.daily_performance_reports

        indexes = [
            ([("date", DESCENDING)], {"unique": True}),
            ([("generated_at", DESCENDING)], {}),
        ]

        created = []
        for index_spec, options in indexes:
            try:
                result = await reports.create_index(index_spec, **options)
                created.append(result)
            except Exception as e:
                logger.warning(f"Index creation warning for reports: {e}")

        return {"created": len(created), "indexes": created}

    async def verify_indexes(self):
        """Verify all indexes are in place"""
        collections = [
            'bookings', 'guests', 'rooms', 'folios',
            'users', 'housekeeping_tasks', 'audit_logs',
            'daily_performance_reports'
        ]

        results = {}

        for collection_name in collections:
            try:
                collection = self.db[collection_name]
                indexes = await collection.index_information()
                results[collection_name] = {
                    "count": len(indexes),
                    "indexes": list(indexes.keys())
                }
            except Exception as e:
                results[collection_name] = {"error": str(e)}

        return results

    async def analyze_query_performance(self):
        """Analyze slow queries and suggest optimizations"""
        # Enable profiling
        await self.db.command('profile', 2)  # Profile all operations

        # Get slow queries
        slow_queries = await self.db.system.profile.find({
            "millis": {"$gt": 100}  # Queries taking more than 100ms
        }).sort("millis", DESCENDING).limit(20).to_list(20)

        # Disable profiling
        await self.db.command('profile', 0)

        suggestions = []
        for query in slow_queries:
            suggestions.append({
                "operation": query.get("op"),
                "namespace": query.get("ns"),
                "duration_ms": query.get("millis"),
                "query": query.get("command", {}).get("filter", {}),
                "suggestion": "Consider adding index" if not query.get("planSummary") else "Existing index may need optimization"
            })

        return {
            "slow_queries_count": len(slow_queries),
            "suggestions": suggestions
        }

    async def get_collection_stats(self):
        """Get statistics for all collections"""
        collections = await self.db.list_collection_names()

        stats = {}

        for collection_name in collections:
            try:
                collection_stats = await self.db.command("collStats", collection_name)
                stats[collection_name] = {
                    "count": collection_stats.get("count", 0),
                    "size_mb": round(collection_stats.get("size", 0) / (1024 * 1024), 2),
                    "avg_obj_size": collection_stats.get("avgObjSize", 0),
                    "indexes": collection_stats.get("nindexes", 0),
                    "index_size_mb": round(collection_stats.get("totalIndexSize", 0) / (1024 * 1024), 2),
                }
            except Exception as e:
                stats[collection_name] = {"error": str(e)}

        return stats


# API endpoint for database optimization
from fastapi import APIRouter

db_optimizer_router = APIRouter(prefix="/api/db-optimizer", tags=["database-optimization"])

@db_optimizer_router.post("/indexes/create")
async def create_all_indexes(db):
    """Create all necessary database indexes"""
    optimizer = DatabaseOptimizer(db)
    result = await optimizer.create_all_indexes()
    return {
        "success": True,
        "results": result,
        "timestamp": datetime.utcnow().isoformat()
    }

@db_optimizer_router.get("/indexes/verify")
async def verify_indexes(db):
    """Verify all indexes are in place"""
    optimizer = DatabaseOptimizer(db)
    result = await optimizer.verify_indexes()
    return {
        "success": True,
        "indexes": result,
        "timestamp": datetime.utcnow().isoformat()
    }

@db_optimizer_router.get("/stats")
async def get_database_stats(db):
    """Get database statistics"""
    optimizer = DatabaseOptimizer(db)
    result = await optimizer.get_collection_stats()
    return {
        "success": True,
        "stats": result,
        "timestamp": datetime.utcnow().isoformat()
    }

@db_optimizer_router.get("/analyze")
async def analyze_performance(db):
    """Analyze query performance and suggest optimizations"""
    optimizer = DatabaseOptimizer(db)
    result = await optimizer.analyze_query_performance()
    return {
        "success": True,
        "analysis": result,
        "timestamp": datetime.utcnow().isoformat()
    }
