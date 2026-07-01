"""
Tests: Urgent Message Report Endpoint (Task #26)

`GET /api/audit/urgent-message-report` — yöneticilerin acil mesaj
kullanımını takip edebilmesi için audit_logs üzerinden filtre + özet
sunan endpoint.

Aggregation pipeline'ı motor cursor üzerinden çalıştığı için tam
entegrasyon testi yerine mock-based: pipeline'ın doğru `$match`
aşamasını ürettiğini ve facet sonucundan response şeklinin doğru
çıkarıldığını doğrularız. Aggregation operatörlerinin (`$facet`,
`$group`, `$sort`, `$count`, `$substr`) MongoDB doğruluğu standart
operatörler olduğu için ek olarak garanti edilmez.
"""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
    pytest.skip("Motor event loop conflict in CI", allow_module_level=True)

from models.enums import UserRole
from models.schemas import User


def _make_user(tenant: str = "tenant-abc", role: UserRole = UserRole.ADMIN) -> User:
    return User(
        id="user-admin-1",
        tenant_id=tenant,
        email="admin@example.com",
        username="admin1",
        name="Ad Min",
        role=role,
    )


def _make_mock_db(facet_result: dict | None = None) -> tuple[MagicMock, MagicMock]:
    """
    Geriye (mock_db, mock_aggregate) tuple'ı döner. Aggregate mock'u
    çağrıldığında `to_list` AsyncMock'u verilen `facet_result`'ı tek
    elemanlı liste olarak döndürür.
    """
    mock_db = MagicMock()
    mock_db.audit_logs = MagicMock()

    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[facet_result] if facet_result else [])

    mock_aggregate = MagicMock(return_value=cursor)
    mock_db.audit_logs.aggregate = mock_aggregate
    return mock_db, mock_aggregate


def _capture_match(mock_aggregate: MagicMock) -> dict:
    """Aggregate'e geçirilen pipeline'ın `$match` aşamasını döndürür."""
    pipeline = mock_aggregate.call_args[0][0]
    return pipeline[0]["$match"]


# ── Filter / pipeline shape ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_includes_tenant_and_operation_name():
    """match aşaması her zaman tenant + send_urgent_internal_message
    operation_name içermeli — tenant izolasyonu için kritik."""
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db()
    user = _make_user(tenant="tenant-xyz")

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_urgent_message_report(limit=50, offset=0, current_user=user)

    match = _capture_match(mock_aggregate)
    assert match["tenant_id"] == "tenant-xyz"
    assert match["operation_name"] == "send_urgent_internal_message"


@pytest.mark.asyncio
async def test_pipeline_applies_date_range():
    """start_date / end_date birlikte verilince timestamp $gte ve
    $lte birlikte oluşmalı."""
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db()
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_urgent_message_report(
            start_date="2026-04-01T00:00:00",
            end_date="2026-04-27T23:59:59",
            limit=50,
            offset=0,
            current_user=user,
        )

    match = _capture_match(mock_aggregate)
    assert match["timestamp"]["$gte"] == "2026-04-01T00:00:00"
    assert match["timestamp"]["$lte"] == "2026-04-27T23:59:59"


@pytest.mark.asyncio
async def test_pipeline_applies_sender_and_recipient_filters():
    """sender_id -> actor_id, recipient_department ->
    after_snapshot.to_department; ikisi de match'a girmeli."""
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db()
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_urgent_message_report(
            sender_id="user-supervisor-9",
            recipient_department="Housekeeping",
            limit=50,
            offset=0,
            current_user=user,
        )

    match = _capture_match(mock_aggregate)
    assert match["actor_id"] == "user-supervisor-9"
    assert match["after_snapshot.to_department"] == "Housekeeping"


@pytest.mark.asyncio
async def test_pipeline_omits_optional_filters_when_unset():
    """Hiç filtre verilmediğinde match yalnızca tenant + operation_name
    içermeli — boş string veya None değer match'e sızmamalı."""
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db()
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_urgent_message_report(limit=50, offset=0, current_user=user)

    match = _capture_match(mock_aggregate)
    assert set(match.keys()) == {"tenant_id", "operation_name"}


# ── Response shape ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_extracts_summary_and_total_correctly():
    """facet sonucundan total, by_sender, by_recipient_department ve
    by_hour_of_day düzgün şekilde flatten edilmeli."""
    from routers import audit_timeline as router_mod

    facet = {
        "events": [
            {
                "id": "audit-1",
                "timestamp": "2026-04-27T08:15:00",
                "actor_id": "u1",
                "after_snapshot": {
                    "from_user_name": "Sup A",
                    "from_department": "Management",
                    "to_department": "Housekeeping",
                    "message_preview": "Yangın!",
                },
            },
        ],
        "by_sender": [
            {
                "_id": {
                    "sender_id": "u1",
                    "sender_name": "Sup A",
                    "sender_department": "Management",
                },
                "count": 7,
            },
            {
                "_id": {
                    "sender_id": "u2",
                    "sender_name": "Sup B",
                    "sender_department": "Management",
                },
                "count": 3,
            },
        ],
        "by_recipient_department": [
            {"_id": "Housekeeping", "count": 6},
            {"_id": "Maintenance", "count": 4},
        ],
        "by_hour_of_day": [
            {"_id": "08", "count": 5},
            {"_id": "14", "count": 5},
        ],
        "total": [{"count": 10}],
    }

    mock_db, _ = _make_mock_db(facet_result=facet)
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        result = await router_mod.get_urgent_message_report(limit=50, offset=0, current_user=user)

    assert result["total"] == 10
    assert result["events"][0]["id"] == "audit-1"

    senders = result["summary"]["by_sender"]
    assert senders[0] == {
        "sender_id": "u1",
        "sender_name": "Sup A",
        "sender_department": "Management",
        "count": 7,
    }
    assert senders[1]["sender_id"] == "u2"

    depts = result["summary"]["by_recipient_department"]
    assert depts == [
        {"department": "Housekeeping", "count": 6},
        {"department": "Maintenance", "count": 4},
    ]

    hours = result["summary"]["by_hour_of_day"]
    assert hours == [
        {"hour": "08", "count": 5},
        {"hour": "14", "count": 5},
    ]

    assert result["filters"] == {
        "start_date": None,
        "end_date": None,
        "sender_id": None,
        "recipient_department": None,
    }


@pytest.mark.asyncio
async def test_response_handles_empty_dataset_gracefully():
    """Hiç eşleşme olmayan dönemde tüm alanlar boş ama tutarlı
    olmalı — frontend `total === 0` üzerinden empty-state gösterebilsin."""
    from routers import audit_timeline as router_mod

    facet = {
        "events": [],
        "by_sender": [],
        "by_recipient_department": [],
        "by_hour_of_day": [],
        "total": [],
    }
    mock_db, _ = _make_mock_db(facet_result=facet)
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        result = await router_mod.get_urgent_message_report(limit=50, offset=0, current_user=user)

    assert result["total"] == 0
    assert result["events"] == []
    assert result["summary"] == {
        "by_sender": [],
        "by_recipient_department": [],
        "by_hour_of_day": [],
    }


# ── Authorization ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_view_audit_log_permission_blocks_non_manager_roles():
    """`view_audit_log` operation'ı manager-only kapı: SUPERVISOR /
    ADMIN dışındaki roller (FRONT_DESK, HOUSEKEEPING vb.) çağrı
    yapamamalı. Endpoint'in dependency'si bu kapıyı uyguluyor."""
    from fastapi import HTTPException

    from modules.pms_core.role_permission_service import require_op

    dep = require_op("view_audit_log")

    # FRONT_DESK reddedilmeli.
    front_desk = _make_user(role=UserRole.FRONT_DESK)
    with pytest.raises(HTTPException) as exc_info:
        await dep(current_user=front_desk)
    assert exc_info.value.status_code == 403

    # SUPERVISOR ve ADMIN ise sessizce geçmeli.
    for role in (UserRole.SUPERVISOR, UserRole.ADMIN):
        user = _make_user(role=role)
        # raise etmemeli.
        result = await dep(current_user=user)
        assert result is None


@pytest.mark.asyncio
async def test_response_drops_summary_buckets_with_null_keys():
    """Audit kaydında `to_department` veya sender bilgisi null ise
    o bucket özet listesinden düşmeli — UI'da '__None__: 4' gibi
    anlamsız satırlar görünmesin."""
    from routers import audit_timeline as router_mod

    facet = {
        "events": [],
        "by_sender": [
            {"_id": {"sender_id": None, "sender_name": None, "sender_department": None}, "count": 2},
            {"_id": {"sender_id": "u1", "sender_name": "Sup A", "sender_department": "Management"}, "count": 5},
        ],
        "by_recipient_department": [
            {"_id": None, "count": 1},
            {"_id": "Housekeeping", "count": 4},
        ],
        "by_hour_of_day": [
            {"_id": None, "count": 1},
            {"_id": "09", "count": 3},
        ],
        "total": [{"count": 6}],
    }
    mock_db, _ = _make_mock_db(facet_result=facet)
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        result = await router_mod.get_urgent_message_report(limit=50, offset=0, current_user=user)

    assert [s["sender_id"] for s in result["summary"]["by_sender"]] == ["u1"]
    assert [d["department"] for d in result["summary"]["by_recipient_department"]] == ["Housekeeping"]
    assert [h["hour"] for h in result["summary"]["by_hour_of_day"]] == ["09"]
