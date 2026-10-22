"""Regression guards for the single-Droplet production rollout."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_frontend_waits_for_backend_health_before_static_nginx_dns_resolution():
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.prod.yml").read_text())
    assert compose["services"]["frontend"]["depends_on"]["backend"]["condition"] == "service_healthy"
    assert "healthcheck" in compose["services"]["backend"]
    assert "healthcheck" in compose["services"]["frontend"]


def test_failed_rollout_collects_the_frontend_failure_not_only_backend_logs():
    workflow = (REPO_ROOT / ".github/workflows/deploy.yml").read_text()
    failure = workflow.split("if ! docker compose", 1)[1].split("exit 1", 1)[0]
    assert "ps --all" in failure
    assert "logs --no-color --tail=150 frontend backend worker beat nginx" in failure
    assert "docker inspect" not in failure  # Never dump container environment/secrets.


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
