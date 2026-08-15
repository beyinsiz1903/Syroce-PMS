from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
CI_WORKFLOW = ROOT / ".github/workflows/ci-cd.yml"
KUBERNETES_WORKFLOW = ROOT / ".github/workflows/deploy.yml"
APP_PLATFORM_WORKFLOW = ROOT / ".github/workflows/deploy-app-platform.yml"


def _load_workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _step_script(workflow: dict, job_name: str, step_name: str) -> str:
    steps = workflow["jobs"][job_name]["steps"]
    return next(step["run"] for step in steps if step.get("name") == step_name)


def test_main_ci_only_enables_kubernetes_deploy_when_explicitly_selected():
    workflow = _load_workflow(CI_WORKFLOW)
    condition = workflow["jobs"]["deploy-production"]["if"]

    assert "github.ref == 'refs/heads/main'" in condition
    assert "vars.PRODUCTION_DEPLOY_TARGET == 'kubernetes'" in condition


def test_kubernetes_production_deploy_fails_closed_without_required_config():
    ci_workflow = _load_workflow(CI_WORKFLOW)
    manual_workflow = _load_workflow(KUBERNETES_WORKFLOW)

    ci_preflight = _step_script(
        ci_workflow,
        "deploy-production",
        "Pre-deploy — Record current revision",
    )
    manual_preflight = _step_script(
        manual_workflow,
        "deploy-production",
        "Pre-deploy check",
    )
    ci_smoke = _step_script(
        ci_workflow,
        "deploy-production",
        "Post-deploy — Smoke test",
    )
    manual_smoke = _step_script(
        manual_workflow,
        "deploy-production",
        "Smoke test",
    )

    for script in (ci_preflight, manual_preflight):
        assert "KUBECONFIG" in script
        assert "exit 1" in script
        assert "deployment skipped" not in script.lower()

    for script in (ci_smoke, manual_smoke):
        assert "PRODUCTION_URL" in script
        assert "exit 1" in script
        assert "smoke test skipped" not in script.lower()


def test_app_platform_workflow_is_the_fail_closed_digitalocean_path():
    workflow = _load_workflow(APP_PLATFORM_WORKFLOW)
    target_check = _step_script(
        workflow,
        "deploy-app-platform",
        "Validate deployment target",
    )
    config_check = _step_script(
        workflow,
        "deploy-app-platform",
        "Validate required configuration",
    )
    deploy = _step_script(
        workflow,
        "deploy-app-platform",
        "Trigger App Platform Deployment",
    )
    smoke = _step_script(
        workflow,
        "deploy-app-platform",
        "Smoke test",
    )

    assert "production" in target_check
    assert "main" in target_check
    assert "DIGITALOCEAN_ACCESS_TOKEN" in config_check
    assert "DO_APP_ID" in config_check
    assert "GITHUB_SHA" in deploy
    assert "Live tag and repository verification passed" in deploy
    assert "APP_BASE_URL" in smoke
    assert "curl --fail" in smoke
