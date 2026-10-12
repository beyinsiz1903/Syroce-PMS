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
from unittest.mock import AsyncMock

import httpcore
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


def test_dual_stack_prefers_ipv4_and_keeps_validated_ipv6(monkeypatch):
    lookup = lambda *args, **kwargs: _fake_addrinfo(["2a03:2880:f084:10d:face:b00c:0:2", "157.240.1.1"])
    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    _, targets, _ = safety._resolve_targets("https://graph.facebook.com")
    assert targets == ("157.240.1.1", "2a03:2880:f084:10d:face:b00c:0:2")


@pytest.mark.asyncio
async def test_connect_falls_back_only_to_validated_ip_without_dns(monkeypatch):
    backend = safety._PinnedNetworkBackend({"example.com": ("1.1.1.1", "8.8.8.8")})
    stream = object()
    backend._inner.connect_tcp = AsyncMock(side_effect=[httpcore.ConnectError("offline"), stream])
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: pytest.fail("must not resolve again"))
    assert await backend.connect_tcp("example.com", 443, timeout=10) is stream
    assert [call.args[0] for call in backend._inner.connect_tcp.call_args_list] == ["1.1.1.1", "8.8.8.8"]
    with pytest.raises(httpcore.ConnectError, match="Unvalidated"):
        await backend.connect_tcp("other.example", 443)


@pytest.mark.asyncio
async def test_connect_exhaustion_propagates():
    backend = safety._PinnedNetworkBackend({"example.com": ("1.1.1.1", "8.8.8.8")})
    backend._inner.connect_tcp = AsyncMock(side_effect=httpcore.ConnectError("offline"))
    with pytest.raises(httpcore.ConnectError):
        await backend.connect_tcp("example.com", 443, timeout=10)
    assert backend._inner.connect_tcp.await_count == 2


@pytest.mark.asyncio
async def test_does_not_retry_non_connect_errors():
    backend = safety._PinnedNetworkBackend({"example.com": ("1.1.1.1", "8.8.8.8")})
    backend._inner.connect_tcp = AsyncMock(side_effect=httpcore.WriteError("ambiguous"))
    with pytest.raises(httpcore.WriteError):
        await backend.connect_tcp("example.com", 443, timeout=10)
    assert backend._inner.connect_tcp.await_count == 1


def test_dual_stack_private_record_blocks_all_targets(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: _fake_addrinfo(["1.1.1.1", "::1"]))
    with pytest.raises(safety.EgressDenied):
        safety._resolve_targets("https://example.com")
