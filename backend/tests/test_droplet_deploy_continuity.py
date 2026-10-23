"""Regression guards for the single-Droplet production rollout."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_COMPOSE = "docker compose -f docker-compose.prod.yml -f deploy/docker-compose.registry.yml"


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


def test_deploy_pulls_ci_images_before_replacing_running_services_without_builds():
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(
        encoding="utf-8"
    )

    pull = workflow.index("bash deploy/pull-ci-images.sh")
    preflight = workflow.index("run --rm --no-deps --pull never backend")
    compose_up = workflow.index("up -d --no-build --pull never")

    assert pull < preflight < compose_up
    assert "docker compose -f docker-compose.prod.yml build" not in workflow
    assert REGISTRY_COMPOSE in workflow
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
    compose_up = "up -d --no-build --pull never"

    assert install in workflow
    assert workflow.index(install) < workflow.index(compose_up)
    assert workflow.index(execute, workflow.index(compose_up)) > workflow.index(compose_up)


def test_deploy_validates_and_reloads_bind_mounted_nginx_configuration():
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(
        encoding="utf-8"
    )

    compose_up = workflow.index("up -d --no-build --pull never")
    nginx_test = "docker compose -f docker-compose.prod.yml exec -T nginx nginx -t"
    nginx_reload = "docker compose -f docker-compose.prod.yml exec -T nginx nginx -s reload"

    assert nginx_test in workflow
    assert nginx_reload in workflow
    assert compose_up < workflow.index(nginx_test) < workflow.index(nginx_reload)


def test_registry_deploy_keeps_exact_revision_ci_gates_and_read_only_credentials():
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/deploy.yml").read_text())
    assert workflow["permissions"] == {"contents": "read", "actions": "read", "packages": "read"}
    steps = workflow["jobs"]["deploy"]["steps"]
    checkout = next(step for step in steps if step.get("name") == "Checkout Code")
    assert checkout["with"]["ref"] == "${{ env.DEPLOY_SHA }}"
    gate = next(step for step in steps if step.get("id") == "gate")["with"]["script"]
    assert "main.data.commit.sha !== sha" in gate
    assert "head_sha: sha" in gate
    assert "['Syroce PMS CI/CD Pipeline', 'Frontend Quality Gates']" in gate
    assert "latest?.conclusion === 'success'" in gate
    deploy = next(step for step in steps if step.get("name") == "Deploy to Server")
    assert deploy["if"] == "steps.gate.outputs.ready == 'true'"
    assert deploy["env"]["REGISTRY_TOKEN"] == "${{ github.token }}"
    assert "unset REGISTRY_TOKEN" in deploy["with"]["script"]
    assert "verify_exely_whitelist.py --env production" in deploy["with"]["script"]


def test_registry_overlay_uses_ci_names_and_does_not_change_service_safety_settings():
    overlay = yaml.safe_load((REPO_ROOT / "deploy/docker-compose.registry.yml").read_text())
    services = overlay["services"]
    assert set(services) == {"backend", "frontend", "worker", "beat"}
    for name, service in services.items():
        assert set(service) == {"image"}
        image_service = "worker" if name == "beat" else name
        assert service["image"] == (
            "${DEPLOY_IMAGE_PREFIX:?CI registry prefix required}-"
            f"{image_service}:${{DEPLOY_SHA:?Exact CI revision required}}"
        )
    pipeline = (REPO_ROOT / ".github/workflows/ci-cd.yml").read_text()
    assert "IMAGE_PREFIX: ${{ github.repository_owner }}/syroce" in pipeline
    for service in ("backend", "frontend", "worker"):
        assert f"${{{{ env.IMAGE_PREFIX }}}}-{service}:${{{{ github.sha }}}}" in pipeline


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
