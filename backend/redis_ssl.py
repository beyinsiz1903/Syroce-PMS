"""
redis_ssl.py — Managed Redis (TLS / rediss://) connection helpers.

Managed Redis providers (DigitalOcean Managed Caching / Valkey, Heroku, etc.)
enforce TLS, so the operator-supplied ``REDIS_URL`` uses the ``rediss://`` scheme.
Three different client stacks consume that URL and each needs explicit handling:

* **redis-py** (cache_manager, security.auth_throttle, infra.redis_cluster,
  modules.event_bus.redis_pubsub) — ``redis.from_url`` builds an SSLConnection
  whose ``ssl_cert_reqs`` defaults to CERT_REQUIRED. The managed CA is usually
  not in the system trust store, so verification fails and every client silently
  falls back to its in-memory mode — which would split the event bus from the
  Celery workers. We append ``ssl_cert_reqs`` to the URL so the SSLConnection is
  created with the configured verification mode.
* **kombu broker** — only opens an SSL connection when ``broker_use_ssl`` is set.
* **celery redis result backend** — hard-refuses a ``rediss://`` URL unless
  ``redis_backend_use_ssl`` carries ``ssl_cert_reqs`` (raises
  "A rediss:// URL must have parameter ssl_cert_reqs").

Verification mode is configurable via ``REDIS_TLS_CERT_REQS``
(``none`` | ``optional`` | ``required``) and defaults to ``none``: TLS still
encrypts data in transit, but the server certificate is not verified against a
trust store. This is the pragmatic default for managed Redis reached over the
provider's private network, where shipping and trusting the provider CA in every
container is impractical. Set ``REDIS_TLS_CERT_REQS=required`` (with a properly
trusted CA) to harden.

All helpers are no-ops for plain ``redis://`` URLs, so Replit/local development is
unaffected.
"""

import os
import ssl
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_CERT_REQS_MAP = {
    "none": ssl.CERT_NONE,
    "optional": ssl.CERT_OPTIONAL,
    "required": ssl.CERT_REQUIRED,
}

_DEFAULT_CERT_REQS = "none"


def _configured_cert_reqs_str() -> str:
    """Return the configured ssl_cert_reqs token, validated against the map."""
    val = (os.environ.get("REDIS_TLS_CERT_REQS") or _DEFAULT_CERT_REQS).strip().lower()
    return val if val in _CERT_REQS_MAP else _DEFAULT_CERT_REQS


def is_tls_redis_url(url: str) -> bool:
    """True when ``url`` is a TLS Redis URL (rediss:// scheme)."""
    return bool(url) and url.strip().lower().startswith("rediss://")


def cert_reqs_constant() -> int:
    """Return the ssl.CERT_* constant for the configured verification mode."""
    return _CERT_REQS_MAP[_configured_cert_reqs_str()]


def normalize_redis_url_for_redis_py(url: str) -> str:
    """Ensure a rediss:// URL carries an ssl_cert_reqs query param for redis-py.

    No-op for plain redis:// URLs and when ssl_cert_reqs is already present.
    """
    if not is_tls_redis_url(url):
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if "ssl_cert_reqs" not in query:
        query["ssl_cert_reqs"] = _configured_cert_reqs_str()
    return urlunsplit(parts._replace(query=urlencode(query)))


def celery_ssl_conf(url: str):
    """Return the dict for celery broker_use_ssl / redis_backend_use_ssl.

    Returns ``None`` for non-TLS URLs so callers leave plain redis:// untouched.
    """
    if not is_tls_redis_url(url):
        return None
    return {"ssl_cert_reqs": cert_reqs_constant()}
