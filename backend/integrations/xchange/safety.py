"""Egress / SSRF guard for tenant-configurable outbound URLs.

Tenant admins can register webhook/CRS/ERP endpoints. Without a
guard, malicious or careless config could point our backend at
internal services (cloud metadata, intranet APIs). This module
rejects URLs that resolve to private/loopback/link-local ranges
unless an explicit allowlist override is provided.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

# Permit private targets only when explicitly enabled
# (e.g. local dev / on-prem partner over VPN).
_ALLOW_PRIVATE = os.getenv("XCHANGE_ALLOW_PRIVATE_EGRESS", "").lower() in {"1", "true", "yes"}
_EXTRA_ALLOWED_HOSTS = {
    h.strip().lower()
    for h in os.getenv("XCHANGE_EGRESS_ALLOWED_HOSTS", "").split(",")
    if h.strip()
}


class EgressDenied(ValueError):
    """Raised when an outbound URL is not permitted."""


def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # treat unparseable as unsafe
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def assert_safe_url(url: str) -> None:
    """Raise EgressDenied if URL targets a private/internal resource."""
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
