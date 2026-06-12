"""
Tests: proxy-safe client IP extraction for the audit trail (Task #568).

Ensures every audit record can attribute a real IP: XFF left-most hop preferred,
then X-Real-IP / Forwarded, then the direct ASGI peer when no proxy headers are
present (so direct connections are never recorded with a null IP).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.request_context import client_ip_from_headers, user_agent_from_headers


def _h(d):
    return [(k.encode("latin-1"), v.encode("latin-1")) for k, v in d.items()]


def test_prefers_leftmost_xff():
    headers = _h({"x-forwarded-for": "203.0.113.7, 10.0.0.1, 10.0.0.2"})
    assert client_ip_from_headers(headers, ("10.0.0.5", 12345)) == "203.0.113.7"


def test_falls_back_to_x_real_ip():
    headers = _h({"x-real-ip": "198.51.100.9"})
    assert client_ip_from_headers(headers, ("10.0.0.5", 1)) == "198.51.100.9"


def test_falls_back_to_forwarded_header():
    headers = _h({"forwarded": 'for=192.0.2.43:443;proto=https'})
    assert client_ip_from_headers(headers) == "192.0.2.43"


def test_forwarded_ipv6():
    headers = _h({"forwarded": 'for="[2001:db8::1]:443"'})
    assert client_ip_from_headers(headers) == "2001:db8::1"


def test_falls_back_to_peer_when_no_proxy_headers():
    assert client_ip_from_headers([], ("192.0.2.123", 51000)) == "192.0.2.123"


def test_returns_none_when_nothing_available():
    assert client_ip_from_headers([], None) is None


def test_user_agent_extraction():
    headers = _h({"user-agent": "Mozilla/5.0 pytest"})
    assert user_agent_from_headers(headers) == "Mozilla/5.0 pytest"
    assert user_agent_from_headers([]) is None
