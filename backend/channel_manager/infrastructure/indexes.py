"""
Channel Manager MongoDB Index Initialization.
Run once during application startup to create required indexes.
"""
import logging
from core.database import db

logger = logging.getLogger("channel_manager.infrastructure.indexes")


async def create_cm_indexes():
    """Create all required indexes for channel manager collections."""
    try:
        # Connector accounts
        await db.cm_connectors.create_index(
            [("tenant_id", 1), ("id", 1)], unique=True, name="cm_conn_tid_id"
        )
        await db.cm_connectors.create_index(
            [("tenant_id", 1), ("property_id", 1), ("provider", 1)],
            unique=True, name="cm_conn_tid_pid_provider"
        )
        await db.cm_connectors.create_index(
            [("tenant_id", 1), ("status", 1)], name="cm_conn_tid_status"
        )

        # Mappings
        await db.cm_mappings.create_index(
            [("tenant_id", 1), ("id", 1)], unique=True, name="cm_map_tid_id"
        )
        await db.cm_mappings.create_index(
            [("tenant_id", 1), ("connector_id", 1), ("entity_type", 1), ("status", 1)],
            name="cm_map_tid_cid_type_status"
        )
        await db.cm_mappings.create_index(
            [("tenant_id", 1), ("connector_id", 1), ("entity_type", 1), ("pms_entity_id", 1)],
            name="cm_map_tid_cid_type_pms"
        )
        await db.cm_mappings.create_index(
            [("tenant_id", 1), ("connector_id", 1), ("entity_type", 1), ("external_entity_id", 1)],
            name="cm_map_tid_cid_type_ext"
        )
        await db.cm_mappings.create_index(
            [("tenant_id", 1), ("connector_id", 1), ("validation_status", 1)],
            name="cm_map_tid_cid_valstatus"
        )

        # Sync jobs
        await db.cm_sync_jobs.create_index(
            [("tenant_id", 1), ("connector_id", 1), ("created_at", -1)],
            name="cm_job_tid_cid_created"
        )
        await db.cm_sync_jobs.create_index(
            [("id", 1)], unique=True, name="cm_job_id"
        )

        # Sync events
        await db.cm_sync_events.create_index(
            [("job_id", 1), ("status", 1)], name="cm_event_jobid_status"
        )
        await db.cm_sync_events.create_index(
            [("id", 1)], unique=True, name="cm_event_id"
        )

        # Import batches
        await db.cm_import_batches.create_index(
            [("tenant_id", 1), ("connector_id", 1), ("started_at", -1)],
            name="cm_batch_tid_cid_started"
        )
        await db.cm_import_batches.create_index(
            [("id", 1)], unique=True, name="cm_batch_id"
        )

        # Imported reservations
        await db.cm_imported_reservations.create_index(
            [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
            unique=True, name="cm_impres_tid_cid_extid"
        )
        await db.cm_imported_reservations.create_index(
            [("tenant_id", 1), ("import_status", 1)], name="cm_impres_tid_status"
        )
        await db.cm_imported_reservations.create_index(
            [("tenant_id", 1), ("connector_id", 1), ("payload_fingerprint", 1)],
            name="cm_impres_tid_cid_fingerprint"
        )
        await db.cm_imported_reservations.create_index(
            [("tenant_id", 1), ("ack_status", 1)], name="cm_impres_tid_ack"
        )
        await db.cm_imported_reservations.create_index(
            [("batch_id", 1)], name="cm_impres_batch"
        )
        await db.cm_imported_reservations.create_index(
            [("tenant_id", 1), ("review_reason_code", 1)],
            name="cm_impres_tid_review_reason"
        )

        # Reconciliation issues
        await db.cm_reconciliation_issues.create_index(
            [("tenant_id", 1), ("connector_id", 1), ("status", 1)],
            name="cm_recon_tid_cid_status"
        )
        await db.cm_reconciliation_issues.create_index(
            [("tenant_id", 1), ("severity", 1), ("created_at", -1)],
            name="cm_recon_tid_sev_created"
        )
        await db.cm_reconciliation_issues.create_index(
            [("tenant_id", 1), ("issue_type", 1), ("status", 1)],
            name="cm_recon_tid_type_status"
        )
        await db.cm_reconciliation_issues.create_index(
            [("id", 1)], unique=True, name="cm_recon_id"
        )

        # Integration audit log
        await db.cm_integration_audit.create_index(
            [("tenant_id", 1), ("created_at", -1)], name="cm_audit_tid_created"
        )
        await db.cm_integration_audit.create_index(
            [("tenant_id", 1), ("connector_id", 1), ("action", 1)],
            name="cm_audit_tid_cid_action"
        )

        logger.info("Channel Manager indexes created successfully")
    except Exception as e:
        logger.error("Failed to create CM indexes: %s", e)
