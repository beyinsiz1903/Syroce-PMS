"""Regression guards for the single-Droplet production rollout."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_deploy_builds_before_replacing_running_services():
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(
        encoding="utf-8"
    )

    first_build = workflow.index("docker compose -f docker-compose.prod.yml build backend")
    compose_up = workflow.index("docker compose -f docker-compose.prod.yml up -d")

    assert first_build < compose_up
    assert "docker compose -f docker-compose.prod.yml down" not in workflow
    assert "docker restart syroce-pms-nginx-1" not in workflow
    assert "--wait --wait-timeout 180" in workflow
    assert "flock -n 9" in workflow


def test_deploy_installs_and_executes_versioned_healthwatch():
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(
        encoding="utf-8"
    )

    install = "install -m 0755 deploy/syroce-healthwatch.sh"
    execute = "/usr/local/sbin/syroce-healthwatch"
    compose_up = "docker compose -f docker-compose.prod.yml up -d"

    assert install in workflow
    assert workflow.index(install) < workflow.index(compose_up)
    assert workflow.index(execute, workflow.index(compose_up)) > workflow.index(compose_up)


def test_deploy_validates_and_reloads_bind_mounted_nginx_configuration():
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(
        encoding="utf-8"
    )

    compose_up = workflow.index("docker compose -f docker-compose.prod.yml up -d")
    nginx_test = "docker compose -f docker-compose.prod.yml exec -T nginx nginx -t"
    nginx_reload = "docker compose -f docker-compose.prod.yml exec -T nginx nginx -s reload"

    assert nginx_test in workflow
    assert nginx_reload in workflow
    assert compose_up < workflow.index(nginx_test) < workflow.index(nginx_reload)


def test_healthwatch_uses_compose_services_and_single_replica_defaults():
    script = (REPO_ROOT / "deploy" / "syroce-healthwatch.sh").read_text(
        encoding="utf-8"
    )

    assert "compose ps --status running -q" in script
    assert "HEALTHWATCH_BACKEND_REPLICAS:-1" in script
    assert "HEALTHWATCH_FRONTEND_REPLICAS:-1" in script
    assert "HEALTHWATCH_WORKER_REPLICAS:-1" in script
    assert "backend-2" not in script
    assert "worker-2" not in script
