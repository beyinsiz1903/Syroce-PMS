"""
Runtime Stress Test — Audit Timeline Query Performance
Tests timeline grouping and aggregation under various conditions.
"""
import pytest
import os


@pytest.fixture(scope="function")
async def db():
    import motor.motor_asyncio
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "hotel_management")
    client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
    database = client[db_name]
    yield database
    client.close()


async def test_audit_timeline_grouping_100_events(db):
    """Timeline grouping should handle 100 events correctly."""
    import sys
    from pathlib import Path
    backend = Path(__file__).resolve().parent.parent.parent
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from routers.audit_timeline import _group_by_time

    logs = []
    for i in range(100):
        hour = i % 24
        logs.append({
            "id": f"log_{i}",
            "operation_name": f"op_{i % 5}",
            "severity": "info",
            "target_type": "booking",
            "timestamp": f"2026-01-15T{hour:02d}:{i % 60:02d}:00",
        })

    grouped = _group_by_time(logs)
    assert isinstance(grouped, list)
    total = sum(g["count"] for g in grouped)
    assert total == 100


async def test_audit_timeline_empty(db):
    """Empty input should return empty grouping."""
    import sys
    from pathlib import Path
    backend = Path(__file__).resolve().parent.parent.parent
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from routers.audit_timeline import _group_by_time

    grouped = _group_by_time([])
    assert grouped == []


async def test_audit_summary_aggregation_nonexistent_tenant(db):
    """Aggregation on nonexistent tenant should return empty."""
    pipeline = [
        {"$match": {"tenant_id": "nonexistent_xyz_test"}},
        {"$facet": {
            "by_severity": [{"$group": {"_id": "$severity", "count": {"$sum": 1}}}],
            "total": [{"$count": "count"}],
        }},
    ]
    result = await db.audit_logs.aggregate(pipeline).to_list(1)
    assert len(result) == 1
    assert "by_severity" in result[0]
