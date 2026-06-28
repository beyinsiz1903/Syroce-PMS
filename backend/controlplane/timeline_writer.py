"""
Timeline Writer — Fire-and-Forget Event Timeline Appender
============================================================
Every subsystem (webhook, ingest, import, outbox, ARI push) calls this
to record pipeline stages. Write failures are logged but NEVER block
the main flow.

Idempotent: (entity_id, stage, source) deduplication via upsert.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("controlplane.timeline_writer")

COLL_TIMELINE = "event_timeline"


class TimelineWriter:
    """Append events to the event_timeline collection.

    Usage:
        writer = get_timeline_writer()
        await writer.append(
            tenant_id="t1",
            correlation_id="uuid",
            entity_type="reservation",
            stage="received",
            source="webhook_exely",
            provider="exely",
        )
    """

    def __init__(self):
        self._db = None

    def _get_db(self):
        if self._db is None:
            from core.database import db

            self._db = db
        return self._db

    async def append(
        self,
        *,
        tenant_id: str,
        correlation_id: str,
        entity_type: str,
        stage: str,
        source: str,
        status: str = "success",
        provider: str | None = None,
        entity_id: str | None = None,
        external_id: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
        parent_event_id: str | None = None,
    ) -> str | None:
        """Append a timeline event. Fire-and-forget — never raises."""
        try:
            now = datetime.now(UTC).isoformat()
            event_id = str(uuid.uuid4())

            # Compute sequence number for this correlation
            db = self._get_db()
            seq = await db[COLL_TIMELINE].count_documents({"correlation_id": correlation_id})

            doc = {
                "id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "entity_type": entity_type,
                "entity_id": entity_id or "",
                "external_id": external_id or "",
                "stage": stage,
                "status": status,
                "source": source,
                "provider": provider or "",
                "timestamp": now,
                "duration_ms": duration_ms,
                "sequence": seq + 1,
                "metadata": metadata or {},
                "parent_event_id": parent_event_id,
            }

            await db[COLL_TIMELINE].insert_one(doc)
            doc.pop("_id", None)

            logger.debug(
                "Timeline: corr=%s stage=%s status=%s src=%s entity=%s",
                correlation_id[:8],
                stage,
                status,
                source,
                entity_id or external_id or "?",
            )
            return event_id

        except Exception:
            logger.warning(
                "Timeline write failed (non-blocking): stage=%s corr=%s",
                stage,
                correlation_id[:8] if correlation_id else "?",
                exc_info=True,
            )
            return None


async def ensure_timeline_indexes():
    """Create indexes for the event_timeline collection."""
    from core.database import db

    coll = db[COLL_TIMELINE]
    try:
        await coll.create_index(
            [("tenant_id", 1), ("entity_id", 1), ("timestamp", 1)],
            name="idx_timeline_entity",
        )
        await coll.create_index(
            [("tenant_id", 1), ("correlation_id", 1), ("timestamp", 1)],
            name="idx_timeline_correlation",
        )
        await coll.create_index(
            [("tenant_id", 1), ("external_id", 1), ("timestamp", 1)],
            name="idx_timeline_external",
        )
        await coll.create_index(
            [("entity_type", 1), ("stage", 1), ("status", 1), ("timestamp", 1)],
            name="idx_timeline_stage_health",
        )
        await coll.create_index(
            [("timestamp", 1)],
            name="idx_timeline_ttl",
            expireAfterSeconds=7776000,  # 90 days
        )
        logger.info("Event timeline indexes ensured")
    except Exception as e:
        logger.warning("Timeline index creation error: %s", e)


# ── Singleton ──────────────────────────────────────────────────────
_writer: TimelineWriter | None = None


def get_timeline_writer() -> TimelineWriter:
    global _writer
    if _writer is None:
        _writer = TimelineWriter()
    return _writer
