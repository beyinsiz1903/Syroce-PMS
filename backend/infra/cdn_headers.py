"""
CDN Cache Headers Middleware
Optimizes browser and CDN caching with proper headers
"""
from fastapi import Request, Response
import os
from datetime import datetime, timedelta

# Cache durations (in seconds)
CACHE_DURATIONS = {
    # Static assets - long cache
    'images': 31536000,      # 1 year
    'fonts': 31536000,       # 1 year
    'css': 31536000,         # 1 year
    'js': 31536000,          # 1 year
    'icons': 31536000,       # 1 year
    
    # API responses
    'api_public': 300,       # 5 minutes
    'api_private': 0,        # No cache
    'api_reports': 3600,     # 1 hour
    
    # HTML
    'html': 0,               # No cache (always fresh)
    'manifest': 86400,       # 1 day
}

# File extensions mapping
FILE_EXTENSIONS = {
    '.jpg': 'images',
    '.jpeg': 'images',
    '.png': 'images',
    '.gif': 'images',
    '.webp': 'images',
    '.svg': 'images',
    '.ico': 'icons',
    '.woff': 'fonts',
    '.woff2': 'fonts',
    '.ttf': 'fonts',
    '.eot': 'fonts',
    '.css': 'css',
    '.js': 'js',
    '.json': 'manifest',
    '.html': 'html',
}


def get_cache_headers(path: str, cache_type: str = None) -> dict:
    """
    Get appropriate cache headers for a given path
    
    Args:
        path: File path or URL path
        cache_type: Override cache type (optional)
        
    Returns:
        dict of cache headers
    """
    # Determine cache type from file extension if not provided
    if cache_type is None:
        ext = os.path.splitext(path)[1].lower()
        cache_type = FILE_EXTENSIONS.get(ext, 'api_public')
    
    duration = CACHE_DURATIONS.get(cache_type, 0)
    
    headers = {}
    
    if duration > 0:
        # Long-term caching
        headers['Cache-Control'] = f'public, max-age={duration}, immutable'
        
        # Set Expires header
        expires = datetime.utcnow() + timedelta(seconds=duration)
        headers['Expires'] = expires.strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        # ETag for validation
        headers['ETag'] = f'"{hash(path)}_{datetime.utcnow().timestamp()}"'
        
        # CDN headers
        headers['CDN-Cache-Control'] = f'max-age={duration}'
        headers['Surrogate-Control'] = f'max-age={duration}'
        
    else:
        # No caching
        headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        headers['Pragma'] = 'no-cache'
        headers['Expires'] = '0'
    
    return headers


def add_cache_headers_middleware(app):
    """
    Middleware to add cache headers to responses
    """
    @app.middleware("http")
    async def cache_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        
        path = request.url.path
        
        # Determine cache type based on path
        if path.startswith('/api/reports'):
            cache_type = 'api_reports'
        elif path.startswith('/api/'):
            # Check if it's a mutation (POST, PUT, DELETE)
            if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
                cache_type = 'api_private'
            else:
                cache_type = 'api_public'
        elif any(path.endswith(ext) for ext in FILE_EXTENSIONS.keys()):
            # Static assets
            ext = os.path.splitext(path)[1].lower()
            cache_type = FILE_EXTENSIONS.get(ext, 'api_public')
        else:
            cache_type = 'html'
        
        # Get and apply cache headers
        cache_headers = get_cache_headers(path, cache_type)
        
        for header, value in cache_headers.items():
            response.headers[header] = value
        
        # Add security headers
        if not response.headers.get('X-Content-Type-Options'):
            response.headers['X-Content-Type-Options'] = 'nosniff'
        
        if not response.headers.get('X-Frame-Options'):
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        
        return response
    
    return app


class CacheableResponse(Response):
    """
    Custom Response class with automatic cache headers
    """
    def __init__(
        self,
        content=None,
        status_code=200,
        headers=None,
        media_type=None,
        background=None,
        cache_type='api_public',
    ):
        super().__init__(content, status_code, headers, media_type, background)
        
        # Add cache headers
        cache_headers = get_cache_headers('', cache_type)
        for header, value in cache_headers.items():
            self.headers[header] = value


def cache_response(cache_type='api_public'):
    """
    Decorator to add cache headers to endpoint responses
    
    Usage:
        @app.get("/api/data")
        @cache_response(cache_type='api_reports')
        async def get_data():
            return {"data": "..."}
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            # If result is already a Response, add headers
            if isinstance(result, Response):
                cache_headers = get_cache_headers('', cache_type)
                for header, value in cache_headers.items():
                    result.headers[header] = value
                return result
            
            # Otherwise, wrap in CacheableResponse
            return CacheableResponse(
                content=result,
                cache_type=cache_type
            )
        
        return wrapper
    return decorator


# Precomputed ETags for common responses
ETAG_CACHE = {}

def get_or_compute_etag(key: str, data: any) -> str:
    """
    Get or compute ETag for cacheable data
    """
    if key in ETAG_CACHE:
        return ETAG_CACHE[key]
    
    # Compute ETag
    etag = f'"{hash(str(data))}"'
    ETAG_CACHE[key] = etag
    
    # Clean old ETags if cache gets too large
    if len(ETAG_CACHE) > 1000:
        # Remove oldest 20%
        keys_to_remove = list(ETAG_CACHE.keys())[:200]
        for k in keys_to_remove:
            del ETAG_CACHE[k]
    
    return etag


def check_etag(request: Request, etag: str) -> bool:
    """
    Check if client's ETag matches current ETag
    Returns True if match (304 Not Modified should be returned)
    """
    client_etag = request.headers.get('If-None-Match')
    return client_etag == etag


# Compression headers
def add_compression_headers(response: Response):
    """Add compression-related headers"""
    response.headers['Vary'] = 'Accept-Encoding'
    return response
