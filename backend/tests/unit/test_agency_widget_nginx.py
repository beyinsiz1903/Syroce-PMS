"""Run with NGINX_BIN pointing to an nginx with auth_request + SSL modules.

Uses the actual two production configs, loopback ports, a disposable certificate,
and a fake backend; no live services, agency credentials, or bookings involved.
"""

import os
import shutil
import socket
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _location(config, marker):
    return config.split(marker + " {", 1)[1].split("\n    }", 1)[0]


def test_widget_nginx_exception_is_exact_authenticated_and_not_cached():
    frontend = (ROOT / "frontend/nginx.conf").read_text()
    edge = (ROOT / "infra/nginx/prod.conf").read_text()
    widget = _location(frontend, "location = /agency-widget")
    auth = _location(frontend, "location = /_agency-widget-frame-policy")
    gateway = _location(edge, "location = /agency-widget")
    assert 'add_header X-Frame-Options "SAMEORIGIN" always;' in frontend
    assert 'add_header X-Frame-Options "SAMEORIGIN" always;' in edge
    assert "X-Frame-Options" not in widget
    assert "auth_request /_agency-widget-frame-policy;" in widget
    assert "auth_request_set $agency_widget_csp $upstream_http_x_widget_frame_policy;" in widget
    assert "try_files /index.html =404;" in widget
    assert "internal;" in auth
    assert "resolver 127.0.0.11 valid=10s ipv6=off;" in auth
    assert "proxy_pass http://$agency_widget_backend/api/marketplace/v1/widget/frame-policy;" in auth
    assert "X-Widget-Token $agency_widget_key;" in auth
    assert 'proxy_set_header Authorization "";' in auth
    assert 'proxy_set_header Cookie "";' in auth
    assert "proxy_hide_header X-Frame-Options;" in gateway
    assert "proxy_hide_header Content-Security-Policy" not in gateway
    for location in (widget, gateway):
        assert 'Cache-Control "no-store" always;' in location
        assert "proxy_cache " not in location
    assert "Strict-Transport-Security" in gateway
    assert "default-src 'self'" in gateway


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def nginx(tmp_path):
    executable = os.environ.get("NGINX_BIN") or shutil.which("nginx")
    if not executable:
        pytest.fail("Install Nginx with auth_request + SSL modules or set NGINX_BIN; this integration gate must run")
    seen = []
    policies = {"agency-one": "https://one.example", "agency-two": "https://two.example"}

    class Backend(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, dict(self.headers)))
            token = self.headers.get("X-Widget-Token")
            if token == "missing-policy":
                self.send_response(204)
            elif token in policies:
                self.send_response(204)
                self.send_header("X-Widget-Frame-Policy", f"frame-ancestors {policies[token]};")
            else:
                self.send_response(503 if token == "unavailable" else 403 if token == "disabled" else 401)
            self.end_headers()

        def log_message(self, *_args):
            pass

    backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
    thread = threading.Thread(target=backend.serve_forever, daemon=True)
    thread.start()
    front_port, edge_port, http_port = _free_port(), _free_port(), _free_port()
    root = tmp_path / "html"
    root.mkdir()
    (root / "index.html").write_text("<!doctype html><title>Widget integration shell</title>")
    (tmp_path / "logs").mkdir()
    certificate, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-subj", "/CN=localhost", "-keyout", str(key), "-out", str(certificate),
    ], check=True, capture_output=True)
    frontend = (ROOT / "frontend/nginx.conf").read_text().replace(
        "listen 3000;", f"listen 127.0.0.1:{front_port};"
    ).replace("/usr/share/nginx/html", str(root)).replace("backend:8001", f"127.0.0.1:{backend.server_port}")
    gateway = (ROOT / "infra/nginx/prod.conf").read_text().replace(
        "listen 80;", f"listen 127.0.0.1:{http_port};"
    ).replace("listen 443 ssl http2;", f"listen 127.0.0.1:{edge_port} ssl http2;").replace(
        "backend:8001", f"127.0.0.1:{backend.server_port}"
    ).replace("frontend:3000", f"127.0.0.1:{front_port}").replace(
        "/etc/nginx/ssl/cert.pem", str(certificate)
    ).replace("/etc/nginx/ssl/key.pem", str(key)).replace("/var/cache/nginx/api_cache", str(tmp_path / "cache"))
    config = tmp_path / "nginx.conf"
    # Distribution packages compile absolute /run and /var/log defaults. Keep
    # every runtime file in tmp_path so this gate also runs as an unprivileged
    # CI user, without touching an installed Nginx service or its PID file.
    runtime = (
        f"daemon off;\nmaster_process off;\nerror_log stderr notice;\npid {tmp_path}/nginx.pid;\n"
        "events {}\nhttp {\naccess_log off;\n"
        + "".join(f"{kind}_temp_path {tmp_path}/{kind}_temp;\n" for kind in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi"))
    )
    config.write_text(runtime + frontend + gateway + "\n}\n")
    process = None
    try:
        check = subprocess.run([executable, "-e", "stderr", "-p", str(tmp_path), "-c", str(config), "-t"], capture_output=True, text=True)
        assert check.returncode == 0, check.stderr
        process = subprocess.Popen([executable, "-e", "stderr", "-p", str(tmp_path), "-c", str(config)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with socket.socket() as sock:
                if sock.connect_ex(("127.0.0.1", edge_port)) == 0:
                    break
            if process.poll() is not None:
                pytest.fail(process.communicate()[1].decode())
            time.sleep(0.02)
        else:
            pytest.fail("Nginx did not listen on the isolated test port")

        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl._create_unverified_context()))

        def request(path, *, direct=False, headers=None):
            url = f"http://127.0.0.1:{front_port}" if direct else f"https://127.0.0.1:{edge_port}"
            try:
                response = opener.open(Request(url + path, headers=headers or {}), timeout=5)
            except HTTPError as error:
                response = error
            with response:
                return response.status, response.headers, response.read()

        yield request, seen, policies
    finally:
        if process:
            process.terminate()
            process.communicate(timeout=5)
        backend.shutdown()
        backend.server_close()
        thread.join(timeout=2)


def test_real_nginx_allows_only_token_specific_frame_ancestors(nginx):
    request, seen, policies = nginx
    for direct in (True, False):
        for token, origin in policies.items():
            status, headers, body = request(f"/agency-widget?key={token}", direct=direct, headers={
                "Authorization": "Bearer private-session", "Cookie": "session=private-session",
            })
            assert status == 200
            assert b"Widget integration shell" in body
            assert headers.get("X-Frame-Options") is None
            assert f"frame-ancestors {origin};" in headers.get_all("Content-Security-Policy")
            assert "no-store" in headers["Cache-Control"]
            assert headers["Referrer-Policy"] == "no-referrer"
        if not direct:
            assert any("default-src 'self'" in value for value in headers.get_all("Content-Security-Policy"))
            assert headers["Strict-Transport-Security"]
    assert seen
    for path, headers in seen:
        assert path == "/api/marketplace/v1/widget/frame-policy"
        assert "Authorization" not in headers
        assert "Cookie" not in headers
    # Editing the saved allowlist takes effect on the very next document load.
    policies["agency-one"] = "https://changed.example"
    assert "frame-ancestors https://changed.example;" in request("/agency-widget?key=agency-one")[1].get_all("Content-Security-Policy")


def test_real_nginx_denies_invalid_widget_and_preserves_pms_protection(nginx):
    request, _, _ = nginx
    for suffix, expected in (("", 401), ("?key=invalid", 401), ("?key=disabled", 403), ("?key=unavailable", 500)):
        status, _, body = request("/agency-widget" + suffix)
        assert status == expected
        assert b"Widget integration shell" not in body
    assert request("/_agency-widget-frame-policy")[0] == 404
    status, headers, _ = request("/agency-widget?key=missing-policy")
    assert status == 200
    assert "frame-ancestors 'none';" in headers.get_all("Content-Security-Policy")
    status, headers, body = request("/app/dashboard")
    assert status == 200
    assert b"Widget integration shell" in body
    assert headers["X-Frame-Options"] == "SAMEORIGIN"
