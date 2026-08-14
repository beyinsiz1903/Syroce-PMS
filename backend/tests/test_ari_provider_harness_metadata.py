import pytest

from domains.channel_manager.ari.provider_test_harness import (
    ExelyTestRunner,
    HotelRunnerTestRunner,
    build_execution_metadata,
    get_checklist,
    summarize_results,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider", "expected_total"), [("hotelrunner", 9), ("exely", 6)])
async def test_checklist_discloses_offline_mode(provider: str, expected_total: int) -> None:
    result = {
        "total": len(get_checklist(provider)),
        **build_execution_metadata(),
    }

    assert result["total"] == expected_total
    assert result["execution_mode"] == "dry_run"
    assert result["provider_verified"] is False
    assert result["provider_write_count"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider", "expected_total"), [("hotelrunner", 9), ("exely", 6)])
async def test_dry_run_never_reports_provider_verification(provider: str, expected_total: int) -> None:
    runner = HotelRunnerTestRunner() if provider == "hotelrunner" else ExelyTestRunner()
    results = await runner.run_all()
    result = {"results": results, **summarize_results(results)}

    assert result["summary"]["total"] == expected_total
    assert result["summary"]["failed"] == 0
    assert result["summary"]["offline_checks_passed"] is True
    assert result["execution_mode"] == "dry_run"
    assert result["provider_verified"] is False
    assert result["provider_write_count"] == 0
    assert all(item["detail"].startswith("DRY-RUN:") for item in result["results"])
