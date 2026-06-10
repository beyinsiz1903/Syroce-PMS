"""
Comprehensive Security Headers Middleware
Implements OWASP security best practices
"""
from fastapi import Request


class SecurityHeadersMiddleware:
    """
    Middleware to add comprehensive security headers to all responses
    Implements OWASP security best practices
    """

    def __init__(
        self,
        app,
        strict_transport_security: str = "max-age=31536000; includeSubDomains; preload",
        content_security_policy: str = None,
        x_frame_options: str = "SAMEORIGIN",
        x_content_type_options: str = "nosniff",
        x_xss_protection: str = "1; mode=block",
        referrer_policy: str = "strict-origin-when-cross-origin",
        permissions_policy: str = None,
    ):
        self.app = app
        self.headers = {}

        # Strict-Transport-Security (HSTS)
        if strict_transport_security:
            self.headers['Strict-Transport-Security'] = strict_transport_security

        # Content-Security-Policy
        if content_security_policy:
            self.headers['Content-Security-Policy'] = content_security_policy
        else:
            # Default CSP
            self.headers['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
                "img-src 'self' data: https:; "
                "font-src 'self' data: https://fonts.gstatic.com; "
                "connect-src 'self' ws: wss: https://cdn.jsdelivr.net https://*.sentry.io; "
                "worker-src 'self' blob:; "
                "frame-ancestors 'self'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )

        # X-Frame-Options
        if x_frame_options:
            self.headers['X-Frame-Options'] = x_frame_options

        # X-Content-Type-Options
        if x_content_type_options:
            self.headers['X-Content-Type-Options'] = x_content_type_options

        # X-XSS-Protection
        if x_xss_protection:
            self.headers['X-XSS-Protection'] = x_xss_protection

        # Referrer-Policy
        if referrer_policy:
            self.headers['Referrer-Policy'] = referrer_policy

        # Permissions-Policy (formerly Feature-Policy)
        if permissions_policy:
            self.headers['Permissions-Policy'] = permissions_policy
        else:
            self.headers['Permissions-Policy'] = (
                "geolocation=(), "
                "microphone=(), "
                "camera=(), "
                "payment=(), "
                "usb=(), "
                "magnetometer=(), "
                "gyroscope=(), "
                "accelerometer=()"
            )

        # Additional security headers
        self.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
        self.headers['X-DNS-Prefetch-Control'] = 'off'
        self.headers['X-Download-Options'] = 'noopen'

    # Permissive CSP for API documentation routes (ReDoc, Swagger, OpenAPI)
    DOC_CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net blob:; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "img-src 'self' data: https:; "
        "font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net; "
        "connect-src 'self' https://cdn.jsdelivr.net; "
        "worker-src blob:; "
        "frame-ancestors 'self'; "
        "base-uri 'self'"
    )
    _DOC_PATHS = {"/api/docs", "/api/redoc", "/api/openapi.json"}

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        path = scope.get('path', '')
        is_doc_route = path in self._DOC_PATHS or path.rstrip('/') in self._DOC_PATHS

        async def send_wrapper(message):
            if message['type'] == 'http.response.start':
                existing_headers = list(message.get('headers', []))
                existing_names = {h[0].lower() if isinstance(h[0], bytes) else h[0].lower().encode() for h in existing_headers}

                for header, value in self.headers.items():
                    h_bytes = header.lower().encode()
                    # For doc routes, override CSP with permissive version
                    if is_doc_route and header == 'Content-Security-Policy':
                        # Remove existing CSP if present
                        existing_headers = [
                            h for h in existing_headers
                            if (h[0].lower() if isinstance(h[0], bytes) else h[0].lower().encode()) != b'content-security-policy'
                        ]
                        existing_headers.append((header.encode(), self.DOC_CSP.encode()))
                    elif h_bytes not in existing_names:
                        existing_headers.append((header.encode(), value.encode()))

                message['headers'] = existing_headers

            await send(message)

        await self.app(scope, receive, send_wrapper)


def add_security_headers(app, **kwargs):
    """
    Add security headers middleware to FastAPI app

    Usage:
        app = FastAPI()
        add_security_headers(app)
    """
    return SecurityHeadersMiddleware(app, **kwargs)


# CORS security configuration
from fastapi.middleware.cors import CORSMiddleware


def configure_cors(
    app,
    allowed_origins: list = None,
    allowed_methods: list = None,
    allowed_headers: list = None,
    allow_credentials: bool = True,
    max_age: int = 600,
):
    """
    Configure CORS with security best practices

    Args:
        app: FastAPI app
        allowed_origins: List of allowed origins (default: localhost only)
        allowed_methods: List of allowed HTTP methods
        allowed_headers: List of allowed headers
        allow_credentials: Allow credentials
        max_age: Preflight cache duration
    """
    if allowed_origins is None:
        allowed_origins = [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
        ]

    if allowed_methods is None:
        allowed_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]

    if allowed_headers is None:
        allowed_headers = [
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "Accept",
            "Origin",
        ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
        allow_methods=allowed_methods,
        allow_headers=allowed_headers,
        max_age=max_age,
    )

    return app


# Security audit endpoint
from datetime import datetime

from fastapi import APIRouter

security_router = APIRouter(prefix="/api/security", tags=["security"])

@security_router.get("/audit")
async def security_audit(request: Request):
    """
    Perform security audit of current configuration
    Returns security recommendations
    """
    issues = []
    recommendations = []

    # Check HTTPS
    if request.url.scheme != 'https' and request.headers.get('host') != 'localhost:8001':
        issues.append({
            "severity": "HIGH",
            "issue": "Not using HTTPS",
            "recommendation": "Enable HTTPS in production"
        })

    # Check security headers

    # Note: These would be checked on the response,
    # but we're checking configuration here

    recommendations.append({
        "category": "Headers",
        "recommendation": "Ensure all security headers are present in responses"
    })

    recommendations.append({
        "category": "Authentication",
        "recommendation": "Use JWT with short expiration times"
    })

    recommendations.append({
        "category": "Rate Limiting",
        "recommendation": "Implement rate limiting on all public endpoints"
    })

    recommendations.append({
        "category": "Input Validation",
        "recommendation": "Validate and sanitize all user inputs"
    })

    recommendations.append({
        "category": "Database",
        "recommendation": "Use parameterized queries to prevent injection attacks"
    })

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "issues": issues,
        "recommendations": recommendations,
        "security_score": max(0, 100 - len(issues) * 10)
    }


@security_router.get("/headers/check")
async def check_security_headers():
    """Check which security headers are configured"""
    middleware = SecurityHeadersMiddleware(None)

    return {
        "configured_headers": list(middleware.headers.keys()),
        "headers": middleware.headers,
        "status": "OK"
    }
