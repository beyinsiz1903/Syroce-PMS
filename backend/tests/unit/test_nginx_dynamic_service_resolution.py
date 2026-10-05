from pathlib import Path


def test_production_nginx_re_resolves_docker_service_names():
    config = (Path(__file__).resolve().parents[3] / "infra" / "nginx" / "prod.conf").read_text()

    assert "resolver 127.0.0.11 valid=10s ipv6=off;" in config
    assert "set $backend_upstream backend:8001;" in config
    assert "set $frontend_upstream frontend:3000;" in config
    assert "proxy_pass http://$backend_upstream;" in config
    assert "proxy_pass http://$frontend_upstream;" in config
    assert "upstream backend_pool" not in config
    assert "upstream frontend_pool" not in config
