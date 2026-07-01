"""
Common — Per-request audit context (client IP + user-agent).

The audit trail must answer "who, when, from which IP/device" for every
critical mutation. FastAPI route handlers and the service/decorator audit
write path do not always carry the raw `Request`, so we stash the client
IP and user-agent in contextvars at the ASGI boundary (TenantContextMiddleware)
and read them back wherever an audit record is written.

Proxy-safe IP extraction mirrors the existing best-effort helper in
finance/folio_einvoice_public.py: take the left-most x-forwarded-for hop
(the original client) when present, otherwise the direct peer.
"""

from contextvars import ContextVar

_ip_ctx: ContextVar[str | None] = ContextVar("audit_client_ip", default=None)
_ua_ctx: ContextVar[str | None] = ContextVar("audit_user_agent", default=None)

# User-agent strings can be arbitrarily long; cap what we persist so a
# crafted header can't bloat audit rows.
_MAX_UA_LEN = 512


def set_request_context(ip: str | None, user_agent: str | None) -> None:
    """Set the current request's client IP and user-agent."""
    _ip_ctx.set(ip or None)
    if user_agent:
        user_agent = user_agent[:_MAX_UA_LEN]
    _ua_ctx.set(user_agent or None)


def clear_request_context() -> None:
    """Clear the per-request context (called in middleware `finally`)."""
    _ip_ctx.set(None)
    _ua_ctx.set(None)


def get_client_ip() -> str | None:
    """Return the captured client IP for the current request, or None."""
    return _ip_ctx.get()


def get_user_agent() -> str | None:
    """Return the captured user-agent for the current request, or None."""
    return _ua_ctx.get()


def client_ip_from_headers(raw_headers: list, peer: tuple | None = None) -> str | None:
    """Proxy-safe client IP from raw ASGI headers.

    Prefers the left-most `x-forwarded-for` hop (the original client). When no
    XFF header is present (e.g. a direct connection without a proxy), falls back
    to the ASGI peer address (`scope["client"]` -> `(host, port)`). Returns None
    only when neither source yields an address.
    """
    xff = None
    forwarded = None
    real_ip = None
    for key, value in raw_headers:
        if key == b"x-forwarded-for":
            try:
                xff = value.decode("latin-1")
            except Exception:
                xff = None
        elif key == b"x-real-ip":
            try:
                real_ip = value.decode("latin-1")
            except Exception:
                real_ip = None
        elif key == b"forwarded":
            try:
                forwarded = value.decode("latin-1")
            except Exception:
                forwarded = None
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    if real_ip and real_ip.strip():
        return real_ip.strip()
    if forwarded:
        # RFC 7239: take the first `for=` token.
        for part in forwarded.split(";"):
            part = part.strip()
            if part.lower().startswith("for="):
                val = part[4:].strip().strip('"')
                # IPv6 is wrapped like for="[2001:db8::1]:443"
                if val.startswith("["):
                    val = val[1:].split("]")[0]
                elif ":" in val and val.count(":") == 1:
                    val = val.split(":")[0]
                if val:
                    return val
    # Direct peer fallback (no proxy headers present).
    if peer and len(peer) >= 1 and peer[0]:
        return str(peer[0])
    return None


def user_agent_from_headers(raw_headers: list) -> str | None:
    """Extract the user-agent string from raw ASGI headers."""
    for key, value in raw_headers:
        if key == b"user-agent":
            try:
                return value.decode("latin-1") or None
            except Exception:
                return None
    return None
