"""
Syroce PMS - Security & Authentication Helpers
JWT token management, password hashing, and user authentication.
"""
import logging

logger = logging.getLogger(__name__)
import base64
import io
import os
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from core.database import db
from models.enums import UserRole

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Configuration
JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    JWT_SECRET = secrets.token_urlsafe(64)
    logger.info("⚠️ JWT_SECRET not set in .env! Using random secret (tokens will invalidate on restart)")
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 168  # 7 days

security = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(password, hashed)
    except Exception:
        return False


def create_token(user_id: str, tenant_id: str | None = None) -> str:
    payload = {
        'user_id': user_id,
        'tenant_id': tenant_id,
        'exp': datetime.now(UTC) + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Decode JWT token and return the authenticated User."""
    # Import here to avoid circular imports with schemas
    from models.schemas import User
    from security.encrypted_lookup import decrypt_user_doc

    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get('user_id')

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing user_id")

        user_doc = await db.users.find_one(
            {'$or': [{'id': user_id}, {'user_id': user_id}]}, {'_id': 0}
        )

        if not user_doc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        user_doc = decrypt_user_doc(user_doc)

        if 'id' not in user_doc:
            user_doc['id'] = user_doc.get('user_id', user_id)
        if 'user_id' not in user_doc:
            user_doc['user_id'] = user_doc.get('id', user_id)

        return User(**user_doc)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired - please login again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token - please login again")
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"Auth error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed")


def _is_super_admin(current_user) -> bool:
    role = getattr(current_user, "role", None)
    if role == UserRole.SUPER_ADMIN:
        return True
    roles = getattr(current_user, "roles", None) or []
    return "super_admin" in roles


def generate_qr_code(data: str) -> str:
    import qrcode
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_base64}"


def generate_time_based_qr_token(booking_id: str, expiry_hours: int = 72) -> str:
    expiry = datetime.now(UTC) + timedelta(hours=expiry_hours)
    token = secrets.token_urlsafe(32)
    return jwt.encode({
        'booking_id': booking_id,
        'token': token,
        'exp': expiry
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)
