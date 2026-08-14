from pathlib import Path

from core.integrations.nilvera.config import get_nilvera_config


ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/nilvera-production-preflight.yml"
SCRIPT = Path(__file__).parents[1] / "scripts/nilvera_production_preflight.py"


def test_nilvera_production_preflight_workflow_is_exact_head_get_only():
    workflow = WORKFLOW.read_text()

    assert "name: Nilvera Production Read-Only Preflight" in workflow
    assert "environment: production" in workflow
    assert 'test "${{ github.ref_name }}" = "main"' in workflow
    assert 'test "$APPROVED_HEAD_SHA" = "${{ github.sha }}"' in workflow
    assert "BLOCKED_READ_ONLY_PREFLIGHT_CONFIRMATION_REQUIRED" in workflow
    assert "BLOCKED_NO_PROVIDER_WRITE_ATTESTATION_REQUIRED" in workflow
    assert "BLOCKED_PREFLIGHT_RERUN" in workflow
    assert 'NILVERA_ENV: production' in workflow
    assert 'NILVERA_RETRY_MAX: "0"' in workflow
    assert 'NILVERA_INCOMING_ANSWER_ENABLED: "false"' in workflow
    assert 'NILVERA_CREATE_RETURN_ENABLED: "false"' in workflow
    assert "provider_read_count: 2" in workflow
    assert "provider_write_count: 0" in workflow
    assert "deploy_count: 0" in workflow
    assert "production_config_mutation_count: 0" in workflow

    forbidden = (
        "doctl apps update",
        "kubectl apply",
        "docker push",
        "CREATE_PURCHASE_RETURN",
        "SEND_ANSWER",
        "SEND_INVOICE_MODEL",
    )
    for token in forbidden:
        assert token not in workflow


def test_nilvera_production_preflight_script_has_only_two_nonretrying_provider_gets():
    source = SCRIPT.read_text()

    assert source.count("await client.get(") == 2
    assert source.count("retryable=False") == 2
    assert "NilveraEndpoints.GET_COMPANY" in source
    assert "NilveraEndpoints.CHECK_TAX_NUMBER" in source
    assert "provider_read_count=2, provider_write_count=0" in source

    forbidden = (
        ".post(",
        ".put(",
        ".patch(",
        ".delete(",
        "NilveraEndpoints.CREATE_PURCHASE_RETURN",
        "NilveraEndpoints.SEND_ANSWER",
        "NilveraEndpoints.SEND_INVOICE_MODEL",
        "update_nilvera_tenant_config",
    )
    for token in forbidden:
        assert token not in source


def test_nilvera_production_config_resolves_only_official_production_host(monkeypatch):
    import core.integrations.nilvera.config

    monkeypatch.setenv("NILVERA_ENABLED", "true")
    monkeypatch.setenv("NILVERA_ENV", "production")
    core.integrations.nilvera.config._config = None

    config = get_nilvera_config()

    assert config.enabled is True
    assert config.env == "production"
    assert config.base_url == "https://api.nilvera.com"
    assert "apitest.nilvera.com" not in config.base_url
    assert "localhost" not in config.base_url

    core.integrations.nilvera.config._config = None
