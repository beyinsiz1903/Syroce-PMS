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
    assert "map $http_upgrade $connection_upgrade" in config
    assert "location /ws/" in config

    ws_location = config.split("location /ws/", maxsplit=1)[1]
    assert "proxy_set_header Upgrade $http_upgrade;" in ws_location
    assert "proxy_set_header Connection $connection_upgrade;" in ws_location
    assert "proxy_read_timeout 86400s;" in ws_location


def test_every_websocket_rate_limit_is_declared() -> None:
    for config_path in (ROOT / "infra/nginx/prod.conf", ROOT / "deploy/nginx/api.conf"):
        config = config_path.read_text(encoding="utf-8")

        assert "limit_req_zone $binary_remote_addr zone=ws_limit:" in config
        ws_location = config.split("location /ws/", maxsplit=1)[1]
        assert "limit_req zone=ws_limit burst=10 nodelay;" in ws_location


def test_service_worker_is_never_served_as_an_immutable_asset() -> None:
    config = (ROOT / "infra/nginx/prod.conf").read_text(encoding="utf-8")

    worker_location = config.split("location = /service-worker.js", maxsplit=1)[1]

    assert 'Cache-Control "no-cache, no-store, must-revalidate" always;' in worker_location
    assert "proxy_hide_header Cache-Control;" in worker_location
    assert config.index("location = /service-worker.js") < config.index("location ~* \\.(js|css")
