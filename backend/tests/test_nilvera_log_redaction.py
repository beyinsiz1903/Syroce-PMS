"""Fail-closed logging contracts for Nilvera background processing."""

import ast
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.integrations.invoice_dispatch_worker import InvoiceDispatchWorker
from core.integrations.nilvera import provisioner
from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.errors import NilveraApiError
from core.integrations.nilvera.series import NilveraSeriesService
from core.integrations.nilvera.taxpayer import NilveraTaxpayerService

BACKEND_ROOT = Path(__file__).resolve().parents[1]
LOG_CONTRACT_FILES = (
    "core/integrations/invoice_dispatch_worker.py",
    "core/integrations/invoice_reconciliation_worker.py",
    "core/integrations/invoice_return_repository.py",
    "core/integrations/invoice_status_service.py",
    "core/integrations/invoice_status_worker.py",
    "core/integrations/nilvera/provisioner.py",
    "core/integrations/nilvera/series.py",
    "core/integrations/nilvera/taxpayer.py",
)
SENSITIVE_LOG_NAMES = {
    "record",
    "record_id",
    "tenant_id",
    "correlation_id",
    "clean_number",
    "tax_number",
    "worker_id",
    "_worker_id",
}


def _logger_calls(tree: ast.AST) -> list[ast.Call]:
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id != "logger":
            continue
        if node.func.attr in {"debug", "info", "warning", "error", "exception", "critical"}:
            calls.append(node)
    return calls


@pytest.mark.parametrize("relative_path", LOG_CONTRACT_FILES)
def test_nilvera_log_calls_do_not_reference_sensitive_identifiers(relative_path: str):
    source = (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for call in _logger_calls(tree):
        referenced_names = {node.id for node in ast.walk(call) if isinstance(node, ast.Name)}
        referenced_attributes = {node.attr for node in ast.walk(call) if isinstance(node, ast.Attribute)}
        leaked_names = (referenced_names | referenced_attributes) & SENSITIVE_LOG_NAMES
        assert not leaked_names, f"{relative_path}:{call.lineno} logs {sorted(leaked_names)}"


@pytest.mark.asyncio
async def test_invalid_dispatch_record_is_not_rendered(caplog):
    caplog.set_level(logging.ERROR)
    worker = InvoiceDispatchWorker()
    sensitive_record = {
        "id": "sensitive-invoice-id",
        "provider_payload": "sensitive-provider-payload",
        "customer": "sensitive-customer",
    }

    await worker._process_record(sensitive_record)

    assert "invalid record" in caplog.text.lower()
    for sensitive_value in sensitive_record.values():
        assert sensitive_value not in caplog.text


@pytest.mark.asyncio
async def test_taxpayer_api_error_omits_tax_and_correlation(caplog):
    caplog.set_level(logging.ERROR)
    client = AsyncMock(spec=NilveraHttpClient)
    client.get.side_effect = NilveraApiError(message="provider failure", http_status=500)
    service = NilveraTaxpayerService(client)

    with pytest.raises(NilveraApiError):
        await service.check_taxpayer("1234567801", correlation_id="sensitive-correlation")

    assert "NilveraApiError" in caplog.text
    assert "1234567801" not in caplog.text
    assert "sensitive-correlation" not in caplog.text


@pytest.mark.asyncio
async def test_series_api_error_omits_correlation(caplog):
    caplog.set_level(logging.ERROR)
    client = AsyncMock(spec=NilveraHttpClient)
    client.get.side_effect = NilveraApiError(message="provider failure", http_status=500)
    service = NilveraSeriesService(client)

    with pytest.raises(NilveraApiError):
        await service.list_einvoice_series(correlation_id="sensitive-correlation")

    assert "Failed to fetch e-Invoice series" in caplog.text
    assert "sensitive-correlation" not in caplog.text


@pytest.mark.asyncio
async def test_tenant_key_decrypt_error_omits_tenant_and_exception(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    tenant_settings = SimpleNamespace(find_one=AsyncMock(return_value={"nilvera": {"enabled": True, "api_key_enc": "ciphertext"}}))
    monkeypatch.setattr(provisioner, "get_system_db", lambda: SimpleNamespace(tenant_settings=tenant_settings))
    crypto = MagicMock()
    crypto.decrypt.side_effect = RuntimeError("sensitive-exception-detail")
    monkeypatch.setattr(provisioner, "get_crypto_service", lambda: crypto)

    result = await provisioner.get_nilvera_tenant_config("sensitive-tenant", decrypt_api_key=True)

    assert result["api_key"] is None
    assert "RuntimeError" in caplog.text
    assert "sensitive-tenant" not in caplog.text
    assert "sensitive-exception-detail" not in caplog.text
