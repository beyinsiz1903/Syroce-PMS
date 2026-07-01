"""
Tests: ID Photo View Report Endpoint (Task #83)

`GET /api/audit/id-photo-views` — yöneticilerin resepsiyonun açtığı
kimlik fotoğrafı görüntüleme audit kayıtlarını filtre + özet ile
takip etmesi için endpoint. Ayrıca `GET /api/audit/id-photo-views.csv`
dışa aktarımı için CSV üreteci.

Aggregation pipeline'ı motor cursor üzerinden çalıştığı için tam
entegrasyon yerine mock-based: pipeline'ın doğru `$match` aşamasını
ürettiğini ve facet sonucundan response şeklinin doğru çıkarıldığını
doğrularız.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# NOTE: bilerek CI atlatma yok. Bu modüldeki tüm testler motor cursor'unu
# `MagicMock`/`AsyncMock` ile değiştirir; gerçek MongoDB event loop'una
# dokunulmaz. Sibling raporları (urgent/recalled) eski bir motor problemi
# nedeniyle CI'da skip ediliyor — yeni rapor mock-only olduğu için bu
# kapı koyulmadı, böylece regresyon koruması CI'da da çalışır.
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


def _make_mock_db_aggregate(facet_result: dict | None = None) -> tuple[MagicMock, MagicMock]:
    mock_db = MagicMock()
    mock_db.audit_logs = MagicMock()

    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[facet_result] if facet_result else [])

    mock_aggregate = MagicMock(return_value=cursor)
    mock_db.audit_logs.aggregate = mock_aggregate
    return mock_db, mock_aggregate


def _make_mock_db_find(rows: list[dict]) -> tuple[MagicMock, MagicMock]:
    """`db.audit_logs.find(query, proj).sort(...).limit(...).to_list(...)` zincirini mockla."""
    mock_db = MagicMock()
    mock_db.audit_logs = MagicMock()

    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.limit = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=rows)

    mock_find = MagicMock(return_value=cursor)
    mock_db.audit_logs.find = mock_find
    return mock_db, mock_find


def _capture_match(mock_aggregate: MagicMock) -> dict:
    pipeline = mock_aggregate.call_args[0][0]
    return pipeline[0]["$match"]


# ── Filter / pipeline shape ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_includes_tenant_and_view_operation_name():
    """match aşaması her zaman tenant + view_online_checkin_id_photo
    operation_name içermeli — tenant izolasyonu için kritik."""
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db_aggregate()
    user = _make_user(tenant="tenant-xyz")

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_id_photo_view_report(
            limit=50, offset=0, current_user=user
        )

    match = _capture_match(mock_aggregate)
    assert match["tenant_id"] == "tenant-xyz"
    assert match["operation_name"] == "view_online_checkin_id_photo"


@pytest.mark.asyncio
async def test_pipeline_applies_date_range():
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db_aggregate()
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_id_photo_view_report(
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
async def test_pipeline_applies_actor_booking_and_checkin_filters():
    """actor_id -> actor_id; booking_id -> after_snapshot.booking_id;
    checkin_id -> target_id."""
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db_aggregate()
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_id_photo_view_report(
            actor_id="user-front-7",
            booking_id="bk-123",
            checkin_id="ck-456",
            limit=50,
            offset=0,
            current_user=user,
        )

    match = _capture_match(mock_aggregate)
    assert match["actor_id"] == "user-front-7"
    assert match["after_snapshot.booking_id"] == "bk-123"
    assert match["target_id"] == "ck-456"


@pytest.mark.asyncio
async def test_pipeline_omits_optional_filters_when_unset():
    """Hiç filtre verilmediğinde match yalnızca tenant + operation_name
    içermeli — boş string veya None değer match'e sızmamalı."""
    from routers import audit_timeline as router_mod

    mock_db, mock_aggregate = _make_mock_db_aggregate()
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        await router_mod.get_id_photo_view_report(
            limit=50, offset=0, current_user=user
        )

    match = _capture_match(mock_aggregate)
    assert set(match.keys()) == {"tenant_id", "operation_name"}


# ── Response shape ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_extracts_summary_and_total_correctly():
    """facet sonucundan total, by_actor, by_booking ve by_hour_of_day
    düzgün şekilde flatten edilmeli."""
    from routers import audit_timeline as router_mod

    facet = {
        "events": [
            {
                "id": "audit-v1",
                "timestamp": "2026-04-27T08:15:00",
                "actor_id": "u1",
                "actor_role": "front_desk",
                "target_id": "ck-1",
                "after_snapshot": {
                    "booking_id": "bk-1",
                    "photo_id": "p-1",
                    "sha256": "abc",
                    "content_type": "image/jpeg",
                },
            },
        ],
        "by_actor": [
            {"_id": "u1", "count": 7},
            {"_id": "u2", "count": 3},
        ],
        "by_booking": [
            {"_id": "bk-1", "count": 6},
            {"_id": "bk-2", "count": 4},
        ],
        "by_hour_of_day": [
            {"_id": "08", "count": 5},
            {"_id": "14", "count": 5},
        ],
        "total": [{"count": 10}],
    }

    mock_db, _ = _make_mock_db_aggregate(facet_result=facet)
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        result = await router_mod.get_id_photo_view_report(
            limit=50, offset=0, current_user=user
        )

    assert result["total"] == 10
    assert result["events"][0]["id"] == "audit-v1"

    actors = result["summary"]["by_actor"]
    assert actors == [
        {"actor_id": "u1", "count": 7},
        {"actor_id": "u2", "count": 3},
    ]

    bookings = result["summary"]["by_booking"]
    assert bookings == [
        {"booking_id": "bk-1", "count": 6},
        {"booking_id": "bk-2", "count": 4},
    ]

    hours = result["summary"]["by_hour_of_day"]
    assert hours == [
        {"hour": "08", "count": 5},
        {"hour": "14", "count": 5},
    ]

    assert result["filters"] == {
        "start_date": None,
        "end_date": None,
        "actor_id": None,
        "booking_id": None,
        "checkin_id": None,
    }
    assert result["pagination"] == {"limit": 50, "offset": 0}


@pytest.mark.asyncio
async def test_response_handles_empty_dataset_gracefully():
    """Hiç eşleşme olmayan dönemde tüm alanlar boş ama tutarlı
    olmalı — frontend `total === 0` üzerinden empty-state gösterebilsin."""
    from routers import audit_timeline as router_mod

    facet = {
        "events": [],
        "by_actor": [],
        "by_booking": [],
        "by_hour_of_day": [],
        "total": [],
    }
    mock_db, _ = _make_mock_db_aggregate(facet_result=facet)
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        result = await router_mod.get_id_photo_view_report(
            limit=50, offset=0, current_user=user
        )

    assert result["total"] == 0
    assert result["events"] == []
    assert result["summary"] == {
        "by_actor": [],
        "by_booking": [],
        "by_hour_of_day": [],
    }


@pytest.mark.asyncio
async def test_response_drops_summary_buckets_with_null_keys():
    """Audit kaydında actor/booking/hour bilgisi null ise o bucket
    özet listesinden düşmeli — UI'da '—: 4' gibi anlamsız satırlar
    görünmesin."""
    from routers import audit_timeline as router_mod

    facet = {
        "events": [],
        "by_actor": [
            {"_id": None, "count": 2},
            {"_id": "u1", "count": 5},
        ],
        "by_booking": [
            {"_id": None, "count": 1},
            {"_id": "bk-9", "count": 4},
        ],
        "by_hour_of_day": [
            {"_id": None, "count": 1},
            {"_id": "09", "count": 3},
        ],
        "total": [{"count": 6}],
    }
    mock_db, _ = _make_mock_db_aggregate(facet_result=facet)
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        result = await router_mod.get_id_photo_view_report(
            limit=50, offset=0, current_user=user
        )

    assert [a["actor_id"] for a in result["summary"]["by_actor"]] == ["u1"]
    assert [b["booking_id"] for b in result["summary"]["by_booking"]] == ["bk-9"]
    assert [h["hour"] for h in result["summary"]["by_hour_of_day"]] == ["09"]


# ── CSV export ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_csv_export_uses_same_match_filters_as_json_endpoint():
    """CSV ucu JSON ucu ile birebir aynı `$match` mantığı kullanmalı —
    aksi halde admin filtreyi kullandığında ekrandaki ile dosyadaki
    içerik birbirini tutmaz."""
    from routers import audit_timeline as router_mod

    mock_db, mock_find = _make_mock_db_find(rows=[])
    user = _make_user(tenant="tenant-xyz")

    with patch.object(router_mod, "db", mock_db):
        await router_mod.export_id_photo_view_report_csv(
            start_date="2026-04-01T00:00:00",
            end_date="2026-04-27T23:59:59",
            actor_id="user-front-7",
            booking_id="bk-123",
            checkin_id="ck-456",
            current_user=user,
        )

    query, _proj = mock_find.call_args[0]
    assert query["tenant_id"] == "tenant-xyz"
    assert query["operation_name"] == "view_online_checkin_id_photo"
    assert query["timestamp"] == {
        "$gte": "2026-04-01T00:00:00",
        "$lte": "2026-04-27T23:59:59",
    }
    assert query["actor_id"] == "user-front-7"
    assert query["after_snapshot.booking_id"] == "bk-123"
    assert query["target_id"] == "ck-456"


@pytest.mark.asyncio
async def test_csv_export_writes_one_row_per_audit_record_with_kvkk_columns():
    """Dosya başlığı + her audit kaydı için bir satır olmalı; her satır
    görev tanımındaki KVKK kolonlarını içermeli (kullanıcı, zaman,
    booking, check-in, photo_id)."""
    from routers import audit_timeline as router_mod

    rows = [
        {
            "id": "audit-1",
            "timestamp": "2026-04-27T08:15:00+00:00",
            "actor_id": "u1",
            "actor_role": "front_desk",
            "target_id": "ck-1",
            "after_snapshot": {
                "booking_id": "bk-1",
                "photo_id": "p-1",
                "sha256": "deadbeef",
                "content_type": "image/jpeg",
            },
        },
        {
            "id": "audit-2",
            "timestamp": "2026-04-27T09:00:00+00:00",
            "actor_id": "u2",
            "actor_role": "supervisor",
            "target_id": "ck-2",
            "after_snapshot": {
                "booking_id": "bk-2",
                "photo_id": "p-2",
                "sha256": "cafef00d",
                "content_type": "image/png",
            },
        },
    ]
    mock_db, _ = _make_mock_db_find(rows=rows)
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        response = await router_mod.export_id_photo_view_report_csv(
            current_user=user,
        )

    assert response.media_type.startswith("text/csv")
    assert "attachment" in response.headers.get("content-disposition", "")
    assert response.headers.get("content-disposition", "").endswith('.csv"')

    # Body'yi okumak için iterator'ı tüket.
    body = b""
    async for chunk in response.body_iterator:
        body += chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")

    text = body.decode("utf-8-sig")  # BOM atlanır
    lines = [line for line in text.splitlines() if line.strip()]
    # Başlık + 2 veri satırı
    assert len(lines) == 3
    header = lines[0].split(",")
    assert header == [
        "timestamp",
        "actor_id",
        "actor_role",
        "checkin_id",
        "booking_id",
        "photo_id",
        "sha256",
        "content_type",
    ]
    # İlk veri satırı doğru sırada üretilmeli.
    assert lines[1].startswith("2026-04-27T08:15:00+00:00,u1,front_desk,ck-1,bk-1,p-1,deadbeef,image/jpeg")


@pytest.mark.asyncio
async def test_csv_export_handles_missing_after_snapshot_gracefully():
    """Eski/yarım yazılmış audit kayıtlarında `after_snapshot` None
    olabilir — CSV bu durumda boş hücrelerle düzgün satır üretmeli,
    AttributeError atmamalı."""
    from routers import audit_timeline as router_mod

    rows = [
        {
            "id": "audit-x",
            "timestamp": "2026-04-27T08:15:00+00:00",
            "actor_id": "u9",
            "actor_role": None,
            "target_id": "ck-x",
            "after_snapshot": None,
        },
    ]
    mock_db, _ = _make_mock_db_find(rows=rows)
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        response = await router_mod.export_id_photo_view_report_csv(
            current_user=user,
        )

    body = b""
    async for chunk in response.body_iterator:
        body += chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
    text = body.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) == 2  # header + 1 row
    cells = lines[1].split(",")
    # timestamp, actor_id, "", checkin_id, "", "", "", ""
    assert cells == [
        "2026-04-27T08:15:00+00:00",
        "u9",
        "",
        "ck-x",
        "",
        "",
        "",
        "",
    ]


# ── Input validation ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_date_range_raises_422():
    """`start_date > end_date` admin'in farkında olmadan filtre uyguladığı
    bir tuzak — sessizce boş sonuç döner ve "kayıt yok" izlenimi verir.
    Endpoint bu durumda 422 atmalı (JSON ve CSV uçlarında aynı davranış)."""
    from fastapi import HTTPException

    from routers import audit_timeline as router_mod

    mock_db, _ = _make_mock_db_aggregate()
    user = _make_user()

    with patch.object(router_mod, "db", mock_db):
        with pytest.raises(HTTPException) as exc_info:
            await router_mod.get_id_photo_view_report(
                start_date="2026-04-30T00:00:00",
                end_date="2026-04-01T00:00:00",
                limit=50,
                offset=0,
                current_user=user,
            )
        assert exc_info.value.status_code == 422

    mock_db_csv, _ = _make_mock_db_find(rows=[])
    with patch.object(router_mod, "db", mock_db_csv):
        with pytest.raises(HTTPException) as exc_info:
            await router_mod.export_id_photo_view_report_csv(
                start_date="2026-04-30T00:00:00",
                end_date="2026-04-01T00:00:00",
                current_user=user,
            )
        assert exc_info.value.status_code == 422


# ── Authorization ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_view_audit_log_permission_blocks_non_manager_roles():
    """`view_audit_log` operation'ı manager-only kapı: SUPERVISOR /
    ADMIN dışındaki roller (FRONT_DESK, HOUSEKEEPING vb.) çağrı
    yapamamalı. KVKK kapsamında özellikle önemli."""
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
