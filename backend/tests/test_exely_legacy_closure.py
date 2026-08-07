"""Offline guards for retired Exely reservation and mutation paths."""

from pathlib import Path

import pytest

from domains.channel_manager.ingest.workers import exely_pull_once
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.soap_builder import build_read_rq
from domains.channel_manager.reconciliation_engine.snapshot_collectors import collect_exely_snapshot


def test_ota_read_request_is_exact_official_undelivered_contract():
    xml = build_read_rq("synthetic-user", "synthetic-password", "synthetic-property")

    assert 'Version="1.17"' in xml
    assert 'SelectionType="Undelivered"' in xml
    assert 'SelectionType="All"' not in xml
    assert "UniqueID" not in xml
    assert " Start=" not in xml
    assert " End=" not in xml


def test_provider_legacy_facade_is_absent():
    provider = ExelyProvider(
        username="synthetic-user",
        password="synthetic-password",
        hotel_code="synthetic-property",
    )

    for method in (
        "legacy_test_connection",
        "legacy_pull_reservations",
        "legacy_discover_rooms",
        "legacy_push_ari",
        "legacy_confirm_delivery",
    ):
        assert not hasattr(provider, method)


@pytest.mark.asyncio
async def test_generic_exely_pull_worker_is_fail_closed():
    result = await exely_pull_once()

    assert result == {
        "fetched": 0,
        "errors": 1,
        "provider": "exely",
        "status": "disabled",
        "reason": "USE_CANONICAL_EXELY_PULL",
        "provider_write_count": 0,
    }


@pytest.mark.asyncio
async def test_unsupported_historical_reservation_snapshot_is_fail_closed():
    with pytest.raises(RuntimeError, match="EXELY_RESERVATION_SNAPSHOT_UNSUPPORTED_BY_CONTRACT"):
        await collect_exely_snapshot({}, since_hours=24)


def test_duplicate_individual_read_path_is_removed():
    worker_source = (Path(__file__).parents[1] / "domains/channel_manager/providers/exely/exely_pull_worker.py").read_text(encoding="utf-8")
    router_source = (Path(__file__).parents[1] / "domains/channel_manager/providers/exely/exely_router.py").read_text(encoding="utf-8")

    assert "_check_individual_changes" not in worker_source
    assert "_check_individual_cancellations" not in router_source
    assert "_check_individual_modifications" not in router_source
    assert "reservation_id=" not in worker_source


def test_manual_pull_does_not_run_a_second_auto_import():
    backend_root = Path(__file__).parents[1]
    worker_source = (backend_root / "domains/channel_manager/providers/exely/exely_pull_worker.py").read_text(encoding="utf-8")
    router_source = (backend_root / "domains/channel_manager/providers/exely/exely_router.py").read_text(encoding="utf-8")

    assert worker_source.count("await auto_import_pending(") == 1
    assert "auto_import_pending" not in router_source


def test_no_legacy_mutation_name_remains_in_runtime_code():
    backend_root = Path(__file__).parents[1]
    runtime_root = backend_root / "domains/channel_manager"
    forbidden = ("legacy_push_ari", "legacy_confirm_delivery", "exely_client_legacy")

    for path in runtime_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in source, path
