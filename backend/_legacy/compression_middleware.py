"""
API Response Compression Middleware
Gzip compression for API responses to reduce bandwidth
"""
from fastapi import Request, Response
import gzip
import io
import json

# Minimum size to compress (bytes)
MIN_COMPRESSION_SIZE = 1024  # 1KB

# Compressible content types
COMPRESSIBLE_TYPES = {
    'application/json',
    'application/javascript',
    'text/html',
    'text/css',
    'text/plain',
    'text/xml',
    'application/xml',
    'image/svg+xml',
}

def should_compress(content_type: str, content_length: int, accept_encoding: str) -> bool:
    """
    Determine if response should be compressed
    
    Args:
        content_type: Response content type
        content_length: Response size in bytes
        accept_encoding: Client's Accept-Encoding header
        
    Returns:
        True if should compress
    """
    # Check if client accepts gzip
    if not accept_encoding or 'gzip' not in accept_encoding:
        return False
    
    # Check if content type is compressible
    if not any(ct in content_type for ct in COMPRESSIBLE_TYPES):
        return False
    
    # Check if content is large enough to benefit from compression
    if content_length < MIN_COMPRESSION_SIZE:
        return False
    
    return True


def compress_content(content: bytes, level: int = 6) -> bytes:
    """
    Compress content using gzip
    
    Args:
        content: Content to compress
        level: Compression level (1-9, default 6)
        
    Returns:
        Compressed content
    """
    buffer = io.BytesIO()
    
    with gzip.GzipFile(fileobj=buffer, mode='wb', compresslevel=level) as gz_file:
        gz_file.write(content)
    
    return buffer.getvalue()


class CompressionMiddleware:
    """
    Middleware for automatic response compression
    """
    
    def __init__(
        self,
        app,
        minimum_size: int = MIN_COMPRESSION_SIZE,
        compression_level: int = 6,
        exclude_paths: list = None
    ):
        self.app = app
        self.minimum_size = minimum_size
        self.compression_level = compression_level
        self.exclude_paths = exclude_paths or []
    
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive)
        
        # Check if path should be excluded
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            await self.app(scope, receive, send)
            return
        
        # Get Accept-Encoding header
        accept_encoding = request.headers.get('accept-encoding', '')
        
        # Capture response
        response_body = bytearray()
        response_headers = {}
        status_code = 200
        
        async def send_wrapper(message):
            nonlocal response_body, response_headers, status_code
            
            if message['type'] == 'http.response.start':
                status_code = message['status']
                response_headers = dict(message['headers'])
            elif message['type'] == 'http.response.body':
                response_body.extend(message.get('body', b''))
                
                # If more body coming, don't send yet
                if message.get('more_body', False):
                    return
                
                # Get content type
                content_type = response_headers.get(b'content-type', b'').decode()
                content_length = len(response_body)
                
                # Check if should compress
                if should_compress(content_type, content_length, accept_encoding):
                    # Compress
                    compressed_body = compress_content(
                        bytes(response_body),
                        self.compression_level
                    )
                    
                    # Calculate compression ratio
                    original_size = len(response_body)
                    compressed_size = len(compressed_body)
                    ratio = (1 - compressed_size / original_size) * 100
                    
                    # Only use compression if it actually reduces size
                    if compressed_size < original_size:
                        response_body = compressed_body
                        
                        # Update headers
                        response_headers[b'content-encoding'] = b'gzip'
                        response_headers[b'content-length'] = str(len(compressed_body)).encode()
                        response_headers[b'vary'] = b'Accept-Encoding'
                        response_headers[b'x-compression-ratio'] = f'{ratio:.1f}%'.encode()
                
                # Send response
                await send({
                    'type': 'http.response.start',
                    'status': status_code,
                    'headers': list(response_headers.items()),
                })
                
                await send({
                    'type': 'http.response.body',
                    'body': bytes(response_body),
                })
        
        await self.app(scope, receive, send_wrapper)


def add_compression_middleware(app, **kwargs):
    """
    Add compression middleware to FastAPI app
    
    Usage:
        app = FastAPI()
        add_compression_middleware(
            app,
            minimum_size=1024,
            compression_level=6,
            exclude_paths=['/health', '/metrics']
        )
    """
    middleware = CompressionMiddleware(app, **kwargs)
    return middleware


# Compression statistics
class CompressionStats:
    """Track compression statistics"""
    
    def __init__(self):
        self.total_requests = 0
        self.compressed_requests = 0
        self.total_original_bytes = 0
        self.total_compressed_bytes = 0
    
    def record_compression(self, original_size: int, compressed_size: int):
        """Record a compression event"""
        self.total_requests += 1
        self.compressed_requests += 1
        self.total_original_bytes += original_size
        self.total_compressed_bytes += compressed_size
    
    def record_no_compression(self, size: int):
        """Record a non-compressed response"""
        self.total_requests += 1
        self.total_original_bytes += size
        self.total_compressed_bytes += size
    
    def get_stats(self) -> dict:
        """Get compression statistics"""
        if self.total_requests == 0:
            return {
                "total_requests": 0,
                "compressed_requests": 0,
                "compression_rate": 0,
                "bytes_saved": 0,
                "average_compression_ratio": 0
            }
        
        bytes_saved = self.total_original_bytes - self.total_compressed_bytes
        avg_ratio = (bytes_saved / self.total_original_bytes * 100) if self.total_original_bytes > 0 else 0
        
        return {
            "total_requests": self.total_requests,
            "compressed_requests": self.compressed_requests,
            "compression_rate": f"{(self.compressed_requests / self.total_requests * 100):.1f}%",
            "total_original_bytes": self.total_original_bytes,
            "total_compressed_bytes": self.total_compressed_bytes,
            "bytes_saved": bytes_saved,
            "bytes_saved_mb": round(bytes_saved / (1024 * 1024), 2),
            "average_compression_ratio": f"{avg_ratio:.1f}%"
        }


# Global compression stats
compression_stats = CompressionStats()


# Example decorator for manual compression
def compress_response(compression_level: int = 6):
    """
    Decorator to manually compress specific endpoint responses
    
    Usage:
        @app.get("/api/large-data")
        @compress_response(compression_level=9)
        async def get_large_data():
            return {"data": [...]}
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            # Serialize to JSON if dict
            if isinstance(result, dict):
                content = json.dumps(result).encode()
            elif isinstance(result, str):
                content = result.encode()
            else:
                content = result
            
            # Compress
            compressed = compress_content(content, compression_level)
            
            # Return compressed response
            return Response(
                content=compressed,
                media_type='application/json',
                headers={
                    'Content-Encoding': 'gzip',
                    'Vary': 'Accept-Encoding',
                    'X-Original-Size': str(len(content)),
                    'X-Compressed-Size': str(len(compressed)),
                    'X-Compression-Ratio': f'{(1 - len(compressed)/len(content)) * 100:.1f}%'
                }
            )
        
        return wrapper
    return decorator
