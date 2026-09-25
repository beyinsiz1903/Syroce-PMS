from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "config_path",
    [
        ROOT / "infra/nginx/prod.conf",
        ROOT / "deploy/nginx/api.conf",
    ],
)
def test_realtime_proxy_and_service_worker_are_allowed(config_path: Path) -> None:
    config = config_path.read_text(encoding="utf-8")

    assert "worker-src 'self' blob:" in config
    assert "connect-src 'self' wss: https:" in config
    assert "location /ws/" in config

    ws_location = config.split("location /ws/", maxsplit=1)[1]
    assert "proxy_set_header Upgrade $http_upgrade;" in ws_location
    assert 'proxy_set_header Connection "upgrade";' in ws_location
    assert "proxy_read_timeout 86400s;" in ws_location
