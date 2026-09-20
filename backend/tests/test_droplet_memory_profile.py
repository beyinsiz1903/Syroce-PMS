"""Regression guard for the 4 GB Droplet deployment profile.

The production deployment workflow starts ``docker-compose.prod.yml`` directly.
Do not raise process counts or the aggregate memory ceiling on this profile
without resizing the Droplet and intentionally updating this contract.
"""

from pathlib import Path


def test_four_gb_profile_uses_single_python_process_per_service():
    compose = (Path(__file__).parents[2] / "docker-compose.prod.yml").read_text(
        encoding="utf-8"
    )

    assert "WEB_CONCURRENCY: ${WEB_CONCURRENCY:-1}" in compose
    assert "--concurrency=${WORKER_CONCURRENCY:-1}" in compose


def test_four_gb_profile_has_headroom_for_host_and_docker():
    compose = (Path(__file__).parents[2] / "docker-compose.prod.yml").read_text(
        encoding="utf-8"
    )

    # API + worker + frontend + beat + nginx = 2,784 MiB.  This deliberately
    # leaves more than 1 GiB for Ubuntu, Docker and short-lived deployment
    # processes on the 4 GiB Droplet.
    for limit in ("memory: 1200M", "memory: 128M", "memory: 160M", "memory: 96M"):
        assert limit in compose
