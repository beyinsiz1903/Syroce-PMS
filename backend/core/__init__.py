"""Core module - database and security."""
from core.database import db, client, mongo_url, db_name
from core.security import (
    hash_password, verify_password, create_token,
    get_current_user, _is_super_admin, security,
    JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_HOURS,
    pwd_context, generate_qr_code, generate_time_based_qr_token,
)
