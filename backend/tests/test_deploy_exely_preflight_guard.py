"""Regression guard for the production webhook security preflight."""

from pathlib import Path


def test_droplet_deploy_checks_exely_trust_boundary_before_image_build():
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (repo_root / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    preflight = "python scripts/verify_exely_whitelist.py --env production"
    build = "docker compose -f docker-compose.prod.yml build backend"
    assert preflight in workflow
    assert build in workflow
    assert workflow.index(preflight) < workflow.index(build)
    assert "docker compose -f docker-compose.prod.yml down" not in workflow
    # Run under compose so backend/.env is available, but prevent startup or
    # dependency attachment while this is only a pure configuration check.
    assert "run --rm --no-deps backend" in workflow
