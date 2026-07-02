import sys
import os
sys.path.insert(0, os.path.abspath("backend"))

from datetime import datetime, timedelta, UTC
import jwt
import requests
from backend.core.security import JWT_SECRET, JWT_ALGORITHM

def get_token():
    payload = {
        "sub": "admin@syrocedemo.com",
        "tenant": "syrocedemo",
        "role": "admin",
        "permissions": ["all"],
        "jti": "fake-jti",
        "exp": datetime.now(UTC) + timedelta(minutes=60)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

token = get_token()
diary = requests.get("http://localhost:8000/api/mice/diary?date_from=2026-07-01&date_to=2026-07-31", headers={"Authorization": f"Bearer {token}", "Origin": "http://localhost:5173"})
print(f"Status: {diary.status_code}")
print(f"Body: {diary.text}")
