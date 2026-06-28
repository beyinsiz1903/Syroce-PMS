"""Egress / SSRF guard for tenant-configurable outbound URLs.

Tenant admins can register webhook/CRS/ERP endpoints. Without a
guard, malicious or careless config could point our backend at
internal services (cloud metadata, intranet APIs). This module
rejects URLs that resolve to private/loopback/link-local ranges
unless an explicit allowlist override is provided.

v109 Bug DAL round-7 follow-up: the original ``assert_safe_url``
performed a single DNS resolution and then handed the *hostname*
back to ``httpx.AsyncClient.post(url, ...)``. The library would
re-resolve the host, opening a TOCTOU/DNS-rebinding window where
a domain could resolve to a public IP at validation time and to
``169.254.169.254`` (or any private IP) milliseconds later when
``httpx`` actually connects. ``safe_post_async`` closes that
window: it resolves once, validates **every** returned address,
picks one as the pinned target, and configures ``httpx`` with a
custom ``httpcore`` network backend that rewrites the connect-time
hostname to the pinned IP. TLS SNI / cert verification still use
the original hostname, so HTTPS targets keep working unchanged.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

import httpcore
import httpx
from httpcore._backends.auto import AutoBackend

logger = logging.getLogger("integrations.xchange.safety")

# Permit private targets only when explicitly enabled
# (e.g. local dev / on-prem partner over VPN).
_ALLOW_PRIVATE = os.getenv("XCHANGE_ALLOW_PRIVATE_EGRESS", "").lower() in {"1", "true", "yes"}
_EXTRA_ALLOWED_HOSTS = {h.strip().lower() for h in os.getenv("XCHANGE_EGRESS_ALLOWED_HOSTS", "").split(",") if h.strip()}

# Default outbound timeout for safe_post_async / safe_request_async.
_DEFAULT_TIMEOUT = float(os.getenv("XCHANGE_EGRESS_TIMEOUT_SECONDS", "15") or "15")


class EgressDenied(ValueError):
    """Raised when an outbound URL is not permitted."""


def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # treat unparseable as unsafe
    return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved or addr.is_unspecified


def assert_safe_url(url: str) -> None:
    """Raise EgressDenied if URL targets a private/internal resource.

    Kept for backward compatibility with callers that only need a
    pre-flight validation. For network calls prefer ``safe_post_async``
    which additionally pins DNS to the validated IP (rebinding-safe).
    """
    if not url:
        raise EgressDenied("empty URL")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise EgressDenied(f"unsupported scheme: {parsed.scheme}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise EgressDenied("missing host")
    if host in _EXTRA_ALLOWED_HOSTS:
        return
    # Block obvious metadata/loopback hostnames upfront
    if host in {"localhost", "metadata", "metadata.google.internal"}:
        if not _ALLOW_PRIVATE:
            raise EgressDenied(f"host not allowed: {host}")
        return
    # Resolve and inspect every address
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise EgressDenied(f"dns failure: {e}") from e
    for info in infos:
        ip = info[4][0]
        if _is_private(ip) and not _ALLOW_PRIVATE:
            raise EgressDenied(f"egress to private address blocked: {host} → {ip}")


def _resolve_and_pin(url: str) -> tuple[str, str, int]:
    """Validate URL + DNS, return (host, pinned_ip, port).

    Resolves the hostname **once** and validates every returned
    address. If any address is private (and override disabled) the
    request is rejected — this prevents an attacker from registering
    a domain whose A-record set mixes one public and one internal IP
    (most resolvers return them in random order, so even
    ``socket.getaddrinfo`` with a single check is not safe).
    """
    if not url:
        raise EgressDenied("empty URL")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise EgressDenied(f"unsupported scheme: {parsed.scheme}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise EgressDenied("missing host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    if host in _EXTRA_ALLOWED_HOSTS:
        # Operator opt-in. Still resolve so we have a pin.
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise EgressDenied(f"dns failure: {e}") from e
        return host, infos[0][4][0], port

    if host in {"localhost", "metadata", "metadata.google.internal"}:
        if not _ALLOW_PRIVATE:
            raise EgressDenied(f"host not allowed: {host}")

    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise EgressDenied(f"dns failure: {e}") from e

    resolved = sorted({info[4][0] for info in infos})
    if not resolved:
        raise EgressDenied(f"no addresses for {host}")
    for ip in resolved:
        if _is_private(ip) and not _ALLOW_PRIVATE:
            raise EgressDenied(f"egress to private address blocked: {host} → {ip}")
    return host, resolved[0], port


class _PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    """httpcore backend that redirects ``connect_tcp(host, …)`` to a pinned IP.

    The TLS handshake (started later by ``httpcore`` against the original
    hostname) still sees the correct SNI and validates the certificate
    against the hostname — only the underlying TCP destination is pinned.
    """

    def __init__(self, host_to_ip: dict[str, str]):
        self._inner = AutoBackend()
        self._map = {h.lower(): ip for h, ip in host_to_ip.items()}

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: list | None = None,
    ):
        target = self._map.get(host.lower(), host)
        return await self._inner.connect_tcp(
            target,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(self, *args, **kwargs):  # pragma: no cover
        return await self._inner.connect_unix_socket(*args, **kwargs)

    async def sleep(self, seconds: float) -> None:
        return await self._inner.sleep(seconds)


def _pinned_transport(host: str, ip: str) -> httpx.AsyncHTTPTransport:
    """Build an ``httpx.AsyncHTTPTransport`` that pins DNS for ``host`` → ``ip``."""
    transport = httpx.AsyncHTTPTransport()
    # Replace the pool's default network backend with a pinned one.
    # ``_pool`` and ``_network_backend`` are private attrs but stable in
    # httpcore 1.x — we own version pinning in requirements/api.txt.
    transport._pool._network_backend = _PinnedNetworkBackend({host: ip})
    return transport


def assert_safe_host(host: str, port: int) -> str:
    """Validate a non-HTTP egress target (e.g. SMTP, IMAP, FTP).

    Resolves DNS once, ensures every returned IP is public (or operator
    has set ``XCHANGE_ALLOW_PRIVATE_EGRESS=1`` / added the host to
    ``XCHANGE_EGRESS_ALLOWED_HOSTS``), and returns a pinned IP that the
    caller should use for its actual TCP connect.

    Returning the pinned IP and asking the caller to connect to that IP
    closes the same DNS-rebinding window that ``safe_post_async`` closes
    for HTTP. SMTP servers don't validate SNI/cert by IP, so this is a
    safe drop-in for ``smtplib.SMTP(host, port) → smtplib.SMTP(ip, port)``
    (callers should keep the original ``msg["From"]/To`` headers).
    """
    if not host:
        raise EgressDenied("empty host")
    host_l = host.lower()
    if host_l in _EXTRA_ALLOWED_HOSTS:
        try:
            infos = socket.getaddrinfo(host_l, port, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise EgressDenied(f"dns failure: {e}") from e
        return infos[0][4][0]
    if host_l in {"localhost", "metadata", "metadata.google.internal"}:
        if not _ALLOW_PRIVATE:
            raise EgressDenied(f"host not allowed: {host_l}")
    try:
        infos = socket.getaddrinfo(host_l, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise EgressDenied(f"dns failure: {e}") from e
    resolved = sorted({info[4][0] for info in infos})
    if not resolved:
        raise EgressDenied(f"no addresses for {host_l}")
    for ip in resolved:
        if _is_private(ip) and not _ALLOW_PRIVATE:
            raise EgressDenied(f"egress to private address blocked: {host_l} → {ip}")
    return resolved[0]


async def safe_request_async(
    method: str,
    url: str,
    *,
    timeout: float | None = None,
    **httpx_kwargs,
) -> httpx.Response:
    """Make an outbound HTTP request safely (rebinding-protected).

    Resolves DNS once, validates every returned IP, then issues the
    request through an ``httpx.AsyncClient`` whose network backend is
    pinned to the validated IP. Raises :class:`EgressDenied` if the URL
    fails validation; ``httpx`` exceptions propagate unchanged.
    """
    host, pinned_ip, _ = _resolve_and_pin(url)
    transport = _pinned_transport(host, pinned_ip)
    timeout_value = timeout if timeout is not None else _DEFAULT_TIMEOUT
    async with httpx.AsyncClient(transport=transport, timeout=timeout_value) as client:
        return await client.request(method, url, **httpx_kwargs)


async def safe_post_async(
    url: str,
    *,
    timeout: float | None = None,
    **httpx_kwargs,
) -> httpx.Response:
    """Convenience wrapper: ``safe_request_async("POST", url, ...)``."""
    return await safe_request_async("POST", url, timeout=timeout, **httpx_kwargs)
