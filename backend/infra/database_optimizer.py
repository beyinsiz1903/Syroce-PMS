"""
Database Optimization & Index Management
Ensures all collections have proper indexes for performance
"""
import logging
from datetime import datetime

from pymongo import ASCENDING, DESCENDING, TEXT
from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)


def _log_index_error(coll_name: str, e: Exception) -> None:
    """Log index creation errors. Treats IndexOptionsConflict (code 85) as
    cosmetic — it just means an index with the same key spec already exists
    under a different name and is safe to ignore."""
    if isinstance(e, OperationFailure) and getattr(e, "code", None) == 85:
        logger.debug(
            "Index for %s already exists with a different name (cosmetic, skipping): %s",
            coll_name, e,
        )
    else:
        logger.warning("Index creation warning for %s: %s", coll_name, e)


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

            # Tenant-prefixed compound indexes (most important for multi-tenant query plans)
            results['tenant_compound'] = await self.create_tenant_compound_indexes()

            logger.info(f"✅ All indexes created successfully: {results}")
            return results

        except Exception as e:
            logger.error(f"❌ Failed to create indexes: {e}")
            return {"error": str(e)}

    async def create_tenant_compound_indexes(self):
        """Multi-tenant compound indexes (tenant_id always as the first key).
        Without these, every tenant-scoped query falls back to a less efficient plan.
        """
        # (collection_name, [(index_spec, options), ...])
        plan = [
            # bookings tenant_compound: TÜMÜ KALDIRILDI (Mayıs 2026, Atlas Advisor):
            #   • idx_b_tid_id        ↔ idx_booking_tenant_id (atomic_checkin_checkout.py, unique)
            #   • idx_b_tid_status    ⊂ idx_booking_status_checkin (perf_indexes.py: tid,status,check_in)
            #   • idx_b_tid_status_chkin EXACT-DUP idx_booking_status_checkin
            #   • idx_b_tid_room      ⊂ idx_booking_room_dates  (perf_indexes.py: tid,room_id,check_in,check_out)
            #   • idx_b_tid_guest     ⊂ idx_booking_guest_status (perf_indexes.py: tid,guest_id,status)
            #   • idx_b_tid_created   EXACT-DUP idx_booking_created (perf_indexes.py: tid,created_at:-1)
            # idx_b_tid_chkin/chkout zaten önceki turda kaldırılmıştı.
            # Drop'lar d_perf.py _redundant listesinde idempotent olarak çalışır.
            ('rooms', [
                ([('tenant_id', ASCENDING), ('id', ASCENDING)], {'name': 'idx_r_tid_id'}),
                ([('tenant_id', ASCENDING), ('status', ASCENDING)], {'name': 'idx_r_tid_status'}),
                ([('tenant_id', ASCENDING), ('room_number', ASCENDING)], {'name': 'idx_r_tid_num'}),
            ]),
            ('guests', [
                ([('tenant_id', ASCENDING), ('id', ASCENDING)], {'name': 'idx_g_tid_id'}),
                ([('tenant_id', ASCENDING), ('vip', ASCENDING)], {'name': 'idx_g_tid_vip'}),
            ]),
            # folios tenant_compound: KALDIRILDI (Mayıs 2026):
            #   • idx_f_tid_booking ↔ idx_folio_tenant_booking (atomic_checkin_checkout.py)
            #     ve idx_folios_tenant_booking (d_perf.py) — üçlü duplikasyon.
            #   • idx_f_tid_status ⊂ idx_folio_status_balance (perf_indexes.py: tid,status,balance)
            ('folio_charges', [
                ([('tenant_id', ASCENDING), ('booking_id', ASCENDING)], {'name': 'idx_fc_tid_booking'}),
                ([('tenant_id', ASCENDING), ('date', ASCENDING)], {'name': 'idx_fc_tid_date'}),
            ]),
            ('housekeeping_tasks', [
                # idx_hk_tid_status: KALDIRILDI ⊂ idx_hk_status_room (perf_indexes.py)
                # idx_hk_tid_done:   KALDIRILDI EXACT-DUP idx_hk_completed (perf_indexes.py)
                # idx_hk_tid_room kalıyor — perf_indexes'te {tid,room_id} prefix'li
                # bağımsız index yok (idx_hk_status_room'un prefix'i sadece tid+status).
                ([('tenant_id', ASCENDING), ('room_id', ASCENDING)], {'name': 'idx_hk_tid_room'}),
            ]),
            ('users', [
                ([('tenant_id', ASCENDING), ('email', ASCENDING)], {'name': 'idx_u_tid_email'}),
                ([('tenant_id', ASCENDING), ('role', ASCENDING)], {'name': 'idx_u_tid_role'}),
            ]),
            ('notifications', [
                ([('tenant_id', ASCENDING), ('created_at', DESCENDING)], {'name': 'idx_n_tid_created'}),
                ([('tenant_id', ASCENDING), ('user_id', ASCENDING), ('read', ASCENDING)], {'name': 'idx_n_tid_user_read'}),
                # Mayıs 2026 — p95 fix: GET /api/notifications/list 1.2-1.5s
                # sürüyordu (3 prod log'unda SLOW REQUEST). Sebep: visibility
                # filtresi target_roles üzerinde $or yapıyor ama sıralı index
                # yok → tenant scope'undaki tüm notification scan'leniyor +
                # ardından count_documents tekrar tarama yapıyor.
                # Bu multikey-friendly compound (tenant + target_roles array
                # eşleşme + created_at sort) hem find hem unread count yolunu
                # kapsar; her iki sorgu da aynı index prefix'inden yararlanır.
                ([('tenant_id', ASCENDING), ('target_roles', ASCENDING), ('created_at', DESCENDING)],
                 {'name': 'idx_n_tid_roles_created'}),
            ]),
            ('communication_logs', [
                ([('tenant_id', ASCENDING), ('booking_id', ASCENDING)], {'name': 'idx_cl_tid_booking'}),
            ]),
            ('booking_guests', [
                ([('tenant_id', ASCENDING), ('booking_id', ASCENDING)], {'name': 'idx_bg_tid_booking'}),
            ]),
            ('deposits', [
                ([('tenant_id', ASCENDING), ('booking_id', ASCENDING)], {'name': 'idx_dep_tid_booking'}),
            ]),
            ('room_notes', [
                ([('tenant_id', ASCENDING), ('room_id', ASCENDING), ('resolved', ASCENDING)], {'name': 'idx_rn_tid_room_resolved'}),
            ]),
        ]

        total = 0
        for coll_name, idx_list in plan:
            coll = self.db[coll_name]
            for spec, opts in idx_list:
                try:
                    await coll.create_index(spec, **opts)
                    total += 1
                except Exception as e:
                    _log_index_error(coll_name, e)

        return {"created": total}

    async def create_booking_indexes(self):
        """Bookings collection indexes.

        NOTE (Mayıs 2026): Eski tek alanlı ve tenant_id'siz bileşik index'ler
        Atlas Performance Advisor tarafından REDUNDANT olarak işaretlendi —
        hepsi tenant_id öncüllü modern bileşik index'lerin (perf_indexes.py /
        d_perf.py / atomic_booking.py) prefix'leri. Yazma maliyetini azaltmak
        için sadece tenant scope'u olmayan gerçekten benzersiz pattern'leri
        burada tutuyoruz; tenant'lı olanlar create_tenant_compound_indexes()
        ve perf_indexes.ensure_performance_indexes()'te yönetiliyor.
        """
        bookings = self.db.bookings

        indexes = [
            # Tek alanlı text index — tenant scope'a girmez, yine yararlı.
            ([("guest_name", TEXT)], {}),
        ]

        created = []
        for index_spec, options in indexes:
            try:
                result = await bookings.create_index(index_spec, **options)
                created.append(result)
            except Exception as e:
                _log_index_error("bookings", e)

        return {"created": len(created), "indexes": created}

    async def create_guest_indexes(self):
        """Guests collection indexes"""
        guests = self.db.guests

        # Drop legacy global unique email index if it exists (causes duplicate key error for empty emails)
        try:
            await guests.drop_index("email_1")
        except Exception:
            pass

        indexes = [
            ([("phone", ASCENDING)], {}),
            ([("id_number", ASCENDING)], {}),
            ([("tags", ASCENDING)], {}),
            ([("created_at", DESCENDING)], {}),
            ([("name", TEXT)], {}),
            # Partial unique: only enforce uniqueness for non-empty emails, per tenant
            ([("tenant_id", ASCENDING), ("email", ASCENDING)], {
                "unique": True,
                "name": "idx_guests_tenant_email_unique",
                "partialFilterExpression": {"email": {"$gt": ""}},
            }),
            # NOTE: MongoDB allows only ONE text index per collection.
            # "name" text index already covers text search needs.
        ]

        created = []
        for index_spec, options in indexes:
            try:
                result = await guests.create_index(index_spec, **options)
                created.append(result)
            except Exception as e:
                _log_index_error("guests", e)

        return {"created": len(created), "indexes": created}

    async def create_room_indexes(self):
        """Rooms collection indexes.

        NOTE (Mayıs 2026): `status_1` ve `status_1_room_type_1` Atlas
        tarafından `idx_rooms_tenant_status_type` (tenant_id, status,
        room_type) prefix'i olarak REDUNDANT işaretlendi. Listeden çıkarıldı.
        """
        rooms = self.db.rooms

        indexes = [
            ([("room_type", ASCENDING)], {}),
            ([("floor", ASCENDING)], {}),
        ]

        created = []
        for index_spec, options in indexes:
            try:
                result = await rooms.create_index(index_spec, **options)
                created.append(result)
            except Exception as e:
                _log_index_error("rooms", e)

        return {"created": len(created), "indexes": created}

    async def create_folio_indexes(self):
        """Folios collection indexes.

        NOTE (Mayıs 2026): Tek alanlı non-tenant index'ler (`booking_id_1`,
        `guest_id_1`, `status_1`, `created_at_-1`, `folio_type_1`,
        `booking_id_1_folio_type_1`) Atlas Performance Advisor tarafından
        REDUNDANT işaretlendi. Sebep:
          • Tüm folio sorguları tenant_id ile scope'lanır (`tenant_db.py`),
            tek-alanlı index'ler asla seçilmez.
          • Mevcut compound'lar zaten kapsıyor:
              idx_folio_booking_status (tid, booking_id, status)
              idx_folio_status_balance (tid, status, balance)
              idx_folio_type_status    (tid, folio_type, status)
              idx_folios_tenant_booking (d_perf.py)
              idx_folios_tenant_status_created (d_perf.py)
        Drop'lar d_perf.py _redundant listesinde idempotent çalışır.
        """
        folios = self.db.folios

        indexes: list = []  # Tüm tek-alanlı non-tenant index'ler kaldırıldı.

        created = []
        for index_spec, options in indexes:
            try:
                result = await folios.create_index(index_spec, **options)
                created.append(result)
            except Exception as e:
                _log_index_error("folios", e)

        return {"created": len(created), "indexes": created}

    async def create_user_indexes(self):
        """Users collection indexes.

        NOTE (Mayıs 2026): `tenant_id_1` Atlas tarafından `idx_u_tid_email`
        ve `idx_u_tid_role` prefix'i olarak REDUNDANT işaretlendi.
        Tek alanlı `email` unique zaten farklı tenantlar için çakışırdı —
        modern multi-tenant şema (tenant_id, email) compound'unu kullanıyor;
        burada bırakılmadı.
        """
        users = self.db.users

        indexes = [
            ([("role", ASCENDING)], {}),
            # E-posta tekilligi DB-zirhi (yaris durumu / orphan onleme).
            # E-posta sifreli saklanir; tekillik DETERMINISTIK blind-index
            # `_hash_email` (HMAC-SHA256, normalize edilmis) uzerinden saglanir
            # — sifreli `email` alani uzerinden DEGIL. partialFilterExpression
            # ile yalniz `_hash_email` (string) tasiyan dokumanlar kisitlanir;
            # boylece legacy/sifresiz (alan yok) satirlar `null` uzerinde
            # cakismaz. Global (login zaten global-by-email; app-katmani dup
            # kontrolu de global) — bu yuzden tenant_id'siz.
            ([("_hash_email", ASCENDING)], {
                "name": "uniq_users_hash_email",
                "unique": True,
                "partialFilterExpression": {"_hash_email": {"$type": "string"}},
            }),
        ]

        created = []
        for index_spec, options in indexes:
            try:
                result = await users.create_index(index_spec, **options)
                created.append(result)
            except Exception as e:
                _log_index_error("users", e)

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
                _log_index_error("tasks", e)

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
                _log_index_error("audit_logs", e)

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
                _log_index_error("reports", e)

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
                # maxTimeMS bounds server-side execution so a slow collStats aborts
                # on the server (frees the connection) instead of only being
                # abandoned client-side by an outer asyncio.wait_for.
                collection_stats = await self.db.command(
                    "collStats", collection_name, maxTimeMS=4000
                )
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
from fastapi import APIRouter, Depends

from modules.pms_core.role_permission_service import require_op  # v88 DW

db_optimizer_router = APIRouter(prefix="/api/db-optimizer", tags=["database-optimization"])

@db_optimizer_router.post("/indexes/create")
async def create_all_indexes(db, _perm=Depends(require_op("view_system_diagnostics"))):  # v88 DW
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
