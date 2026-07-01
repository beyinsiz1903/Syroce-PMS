"""Regression test for the v109 round-7 DNS-rebinding closure.

These tests exercise ``backend.integrations.xchange.safety`` with three
scenarios:
  1. Public hostname  → ``_resolve_and_pin`` succeeds, ``EgressDenied`` not raised.
  2. Private IP literal → ``EgressDenied`` raised at validation time.
  3. ``localhost`` → ``EgressDenied`` raised (unless override set).
  4. Hostname whose A-record set MIXES public + private addresses → ``EgressDenied``
     raised even though one of the addresses is public (this is the actual
     rebinding payload — most resolvers return them in random order, so a
     "first IP wins" check is unsafe).
  5. ``assert_safe_host`` (SMTP variant) parallels (1)+(2)+(3).

We monkeypatch ``socket.getaddrinfo`` so the test does not depend on real DNS.
"""
from __future__ import annotations

import socket

import pytest

from integrations.xchange import safety


def _fake_addrinfo(addresses):
    """Build a fake ``getaddrinfo`` return value for the given IP list."""
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))
        for ip in addresses
    ]


def test_resolve_and_pin_accepts_public(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port, **kw: _fake_addrinfo(["93.184.216.34"]),
    )
    host, ip, port = safety._resolve_and_pin("https://example.com/api")
    assert host == "example.com"
    assert ip == "93.184.216.34"
    assert port == 443


def test_resolve_and_pin_rejects_private(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port, **kw: _fake_addrinfo(["10.0.0.5"]),
    )
    with pytest.raises(safety.EgressDenied) as ei:
        safety._resolve_and_pin("https://intranet.example/api")
    assert "private" in str(ei.value).lower()


def test_resolve_and_pin_rejects_metadata(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port, **kw: _fake_addrinfo(["169.254.169.254"]),
    )
    with pytest.raises(safety.EgressDenied):
        safety._resolve_and_pin("http://attacker.example/api")


def test_resolve_and_pin_rejects_localhost(monkeypatch):
    # _ALLOW_PRIVATE is False by default
    with pytest.raises(safety.EgressDenied):
        safety._resolve_and_pin("http://localhost:8080/api")


def test_rebinding_mixed_record_set_blocked(monkeypatch):
    """The actual rebinding payload: A-record set has BOTH public AND private IPs.

    Even if a "first IP wins" check picked the public one, our policy resolves
    once and validates ALL addresses → request rejected.
    """
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port, **kw: _fake_addrinfo(["1.1.1.1", "169.254.169.254"]),
    )
    with pytest.raises(safety.EgressDenied) as ei:
        safety._resolve_and_pin("https://rebind.attacker.example/api")
    assert "169.254.169.254" in str(ei.value)


def test_assert_safe_host_smtp_public(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port, **kw: _fake_addrinfo(["35.190.247.13"]),
    )
    ip = safety.assert_safe_host("smtp.gmail.com", 587)
    assert ip == "35.190.247.13"


def test_assert_safe_host_smtp_private_blocked(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port, **kw: _fake_addrinfo(["192.168.1.10"]),
    )
    with pytest.raises(safety.EgressDenied):
        safety.assert_safe_host("smtp.intranet.local", 25)


def test_assert_safe_host_smtp_mixed_blocked(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port, **kw: _fake_addrinfo(["8.8.8.8", "10.0.0.1"]),
    )
    with pytest.raises(safety.EgressDenied):
        safety.assert_safe_host("rebind-smtp.attacker.example", 587)


def test_assert_safe_host_empty_rejected():
    with pytest.raises(safety.EgressDenied):
        safety.assert_safe_host("", 587)
