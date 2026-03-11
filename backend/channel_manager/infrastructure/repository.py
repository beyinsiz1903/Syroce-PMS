"""
Channel Manager Repository - MongoDB persistence for all channel manager entities.
Centralized data access layer with tenant isolation enforced at every query.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from core.database import db

logger = logging.getLogger("channel_manager.repository")

# Collection names
CONNECTORS = "cm_connectors"
EXTERNAL_PROPERTIES = "cm_external_properties"
EXTERNAL_ROOM_TYPES = "cm_external_room_types"
EXTERNAL_RATE_PLANS = "cm_external_rate_plans"
MAPPINGS = "cm_mappings"
SYNC_JOBS = "cm_sync_jobs"
SYNC_EVENTS = "cm_sync_events"
PUSH_RECEIPTS = "cm_push_receipts"
CHANGE_RECORDS = "cm_change_records"
SYNC_SNAPSHOTS = "cm_sync_snapshots"
IMPORT_BATCHES = "cm_import_batches"
IMPORTED_RESERVATIONS = "cm_imported_reservations"
RECONCILIATION_ISSUES = "cm_reconciliation_issues"
INTEGRATION_AUDIT = "cm_integration_audit"

_NO_ID = {"_id": 0}


class ChannelManagerRepository:
    """MongoDB repository with tenant-scoped queries for all CM entities."""

    # ─── Connector Account ─────────────────────────────────────────────

    async def get_connector(self, tenant_id: str, connector_id: str) -> Optional[Dict]:
        return await db[CONNECTORS].find_one(
            {"tenant_id": tenant_id, "id": connector_id}, _NO_ID,
        )

    async def get_connectors_by_tenant(self, tenant_id: str, status: Optional[str] = None) -> List[Dict]:
        q = {"tenant_id": tenant_id}
        if status:
            q["status"] = status
        return await db[CONNECTORS].find(q, _NO_ID).to_list(100)

    async def get_active_connectors(self, tenant_id: str, property_id: str) -> List[Dict]:
        return await db[CONNECTORS].find(
            {"tenant_id": tenant_id, "property_id": property_id, "status": "active"}, _NO_ID,
        ).to_list(10)

    async def upsert_connector(self, doc: Dict) -> None:
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db[CONNECTORS].replace_one(
            {"tenant_id": doc["tenant_id"], "id": doc["id"]},
            doc, upsert=True,
        )

    async def delete_connector(self, tenant_id: str, connector_id: str) -> bool:
        r = await db[CONNECTORS].delete_one({"tenant_id": tenant_id, "id": connector_id})
        return r.deleted_count > 0

    # ─── Mapping Rules ─────────────────────────────────────────────────

    async def get_mappings(self, tenant_id: str, connector_id: str, entity_type: Optional[str] = None) -> List[Dict]:
        q: Dict[str, Any] = {"tenant_id": tenant_id, "connector_id": connector_id}
        if entity_type:
            q["entity_type"] = entity_type
        return await db[MAPPINGS].find(q, _NO_ID).to_list(500)

    async def get_active_mappings(self, tenant_id: str, connector_id: str, entity_type: str) -> List[Dict]:
        return await db[MAPPINGS].find(
            {"tenant_id": tenant_id, "connector_id": connector_id, "entity_type": entity_type, "status": "active"},
            _NO_ID,
        ).to_list(500)

    async def get_mapping(self, tenant_id: str, mapping_id: str) -> Optional[Dict]:
        return await db[MAPPINGS].find_one({"tenant_id": tenant_id, "id": mapping_id}, _NO_ID)

    async def upsert_mapping(self, doc: Dict) -> None:
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db[MAPPINGS].replace_one(
            {"tenant_id": doc["tenant_id"], "id": doc["id"]},
            doc, upsert=True,
        )

    async def delete_mapping(self, tenant_id: str, mapping_id: str) -> bool:
        r = await db[MAPPINGS].delete_one({"tenant_id": tenant_id, "id": mapping_id})
        return r.deleted_count > 0

    async def find_duplicate_mappings(
        self, tenant_id: str, connector_id: str, entity_type: str,
        pms_entity_id: str, external_entity_id: str,
        exclude_mapping_id: Optional[str] = None,
    ) -> List[Dict]:
        q: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "entity_type": entity_type,
            "$or": [
                {"pms_entity_id": pms_entity_id},
                {"external_entity_id": external_entity_id},
            ],
        }
        if exclude_mapping_id:
            q["id"] = {"$ne": exclude_mapping_id}
        return await db[MAPPINGS].find(q, _NO_ID).to_list(50)

    async def count_mappings_by_type(
        self, tenant_id: str, connector_id: str,
    ) -> Dict[str, Dict[str, int]]:
        pipeline = [
            {"$match": {"tenant_id": tenant_id, "connector_id": connector_id}},
            {"$group": {
                "_id": {"entity_type": "$entity_type", "status": "$status"},
                "count": {"$sum": 1},
            }},
        ]
        result: Dict[str, Dict[str, int]] = {}
        async for doc in db[MAPPINGS].aggregate(pipeline):
            et = doc["_id"]["entity_type"]
            st = doc["_id"]["status"]
            if et not in result:
                result[et] = {}
            result[et][st] = doc["count"]
        return result

    async def get_mappings_by_validation_status(
        self, tenant_id: str, connector_id: str, validation_status: str,
    ) -> List[Dict]:
        return await db[MAPPINGS].find(
            {"tenant_id": tenant_id, "connector_id": connector_id, "validation_status": validation_status},
            _NO_ID,
        ).to_list(500)

    async def bulk_update_mapping_validation(
        self, tenant_id: str, mapping_ids: List[str], updates: Dict,
    ) -> None:
        if mapping_ids:
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            await db[MAPPINGS].update_many(
                {"tenant_id": tenant_id, "id": {"$in": mapping_ids}},
                {"$set": updates},
            )

    # ─── Sync Jobs ─────────────────────────────────────────────────────

    async def create_sync_job(self, doc: Dict) -> None:
        await db[SYNC_JOBS].insert_one(doc)

    async def update_sync_job(self, job_id: str, updates: Dict) -> None:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db[SYNC_JOBS].update_one({"id": job_id}, {"$set": updates})

    async def get_sync_jobs(self, tenant_id: str, connector_id: Optional[str] = None, limit: int = 50) -> List[Dict]:
        q: Dict[str, Any] = {"tenant_id": tenant_id}
        if connector_id:
            q["connector_id"] = connector_id
        return await db[SYNC_JOBS].find(q, _NO_ID).sort("created_at", -1).to_list(limit)

    async def get_sync_job(self, job_id: str) -> Optional[Dict]:
        return await db[SYNC_JOBS].find_one({"id": job_id}, _NO_ID)

    # ─── Sync Events ───────────────────────────────────────────────────

    async def create_sync_event(self, doc: Dict) -> None:
        await db[SYNC_EVENTS].insert_one(doc)

    async def create_sync_events_batch(self, docs: List[Dict]) -> None:
        if docs:
            await db[SYNC_EVENTS].insert_many(docs)

    async def update_sync_event(self, event_id: str, updates: Dict) -> None:
        await db[SYNC_EVENTS].update_one({"id": event_id}, {"$set": updates})

    async def get_sync_events(self, job_id: str, limit: int = 200) -> List[Dict]:
        return await db[SYNC_EVENTS].find({"job_id": job_id}, _NO_ID).to_list(limit)

    async def get_sync_events_by_status(self, job_id: str, status: str) -> List[Dict]:
        return await db[SYNC_EVENTS].find({"job_id": job_id, "status": status}, _NO_ID).to_list(500)

    async def update_sync_events_batch(self, event_ids: List[str], updates: Dict) -> None:
        if event_ids:
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            await db[SYNC_EVENTS].update_many({"id": {"$in": event_ids}}, {"$set": updates})

    # ─── Change Records ─────────────────────────────────────────────────

    async def create_change_records(self, docs: List[Dict]) -> None:
        if docs:
            await db[CHANGE_RECORDS].insert_many(docs)

    async def get_pending_changes(self, tenant_id: str, connector_id: str, limit: int = 1000) -> List[Dict]:
        return await db[CHANGE_RECORDS].find(
            {"tenant_id": tenant_id, "connector_id": connector_id, "is_coalesced": False},
            _NO_ID,
        ).sort("created_at", 1).to_list(limit)

    async def mark_changes_coalesced(self, change_ids: List[str], event_id: str) -> None:
        if change_ids:
            await db[CHANGE_RECORDS].update_many(
                {"id": {"$in": change_ids}},
                {"$set": {"is_coalesced": True, "coalesced_into": event_id}},
            )

    # ─── Sync Snapshots (last synced state for delta detection) ─────────

    async def get_sync_snapshot(self, tenant_id: str, connector_id: str, room_type_id: str, date: str) -> Optional[Dict]:
        return await db[SYNC_SNAPSHOTS].find_one(
            {"tenant_id": tenant_id, "connector_id": connector_id, "room_type_id": room_type_id, "date": date},
            _NO_ID,
        )

    async def upsert_sync_snapshot(self, doc: Dict) -> None:
        await db[SYNC_SNAPSHOTS].replace_one(
            {"tenant_id": doc["tenant_id"], "connector_id": doc["connector_id"],
             "room_type_id": doc["room_type_id"], "date": doc["date"]},
            doc, upsert=True,
        )

    async def upsert_sync_snapshots_batch(self, docs: List[Dict]) -> None:
        for doc in docs:
            await self.upsert_sync_snapshot(doc)

    # ─── Manual Review Queue ────────────────────────────────────────────

    async def get_manual_review_jobs(self, tenant_id: str, connector_id: Optional[str] = None, limit: int = 50) -> List[Dict]:
        q: Dict[str, Any] = {"tenant_id": tenant_id, "status": "manual_review"}
        if connector_id:
            q["connector_id"] = connector_id
        return await db[SYNC_JOBS].find(q, _NO_ID).sort("created_at", -1).to_list(limit)

    async def get_failed_events_for_job(self, job_id: str) -> List[Dict]:
        return await db[SYNC_EVENTS].find(
            {"job_id": job_id, "status": {"$in": ["failed", "manual_review"]}}, _NO_ID,
        ).to_list(200)

    # ─── Push Receipts ─────────────────────────────────────────────────

    async def create_push_receipt(self, doc: Dict) -> None:
        await db[PUSH_RECEIPTS].insert_one(doc)

    # ─── Import Batches ────────────────────────────────────────────────

    async def create_import_batch(self, doc: Dict) -> None:
        await db[IMPORT_BATCHES].insert_one(doc)

    async def update_import_batch(self, batch_id: str, updates: Dict) -> None:
        await db[IMPORT_BATCHES].update_one({"id": batch_id}, {"$set": updates})

    async def get_import_batches(self, tenant_id: str, connector_id: Optional[str] = None, limit: int = 50) -> List[Dict]:
        q: Dict[str, Any] = {"tenant_id": tenant_id}
        if connector_id:
            q["connector_id"] = connector_id
        return await db[IMPORT_BATCHES].find(q, _NO_ID).sort("started_at", -1).to_list(limit)

    # ─── Imported Reservations ─────────────────────────────────────────

    async def upsert_imported_reservation(self, doc: Dict) -> None:
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db[IMPORTED_RESERVATIONS].replace_one(
            {"tenant_id": doc["tenant_id"], "connector_id": doc["connector_id"], "external_reservation_id": doc["external_reservation_id"]},
            doc, upsert=True,
        )

    async def update_imported_reservation(self, tenant_id: str, reservation_id: str, updates: Dict) -> None:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db[IMPORTED_RESERVATIONS].update_one(
            {"tenant_id": tenant_id, "id": reservation_id}, {"$set": updates},
        )

    async def get_imported_reservation_by_id(self, tenant_id: str, reservation_id: str) -> Optional[Dict]:
        return await db[IMPORTED_RESERVATIONS].find_one(
            {"tenant_id": tenant_id, "id": reservation_id}, _NO_ID,
        )

    async def get_imported_reservation_by_external_id(self, tenant_id: str, connector_id: str, external_id: str) -> Optional[Dict]:
        return await db[IMPORTED_RESERVATIONS].find_one(
            {"tenant_id": tenant_id, "connector_id": connector_id, "external_reservation_id": external_id}, _NO_ID,
        )

    async def get_imported_reservations(
        self, tenant_id: str, connector_id: Optional[str] = None,
        status: Optional[str] = None, limit: int = 100,
    ) -> List[Dict]:
        q: Dict[str, Any] = {"tenant_id": tenant_id}
        if connector_id:
            q["connector_id"] = connector_id
        if status:
            q["import_status"] = status
        return await db[IMPORTED_RESERVATIONS].find(q, _NO_ID).sort("created_at", -1).to_list(limit)

    async def get_reservation_review_queue(
        self, tenant_id: str, connector_id: Optional[str] = None, limit: int = 100,
    ) -> List[Dict]:
        q: Dict[str, Any] = {"tenant_id": tenant_id, "import_status": {"$in": ["review", "conflict", "out_of_order"]}}
        if connector_id:
            q["connector_id"] = connector_id
        return await db[IMPORTED_RESERVATIONS].find(q, _NO_ID).sort("created_at", -1).to_list(limit)

    async def get_imported_reservations_by_batch(self, batch_id: str, limit: int = 500) -> List[Dict]:
        return await db[IMPORTED_RESERVATIONS].find(
            {"batch_id": batch_id}, _NO_ID,
        ).sort("created_at", -1).to_list(limit)

    async def count_imported_reservations(self, tenant_id: str, connector_id: str, status: Optional[str] = None) -> int:
        q: Dict[str, Any] = {"tenant_id": tenant_id, "connector_id": connector_id}
        if status:
            q["import_status"] = status
        return await db[IMPORTED_RESERVATIONS].count_documents(q)

    async def get_import_batch_by_id(self, tenant_id: str, batch_id: str) -> Optional[Dict]:
        return await db[IMPORT_BATCHES].find_one(
            {"tenant_id": tenant_id, "id": batch_id}, _NO_ID,
        )

    # ─── Reconciliation Issues ─────────────────────────────────────────

    async def create_reconciliation_issue(self, doc: Dict) -> None:
        await db[RECONCILIATION_ISSUES].insert_one(doc)

    async def get_reconciliation_issues(
        self, tenant_id: str, connector_id: Optional[str] = None,
        status: str = "open", limit: int = 100,
    ) -> List[Dict]:
        q: Dict[str, Any] = {"tenant_id": tenant_id, "status": status}
        if connector_id:
            q["connector_id"] = connector_id
        return await db[RECONCILIATION_ISSUES].find(q, _NO_ID).sort("created_at", -1).to_list(limit)

    async def update_reconciliation_issue(self, issue_id: str, updates: Dict) -> None:
        await db[RECONCILIATION_ISSUES].update_one({"id": issue_id}, {"$set": updates})

    async def get_reconciliation_issue(self, tenant_id: str, issue_id: str) -> Optional[Dict]:
        return await db[RECONCILIATION_ISSUES].find_one(
            {"tenant_id": tenant_id, "id": issue_id}, _NO_ID,
        )

    async def get_reconciliation_summary(
        self, tenant_id: str, connector_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate issue counts by type and severity."""
        match = {"tenant_id": tenant_id, "status": {"$in": ["open", "investigating", "retrying"]}}
        if connector_id:
            match["connector_id"] = connector_id

        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": {"issue_type": "$issue_type", "severity": "$severity"},
                "count": {"$sum": 1},
            }},
        ]
        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        total = 0
        async for doc in db[RECONCILIATION_ISSUES].aggregate(pipeline):
            it = doc["_id"]["issue_type"]
            sev = doc["_id"]["severity"]
            cnt = doc["count"]
            by_type[it] = by_type.get(it, 0) + cnt
            by_severity[sev] = by_severity.get(sev, 0) + cnt
            total += cnt
        return {"total_open": total, "by_type": by_type, "by_severity": by_severity}

    # ─── Integration Audit Log ─────────────────────────────────────────

    async def create_audit_log(self, doc: Dict) -> None:
        await db[INTEGRATION_AUDIT].insert_one(doc)

    async def get_audit_logs(
        self, tenant_id: str, connector_id: Optional[str] = None, limit: int = 100,
    ) -> List[Dict]:
        q: Dict[str, Any] = {"tenant_id": tenant_id}
        if connector_id:
            q["connector_id"] = connector_id
        return await db[INTEGRATION_AUDIT].find(q, _NO_ID).sort("created_at", -1).to_list(limit)

    # ─── External Properties / Room Types / Rate Plans ─────────────────

    async def upsert_external_property(self, doc: Dict) -> None:
        await db[EXTERNAL_PROPERTIES].replace_one(
            {"tenant_id": doc["tenant_id"], "connector_id": doc["connector_id"], "external_id": doc["external_id"]},
            doc, upsert=True,
        )

    async def get_external_properties(self, tenant_id: str, connector_id: str) -> List[Dict]:
        return await db[EXTERNAL_PROPERTIES].find(
            {"tenant_id": tenant_id, "connector_id": connector_id}, _NO_ID,
        ).to_list(100)

    async def upsert_external_room_type(self, doc: Dict) -> None:
        await db[EXTERNAL_ROOM_TYPES].replace_one(
            {"tenant_id": doc["tenant_id"], "connector_id": doc["connector_id"], "external_id": doc["external_id"]},
            doc, upsert=True,
        )

    async def get_external_room_types(self, tenant_id: str, connector_id: str) -> List[Dict]:
        return await db[EXTERNAL_ROOM_TYPES].find(
            {"tenant_id": tenant_id, "connector_id": connector_id}, _NO_ID,
        ).to_list(500)

    async def upsert_external_rate_plan(self, doc: Dict) -> None:
        await db[EXTERNAL_RATE_PLANS].replace_one(
            {"tenant_id": doc["tenant_id"], "connector_id": doc["connector_id"], "external_id": doc["external_id"]},
            doc, upsert=True,
        )

    async def get_external_rate_plans(self, tenant_id: str, connector_id: str) -> List[Dict]:
        return await db[EXTERNAL_RATE_PLANS].find(
            {"tenant_id": tenant_id, "connector_id": connector_id}, _NO_ID,
        ).to_list(500)

    # ─── Observability Metrics ─────────────────────────────────────────

    async def get_sync_metrics(self, tenant_id: str, connector_id: str) -> Dict[str, Any]:
        """Aggregate sync metrics for dashboard display."""
        pipeline = [
            {"$match": {"tenant_id": tenant_id, "connector_id": connector_id}},
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1},
            }},
        ]
        job_stats = {}
        async for doc in db[SYNC_JOBS].aggregate(pipeline):
            job_stats[doc["_id"]] = doc["count"]

        event_pipeline = [
            {"$match": {"tenant_id": tenant_id, "connector_id": connector_id}},
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1},
            }},
        ]
        event_stats = {}
        async for doc in db[SYNC_EVENTS].aggregate(event_pipeline):
            event_stats[doc["_id"]] = doc["count"]

        issue_count = await db[RECONCILIATION_ISSUES].count_documents(
            {"tenant_id": tenant_id, "connector_id": connector_id, "status": "open"},
        )

        return {
            "sync_jobs": job_stats,
            "sync_events": event_stats,
            "open_issues": issue_count,
        }
