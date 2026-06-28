"""
Bootstrap: Middleware Registry
All middleware configuration in one place.
"""

from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware


def register_middleware(app: FastAPI) -> None:
    """Attach all middleware to the FastAPI app in the correct order."""

    # Bug AL: previously this registered a permissive CORSMiddleware with
    # `allow_origins=["*"]` + `allow_credentials=True` (a CORS protocol
    # violation that browsers normally ignore, but it ALSO caused a
    # second CORS layer that could shadow the strict regex configured in
    # server.py). The single authoritative CORS layer now lives in
    # `backend/server.py` (origin allow-list + tightened *.replit.dev
    # regex). Do not re-introduce a wildcard CORSMiddleware here.

    # GZip compression for responses > 500 bytes
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # TI-003: Tenant context middleware — sets tenant_id from JWT
    # Must be added AFTER CORS (runs BEFORE route handlers due to LIFO)
    try:
        from core.security import JWT_ALGORITHM, JWT_SECRET
        from core.tenant_middleware import TenantContextMiddleware

        app.add_middleware(
            TenantContextMiddleware,
            jwt_secret=JWT_SECRET,
            jwt_algorithm=JWT_ALGORITHM,
        )
    except Exception:
        pass

    # APM / request-timing middleware (imported lazily to avoid circular deps)
    try:
        from apm_middleware import APMMiddleware

        app.add_middleware(APMMiddleware)
    except ImportError:
        pass

    # CDN cache-control headers
    try:
        from infra.cdn_headers import CDNHeaderMiddleware

        app.add_middleware(CDNHeaderMiddleware)
    except ImportError:
        pass

    # Security headers
    try:
        from infra.security_headers import SecurityHeadersMiddleware

        app.add_middleware(SecurityHeadersMiddleware)
    except ImportError:
        pass

    # Compression middleware (disabled - CDN/proxy handles compression)
    # Custom CompressionMiddleware conflicts with proxy layer which strips
    # Content-Encoding headers while keeping compressed body, causing
    # API clients to receive undecodable gzip bytes.
    # try:
    #     from compression_middleware import CompressionMiddleware
    #     app.add_middleware(CompressionMiddleware)
    # except ImportError:
    #     pass
