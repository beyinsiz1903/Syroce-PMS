"""
Rate Limiting Middleware for API Protection
Prevents abuse and ensures fair resource usage
"""

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict, Tuple
import time
import redis
import os
import logging
from collections import defaultdict
import hashlib

logger = logging.getLogger(__name__)

class RateLimiter:
    """Redis-based rate limiter with sliding window"""
    
    def __init__(self):
        self.redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        try:
            self.client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            self.client.ping()
            self.enabled = True
            logger.info("✅ Rate limiter connected to Redis")
        except Exception as e:
            logger.warning(f"⚠️ Redis not available for rate limiting: {e}")
            self.enabled = False
            self.client = None
            # Fallback to in-memory rate limiting
            self.memory_store = defaultdict(list)
    
    def _get_key(self, identifier: str, endpoint: str) -> str:
        """Generate Redis key for rate limiting"""
        return f"ratelimit:{identifier}:{endpoint}"
    
    def check_rate_limit(
        self,
        identifier: str,
        endpoint: str,
        limit: int,
        window: int
    ) -> Tuple[bool, Dict]:
        """
        Check if request is within rate limit
        
        Args:
            identifier: User/IP identifier
            endpoint: API endpoint
            limit: Number of requests allowed
            window: Time window in seconds
        
        Returns:
            (allowed, info_dict)
        """
        if self.enabled:
            return self._check_redis(identifier, endpoint, limit, window)
        else:
            return self._check_memory(identifier, endpoint, limit, window)
    
    def _check_redis(
        self,
        identifier: str,
        endpoint: str,
        limit: int,
        window: int
    ) -> Tuple[bool, Dict]:
        """Redis-based rate limiting with sliding window"""
        key = self._get_key(identifier, endpoint)
        now = time.time()
        window_start = now - window
        
        try:
            # Remove old entries
            self.client.zremrangebyscore(key, 0, window_start)
            
            # Count current requests
            current_count = self.client.zcard(key)
            
            if current_count < limit:
                # Add new request
                self.client.zadd(key, {str(now): now})
                self.client.expire(key, window)
                
                return True, {
                    'remaining': limit - current_count - 1,
                    'limit': limit,
                    'reset': int(now + window)
                }
            else:
                # Rate limit exceeded
                oldest = self.client.zrange(key, 0, 0, withscores=True)
                reset_time = int(oldest[0][1] + window) if oldest else int(now + window)
                
                return False, {
                    'remaining': 0,
                    'limit': limit,
                    'reset': reset_time
                }
                
        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            # On error, allow request
            return True, {
                'remaining': limit,
                'limit': limit,
                'reset': int(now + window)
            }
    
    def _check_memory(
        self,
        identifier: str,
        endpoint: str,
        limit: int,
        window: int
    ) -> Tuple[bool, Dict]:
        """In-memory fallback rate limiting"""
        key = f"{identifier}:{endpoint}"
        now = time.time()
        window_start = now - window
        
        # Clean old requests
        self.memory_store[key] = [
            req_time for req_time in self.memory_store[key]
            if req_time > window_start
        ]
        
        current_count = len(self.memory_store[key])
        
        if current_count < limit:
            self.memory_store[key].append(now)
            return True, {
                'remaining': limit - current_count - 1,
                'limit': limit,
                'reset': int(now + window)
            }
        else:
            reset_time = int(self.memory_store[key][0] + window)
            return False, {
                'remaining': 0,
                'limit': limit,
                'reset': reset_time
            }


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting
    
    Rate limit tiers:
    - Guest/Anonymous: 20 req/min
    - Authenticated users: 100 req/min
    - Admin users: 500 req/min
    - Special endpoints (reports, exports): 10 req/min
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.limiter = RateLimiter()
        
        # Define rate limits for different endpoint categories
        self.rate_limits = {
            'default': (100, 60),  # 100 requests per minute
            'auth': (10, 60),  # 10 login attempts per minute
            'export': (10, 60),  # 10 exports per minute
            'report': (20, 60),  # 20 report requests per minute
            'write': (50, 60),  # 50 write operations per minute
            'anonymous': (20, 60),  # 20 requests per minute for anonymous
            'admin': (500, 60),  # 500 requests per minute for admin
        }
        
        # Endpoint patterns
        self.endpoint_categories = {
            '/api/auth': 'auth',
            '/api/export': 'export',
            '/api/reports': 'report',
            '/api/dashboard': 'report',
            '/api/executive': 'report',
        }
    
    def _get_identifier(self, request: Request) -> str:
        """Get unique identifier for request (user_id or IP)"""
        # Try to get user from token
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            # Extract user identifier from token (simplified)
            token = auth_header.split(' ')[1]
            # Hash token for privacy
            return hashlib.sha256(token.encode()).hexdigest()[:16]
        
        # Fallback to IP address
        forwarded = request.headers.get('X-Forwarded-For')
        if forwarded:
            return forwarded.split(',')[0].strip()
        
        client_host = request.client.host if request.client else 'unknown'
        return client_host
    
    def _get_rate_limit(self, path: str, user_role: str = None) -> Tuple[int, int]:
        """Get rate limit for endpoint"""
        # Admin bypass
        if user_role == 'admin':
            return self.rate_limits['admin']
        
        # Check endpoint category
        for pattern, category in self.endpoint_categories.items():
            if path.startswith(pattern):
                return self.rate_limits[category]
        
        # Check if write operation
        if any(path.startswith(p) for p in ['/api/pms/bookings', '/api/folio', '/api/frontdesk']):
            return self.rate_limits['write']
        
        # Default rate limit
        return self.rate_limits['default']
    
    def _is_whitelisted(self, path: str) -> bool:
        """Check if endpoint is whitelisted from rate limiting"""
        whitelist = [
            '/api/health',
            '/api/ping',
            '/docs',
            '/openapi.json',
            '/api/status',
        ]
        return any(path.startswith(w) for w in whitelist)
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting"""
        path = request.url.path
        
        # Skip whitelisted endpoints
        if self._is_whitelisted(path):
            return await call_next(request)
        
        # Get identifier and rate limit
        identifier = self._get_identifier(request)
        
        # Try to get user role (simplified - in real app, decode token)
        user_role = None  # Would extract from JWT token
        
        limit, window = self._get_rate_limit(path, user_role)
        
        # Check rate limit
        allowed, info = self.limiter.check_rate_limit(
            identifier,
            path,
            limit,
            window
        )
        
        if not allowed:
            # Rate limit exceeded
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    'error': 'Rate limit exceeded',
                    'limit': info['limit'],
                    'reset': info['reset'],
                    'retry_after': info['reset'] - int(time.time())
                },
                headers={
                    'X-RateLimit-Limit': str(info['limit']),
                    'X-RateLimit-Remaining': str(info['remaining']),
                    'X-RateLimit-Reset': str(info['reset']),
                    'Retry-After': str(info['reset'] - int(time.time()))
                }
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers['X-RateLimit-Limit'] = str(info['limit'])
        response.headers['X-RateLimit-Remaining'] = str(info['remaining'])
        response.headers['X-RateLimit-Reset'] = str(info['reset'])
        
        return response


# IP-based blocking for severe abuse
class IPBlocker:
    """Block IPs that severely abuse the API"""
    
    def __init__(self):
        self.redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        try:
            self.client = redis.from_url(self.redis_url, decode_responses=True)
            self.client.ping()
            self.enabled = True
        except:
            self.enabled = False
            self.blocked_ips = set()
    
    def is_blocked(self, ip: str) -> bool:
        """Check if IP is blocked"""
        if self.enabled:
            return self.client.sismember('blocked_ips', ip)
        else:
            return ip in self.blocked_ips
    
    def block_ip(self, ip: str, duration: int = 3600):
        """Block IP for duration (seconds)"""
        if self.enabled:
            self.client.sadd('blocked_ips', ip)
            self.client.expire('blocked_ips', duration)
        else:
            self.blocked_ips.add(ip)
    
    def unblock_ip(self, ip: str):
        """Unblock IP"""
        if self.enabled:
            self.client.srem('blocked_ips', ip)
        else:
            self.blocked_ips.discard(ip)


# Global instances
rate_limiter = RateLimiter()
ip_blocker = IPBlocker()
