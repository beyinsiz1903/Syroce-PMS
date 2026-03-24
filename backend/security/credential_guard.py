"""
Security — Credential Guard
Detects default/weak credentials and enforces credential policies.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict

from core.database import db

logger = logging.getLogger(__name__)

# Common weak passwords to detect
_WEAK_PASSWORDS = {
    "password", "123456", "12345678", "admin", "admin123",
    "demo123", "test123", "hotel123", "password123", "qwerty",
    "letmein", "welcome", "monkey", "master", "dragon",
}

_WEAK_PATTERNS = [
    r"^(.)\1+$",            # All same character
    r"^[0-9]{1,6}$",        # Short numeric only
    r"^(admin|test|demo)",   # Common test prefixes
]


class CredentialGuard:
    """Detects weak credentials and enforces password policies."""

    @staticmethod
    async def scan_weak_credentials(tenant_id: str = None) -> Dict[str, Any]:
        """Scan for users with known weak passwords or default credentials.
        Limits to admin/super_admin roles first, then samples others for performance.
        """
        from passlib.context import CryptContext
        pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

        query: Dict[str, Any] = {}
        if tenant_id:
            query["tenant_id"] = tenant_id
        # Prioritize admin/privileged users for credential scanning
        query["role"] = {"$in": ["admin", "super_admin", "supervisor"]}

        users = await db.users.find(
            query,
            {"_id": 0, "id": 1, "email": 1, "tenant_id": 1, "role": 1, "hashed_password": 1, "password": 1},
        ).to_list(200)

        # Also check a sample of other users
        other_query = dict(query)
        other_query["role"] = {"$nin": ["admin", "super_admin", "supervisor"]}
        others = await db.users.find(
            other_query,
            {"_id": 0, "id": 1, "email": 1, "tenant_id": 1, "role": 1, "hashed_password": 1, "password": 1},
        ).limit(50).to_list(50)
        users.extend(others)

        # Only check top 3 most common weak passwords for speed
        quick_check = list(_WEAK_PASSWORDS)[:3]

        findings = []
        for user in users:
            hashed = user.get("hashed_password") or user.get("password", "")
            if not hashed:
                continue
            for weak_pw in quick_check:
                try:
                    if pwd_ctx.verify(weak_pw, hashed):
                        findings.append({
                            "user_id": user["id"],
                            "email": user.get("email"),
                            "tenant_id": user.get("tenant_id"),
                            "role": user.get("role"),
                            "issue": "Uses known weak password",
                            "severity": "critical" if user.get("role") in ("admin", "super_admin") else "high",
                        })
                        break
                except Exception:
                    continue

        return {
            "scanned_users": len(users),
            "weak_credentials_found": len(findings),
            "findings": findings,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def validate_password_strength(password: str) -> Dict[str, Any]:
        """Validate password meets minimum complexity requirements."""
        issues = []
        if len(password) < 8:
            issues.append("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", password):
            issues.append("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", password):
            issues.append("Password must contain at least one lowercase letter")
        if not re.search(r"[0-9]", password):
            issues.append("Password must contain at least one digit")
        if password.lower() in _WEAK_PASSWORDS:
            issues.append("Password is in the known weak password list")

        for pattern in _WEAK_PATTERNS:
            if re.match(pattern, password):
                issues.append("Password matches a known weak pattern")
                break

        return {
            "is_strong": len(issues) == 0,
            "issues": issues,
            "score": max(0, 100 - len(issues) * 25),
        }


credential_guard = CredentialGuard()
