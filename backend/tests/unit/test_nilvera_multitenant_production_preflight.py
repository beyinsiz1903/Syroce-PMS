from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "nilvera_production_preflight.py"
WORKFLOW = ROOT.parent / ".github" / "workflows" / "nilvera-production-preflight.yml"
PROVISIONER = ROOT / "core" / "integrations" / "nilvera" / "provisioner.py"


def test_preflight_uses_one_central_github_nilvera_secret() -> None:
    workflow = WORKFLOW.read_text()

    assert "secrets.NILVERA_PRODUCTION_API_KEY" in workflow
    assert "secrets.NILVERA_PRODUCTION_TENANT_ID" not in workflow
    assert "secrets.NILVERA_PRODUCTION_SELLER_VKN" not in workflow
    assert "NILVERA_PRODUCTION_TARGET_TENANT_ID" not in workflow


def test_platform_workflow_remains_read_only_and_single_read_at_runtime() -> None:
    workflow = WORKFLOW.read_text()
    script = SCRIPT.read_text()

    for token in (".post(", ".put(", ".patch(", ".delete("):
        assert token not in script

    assert script.count("await client.get(") == 2
    assert 'expected_read_count = 2 if tenant_id is not None else 1' in script
    assert 'NILVERA_PRODUCTION_TARGET_TENANT_ID' in script
    assert 'provider_write_count=0' in script
    assert 'echo "- provider_read_count: 1"' in workflow
    assert 'echo "- provider_write_count: 0"' in workflow


def test_tenant_identity_is_loaded_from_syroce_tenant_settings() -> None:
    script = SCRIPT.read_text()
    provisioner = PROVISIONER.read_text()

    assert "get_nilvera_tenant_config" in script
    assert "decrypt_api_key=False" in script
    assert 'seller = tenant_cfg.get("seller") or {}' in script
    assert 'seller.get("vkn")' in script
    assert 'sysdb.tenant_settings.find_one' in provisioner


def test_tenant_preflight_is_fail_closed() -> None:
    script = SCRIPT.read_text()

    assert "BLOCKED_TENANT_NILVERA_NOT_ENABLED" in script
    assert "BLOCKED_TENANT_SELLER_VKN_INVALID" in script
    assert "BLOCKED_PRODUCTION_PROVIDER_READ_COUNT" in script
    assert 'retryable=False' in script
    assert "tenant identifiers, or response payloads" in script


def test_workflow_does_not_deploy_or_mutate_production_config() -> None:
    workflow = WORKFLOW.read_text().lower()

    forbidden = (
        "doctl apps update",
        "kubectl",
        "docker push",
        "deployctl",
        "production config mutation",
    )
    for token in forbidden:
        assert token not in workflow
