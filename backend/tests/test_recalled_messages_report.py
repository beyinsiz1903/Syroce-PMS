"""
Tests: Recalled Messages Report Endpoint (Task #35)

`GET /api/audit/recalled-messages` — yöneticilerin iç mesaj geri alma
denetim kayıtlarını filtre + özet ile takip etmesi için endpoint.

Aggregation pipeline'ı motor cursor üzerinden çalıştığı için tam
entegrasyon yerine mock-based: pipeline'ın doğru `$match` aşamasını
ürettiğini ve facet sonucundan response şeklinin doğru çıkarıldığını
doğrularız.
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
    mock_db = MagicMock()
    mock_db.audit_logs = MagicMock()

    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[facet_result] if facet_result else [])

    mock_aggregate = MagicMock(return_value=cursor)
    mock_db.audit_logs.aggregate = mock_aggregate
    return mock_db, mock_aggregate


def _capture_match(mock_aggregate: MagicMock) -> dict:
    pipeline = mock_aggregate.call_args[0][0]
    return pipeline[0]["$match"]


# ── Filter / pipeline shape ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_includes_tenant_and_recall_operation_name():
    """match aşaması her zaman tenant + recall_internal_message
    operation_name içermeli — tenant izolasyonu için kritik."""
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db()
    user = _make_user(tenant="tenant-xyz")

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_recalled_messages_report(
            limit=50, offset=0, current_user=user
        )

    match = _capture_match(mock_aggregate)
    assert match["tenant_id"] == "tenant-xyz"
    assert match["operation_name"] == "recall_internal_message"


@pytest.mark.asyncio
async def test_pipeline_applies_date_range():
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db()
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_recalled_messages_report(
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
async def test_pipeline_applies_sender_and_priority_filters():
    """sender_id -> actor_id; priority -> before_snapshot.priority."""
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db()
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_recalled_messages_report(
            sender_id="user-sender-9",
            priority="urgent",
            limit=50,
            offset=0,
            current_user=user,
        )

    match = _capture_match(mock_aggregate)
    assert match["actor_id"] == "user-sender-9"
    assert match["before_snapshot.priority"] == "urgent"


@pytest.mark.asyncio
async def test_invalid_priority_value_raises_422():
    """priority="bogus" gibi geçersiz değer endpoint'e ulaşınca 422
    HTTPException atılmalı — admin "filtre uyguladım" sanıp filtresiz
    sonuçları görüp yanlış değerlendirmesin."""
    from fastapi import HTTPException

    from routers import audit_timeline as router_mod

    mock_db, _ = _make_mock_db()
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        with pytest.raises(HTTPException) as exc_info:
            await router_mod.get_recalled_messages_report(
                priority="bogus",
                limit=50,
                offset=0,
                current_user=user,
            )
        assert exc_info.value.status_code == 422

        # Geçerli değerler raise etmemeli.
        for ok in ("urgent", "normal"):
            await router_mod.get_recalled_messages_report(
                priority=ok,
                limit=50,
                offset=0,
                current_user=user,
            )


@pytest.mark.asyncio
async def test_pipeline_omits_priority_when_unset():
    """priority parametresi verilmediğinde match'e priority kısıtı
    eklenmemeli."""
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db()
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_recalled_messages_report(
            limit=50, offset=0, current_user=user,
        )

    match = _capture_match(mock_aggregate)
    assert "before_snapshot.priority" not in match


@pytest.mark.asyncio
async def test_pipeline_omits_optional_filters_when_unset():
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db()
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_recalled_messages_report(
            limit=50, offset=0, current_user=user
        )

    match = _capture_match(mock_aggregate)
    assert set(match.keys()) == {"tenant_id", "operation_name"}


# ── Task #36: include_denied flag ────────────────────────────────────


@pytest.mark.asyncio
async def test_include_denied_false_keeps_narrow_recall_filter():
    """Default behavior (Task #35): only successful recalls are returned.
    Backward compatibility — existing callers must be unaffected."""
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db()
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_recalled_messages_report(
            include_denied=False, limit=50, offset=0, current_user=user
        )

    match = _capture_match(mock_aggregate)
    assert match["operation_name"] == "recall_internal_message"


@pytest.mark.asyncio
async def test_include_denied_true_widens_filter_to_both_actions():
    """When include_denied=True the report covers both successful and
    window-expired recall attempts (Task #36)."""
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db()
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_recalled_messages_report(
            include_denied=True, limit=50, offset=0, current_user=user
        )

    match = _capture_match(mock_aggregate)
    op = match["operation_name"]
    assert isinstance(op, dict) and "$in" in op
    assert "recall_internal_message" in op["$in"]
    assert "recall_internal_message_denied" in op["$in"]


@pytest.mark.asyncio
async def test_events_project_includes_operation_name_for_denial_distinction():
    """Frontend must be able to tell a successful recall from a denied
    attempt — pipeline projection must preserve `operation_name`."""
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db()
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_recalled_messages_report(
            include_denied=True, limit=50, offset=0, current_user=user
        )

    pipeline = mock_aggregate.call_args[0][0]
    facet = pipeline[1]["$facet"]
    events_stages = facet["events"]
    # Find the $project stage and assert operation_name is kept.
    project_stage = next(s for s in events_stages if "$project" in s)["$project"]
    assert project_stage.get("operation_name") == 1


# ── Response shape ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_extracts_summary_and_total_correctly():
    """facet sonucundan total, by_sender, by_priority ve by_hour_of_day
    düzgün şekilde flatten edilmeli."""
    from routers import audit_timeline as router_mod

    facet = {
        "events": [
            {
                "id": "audit-r1",
                "timestamp": "2026-04-27T08:15:00",
                "actor_id": "u1",
                "before_snapshot": {
                    "from_user_name": "Sup A",
                    "from_department": "Management",
                    "to_department": "Housekeeping",
                    "priority": "urgent",
                    "message_preview": "Yangın!",
                },
                "after_snapshot": {
                    "deleted": True,
                    "deleted_by": "u1",
                    "alarm_cleared": True,
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
                "count": 4,
            },
            {
                "_id": {
                    "sender_id": "u2",
                    "sender_name": "Sup B",
                    "sender_department": "Reception",
                },
                "count": 2,
            },
        ],
        "by_priority": [
            {"_id": "normal", "count": 4},
            {"_id": "urgent", "count": 2},
        ],
        "by_hour_of_day": [
            {"_id": "08", "count": 3},
            {"_id": "14", "count": 3},
        ],
        "total": [{"count": 6}],
    }

    mock_db, _ = _make_mock_db(facet_result=facet)
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        result = await router_mod.get_recalled_messages_report(
            limit=50, offset=0, current_user=user
        )

    assert result["total"] == 6
    assert result["events"][0]["id"] == "audit-r1"

    senders = result["summary"]["by_sender"]
    assert senders[0] == {
        "sender_id": "u1",
        "sender_name": "Sup A",
        "sender_department": "Management",
        "count": 4,
    }
    assert senders[1]["sender_id"] == "u2"

    priorities = result["summary"]["by_priority"]
    assert priorities == [
        {"priority": "normal", "count": 4},
        {"priority": "urgent", "count": 2},
    ]

    hours = result["summary"]["by_hour_of_day"]
    assert hours == [
        {"hour": "08", "count": 3},
        {"hour": "14", "count": 3},
    ]

    assert result["filters"] == {
        "start_date": None,
        "end_date": None,
        "sender_id": None,
        "priority": None,
    }
    assert result["pagination"] == {"limit": 50, "offset": 0}


@pytest.mark.asyncio
async def test_response_handles_empty_dataset_gracefully():
    """Hiç eşleşme olmayan dönemde tüm alanlar boş ama tutarlı
    olmalı — frontend `total === 0` üzerinden empty-state gösterebilsin."""
    from routers import audit_timeline as router_mod

    facet = {
        "events": [],
        "by_sender": [],
        "by_priority": [],
        "by_hour_of_day": [],
        "total": [],
    }
    mock_db, _ = _make_mock_db(facet_result=facet)
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        result = await router_mod.get_recalled_messages_report(
            limit=50, offset=0, current_user=user
        )

    assert result["total"] == 0
    assert result["events"] == []
    assert result["summary"] == {
        "by_sender": [],
        "by_priority": [],
        "by_hour_of_day": [],
    }


@pytest.mark.asyncio
async def test_response_drops_summary_buckets_with_null_keys():
    """Audit kaydında sender bilgisi null ise o bucket özet listesinden
    düşmeli — by_priority "unknown" etiketi ile gösterilir."""
    from routers import audit_timeline as router_mod

    facet = {
        "events": [],
        "by_sender": [
            {"_id": {"sender_id": None, "sender_name": None,
                     "sender_department": None}, "count": 2},
            {"_id": {"sender_id": "u1", "sender_name": "Sup A",
                     "sender_department": "Management"}, "count": 5},
        ],
        "by_priority": [
            {"_id": None, "count": 1},
            {"_id": "normal", "count": 4},
        ],
        "by_hour_of_day": [
            {"_id": None, "count": 1},
            {"_id": "09", "count": 3},
        ],
        "total": [{"count": 8}],
    }
    mock_db, _ = _make_mock_db(facet_result=facet)
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        result = await router_mod.get_recalled_messages_report(
            limit=50, offset=0, current_user=user
        )

    # Null sender bucket'ı düşmeli; null hour bucket'ı düşmeli; null
    # priority bucket'ı "unknown" etiketi ile kalır (UI'a en azından
    # "neyse" diye gösterilebilsin).
    assert [s["sender_id"] for s in result["summary"]["by_sender"]] == ["u1"]
    assert [h["hour"] for h in result["summary"]["by_hour_of_day"]] == ["09"]
    priorities = [p["priority"] for p in result["summary"]["by_priority"]]
    assert "normal" in priorities
    assert "unknown" in priorities


# ── Authorization ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_view_audit_log_permission_blocks_non_manager_roles():
    """`view_audit_log` operation'ı manager-only kapı: SUPERVISOR /
    ADMIN dışındaki roller (FRONT_DESK, HOUSEKEEPING vb.) çağrı
    yapamamalı. Endpoint'in dependency'si bu kapıyı uyguluyor."""
    from fastapi import HTTPException

    from modules.pms_core.role_permission_service import require_op

    dep = require_op("view_audit_log")

    front_desk = _make_user(role=UserRole.FRONT_DESK)
    with pytest.raises(HTTPException) as exc_info:
        await dep(current_user=front_desk)
    assert exc_info.value.status_code == 403

    for role in (UserRole.SUPERVISOR, UserRole.ADMIN):
        user = _make_user(role=role)
        result = await dep(current_user=user)
        assert result is None
