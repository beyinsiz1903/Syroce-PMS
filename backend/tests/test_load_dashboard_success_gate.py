"""The load gate must reject successful transport with unsuccessful HTTP status."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_module():
    path = Path(__file__).resolve().parents[1] / "load_tests/test_multi_tenant_load.py"
    spec = importlib.util.spec_from_file_location("load_dashboard_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 401, 403, 404, 429, 500])
async def test_dashboard_load_requires_successful_reads(monkeypatch, status):
    module = load_module()

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, *args, **kwargs):
            return SimpleNamespace(status_code=status)

    monkeypatch.setattr(module.httpx, "AsyncClient", Client)
    tenants = {key: {"headers": {}} for key in ("a", "b")}
    run = module.TestMultiTenantDashboardIsolation().test_concurrent_dashboard_reads_per_tenant
    if status == 200:
        await run("http://localhost:1", tenants)
    else:
        with pytest.raises(AssertionError, match="Dashboard reads must succeed"):
            await run("http://localhost:1", tenants)
