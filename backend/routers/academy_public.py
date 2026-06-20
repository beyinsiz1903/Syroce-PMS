"""Public (unauthenticated) Academy certificate verification.

A third party (audit, HR, an external recruiter) can confirm that a Syroce
Academy certificate is genuine by entering the verification code printed on the
PDF (`SYR-ACAD-XXXXXXXXXX`).

Security model:
  - NO JWT and NO tenant context. The endpoint lives under `/api/academy/verify`
    and declares no `Depends(get_current_user)`; the tenant middleware sets no
    context for it. The verification code itself is the opaque, globally-unique
    bearer capability — it is format-validated before any DB read, so the route
    is not an enumeration oracle.
  - Data minimization: only course title, department label, issue date, validity
    and a MASKED recipient name are returned. No PII (e-mail, user_id, tenant_id,
    score) ever leaves this surface.
  - IP rate-limited (Redis-backed, shared across instances) so the public,
    low-cost surface cannot be abused to brute-force codes or generate load.
"""
from __future__ import annotations

import ipaddress
import logging
import os

from fastapi import APIRouter, HTTPException, Request

from cache_manager import cache as _cache
from core import academy

logger = logging.getLogger("academy_public")

router = APIRouter(prefix="/api/academy", tags=["academy-public"])

# IP-based rate limit: 30 verification attempts per 10 minutes per IP. Generous
# for legitimate batch checks (an HR reviewer with several certificates) yet far
# too tight to brute-force the opaque code space.
_RL_WINDOW_SEC = 600
_RL_MAX_HITS = 30

_DEFAULT_TRUSTED_CIDRS = "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"


def _parse_trusted_proxies() -> list:
    raw = os.environ.get("TRUSTED_PROXIES", _DEFAULT_TRUSTED_CIDRS)
    networks = []
    for token in (raw or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            networks.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            logger.warning("[academy_public] invalid TRUSTED_PROXIES entry: %r", token)
    return networks


_TRUSTED_PROXIES = _parse_trusted_proxies()


def _is_trusted_proxy(ip_str: str) -> bool:
    if not ip_str or not _TRUSTED_PROXIES:
        return False
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in net for net in _TRUSTED_PROXIES)


def _client_ip(request: Request) -> str:
    """Client IP for rate-limiting. Trust x-forwarded-for ONLY when the direct
    connection comes from a trusted proxy; otherwise the header is spoofable."""
    direct_ip = request.client.host if request.client else ""
    xff = request.headers.get("x-forwarded-for", "")
    if xff and _is_trusted_proxy(direct_ip):
        first = xff.split(",")[0].strip()
        if first:
            return first
    return direct_ip or "unknown"


def _rl_check(ip: str) -> bool:
    """True = allowed, False = limit exceeded. Fail-open when the counter backend
    is unavailable (verification is read-only and low-risk)."""
    count = _cache.incr_with_ttl(f"academy:verify:rl:{ip}", _RL_WINDOW_SEC)
    if count == 0:
        logger.warning("[academy_public] rate-limit counter unavailable, allowing %s", ip)
        return True
    return count <= _RL_MAX_HITS


@router.get("/verify/{code}")
async def verify_certificate(code: str, request: Request) -> dict:
    """Public certificate verification by code. Returns minimal, PII-safe fields.

    - 200 ``{valid: true, ...}`` when the code matches an issued certificate.
    - 200 ``{valid: false}`` when the code is well-formed but not found, OR is
      malformed — a uniform negative response (no format/existence oracle).
    - 429 when the per-IP rate limit is exceeded.
    """
    if not _rl_check(_client_ip(request)):
        raise HTTPException(
            status_code=429,
            detail="Çok fazla deneme — lütfen birazdan tekrar deneyin.",
        )
    cert = await academy.get_certificate_by_code((code or "").strip().upper())
    if not cert:
        return {"valid": False}
    return academy.public_certificate_view(cert)
