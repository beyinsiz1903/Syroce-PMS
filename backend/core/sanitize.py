"""
Input Sanitization & Validation Utilities
XSS, NoSQL injection, ve path traversal koruması
"""
import html
import re
from typing import Any

# NoSQL injection patterns
NOSQL_PATTERNS = [
    re.compile(r'\$(?:gt|gte|lt|lte|ne|in|nin|and|or|not|nor|exists|type|regex|where|all|elemMatch|size|mod|text|search)', re.I),
    re.compile(r'\{.*\$.*\}'),
]

# Path traversal patterns
PATH_TRAVERSAL = re.compile(r'\.\.[\\/]|[\\/]\.\.|\.\./|\.\.\\')

# Script injection patterns
XSS_PATTERNS = [
    re.compile(r'<script[^>]*>', re.I),
    re.compile(r'javascript\s*:', re.I),
    re.compile(r'on\w+\s*=', re.I),
    re.compile(r'<iframe[^>]*>', re.I),
    re.compile(r'<object[^>]*>', re.I),
    re.compile(r'<embed[^>]*>', re.I),
]


def sanitize_string(value: str, max_length: int = 10000) -> str:
    """Sanitize a string input - escape HTML and trim length."""
    if not isinstance(value, str):
        return value
    value = value[:max_length]
    value = html.escape(value, quote=True)
    return value.strip()


def check_nosql_injection(value: Any) -> bool:
    """Check if value contains NoSQL injection patterns. Returns True if suspicious."""
    if isinstance(value, str):
        for pattern in NOSQL_PATTERNS:
            if pattern.search(value):
                return True
    elif isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str) and k.startswith('$'):
                return True
            if check_nosql_injection(v):
                return True
    elif isinstance(value, list):
        for item in value:
            if check_nosql_injection(item):
                return True
    return False


def check_xss(value: str) -> bool:
    """Check if string contains potential XSS patterns. Returns True if suspicious."""
    if not isinstance(value, str):
        return False
    for pattern in XSS_PATTERNS:
        if pattern.search(value):
            return True
    return False


def check_path_traversal(value: str) -> bool:
    """Check for path traversal attempts."""
    if not isinstance(value, str):
        return False
    return bool(PATH_TRAVERSAL.search(value))


def sanitize_dict(data: dict, max_depth: int = 5) -> dict:
    """Recursively sanitize a dictionary of input data."""
    if max_depth <= 0:
        return data
    
    cleaned = {}
    for key, value in data.items():
        # Sanitize keys
        clean_key = str(key)[:100]
        
        if isinstance(value, str):
            cleaned[clean_key] = sanitize_string(value)
        elif isinstance(value, dict):
            cleaned[clean_key] = sanitize_dict(value, max_depth - 1)
        elif isinstance(value, list):
            cleaned[clean_key] = [
                sanitize_string(v) if isinstance(v, str)
                else sanitize_dict(v, max_depth - 1) if isinstance(v, dict)
                else v
                for v in value[:1000]  # Limit list size
            ]
        else:
            cleaned[clean_key] = value
    
    return cleaned


def validate_email(email: str) -> bool:
    """Basic email validation."""
    pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    return bool(pattern.match(email)) and len(email) <= 254


def validate_phone(phone: str) -> bool:
    """Basic phone validation."""
    cleaned = re.sub(r'[\s\-\(\)\+]', '', phone)
    return cleaned.isdigit() and 7 <= len(cleaned) <= 15
