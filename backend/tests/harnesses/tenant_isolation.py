import os
import uuid
from typing import Any, Dict, Optional

import requests


class TenantIsolationHarness:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or os.environ.get("VITE_BACKEND_URL", "")).rstrip("/")

    def login(self, email: str, password: str) -> Optional[str]:
        if not self.base_url:
            return None

        response = requests.post(
            f"{self.base_url}/api/auth/login",
            json={"email": email, "password": password},
            timeout=20,
        )
        if response.status_code != 200:
            return None
        return response.json().get("access_token")

    def register_tenant(self, suffix: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self.base_url:
            return None

        unique = suffix or uuid.uuid4().hex[:8]
        payload = {
            "property_name": f"Semantic Test Hotel {unique}",
            "email": f"semantic-{unique}@example.com",
            "password": "semantic123",
            "name": f"Semantic Admin {unique}",
            "phone": "+905550000000",
            "address": "Semantic Test Address",
            "location": "Test City",
        }
        response = requests.post(
            f"{self.base_url}/api/auth/register",
            json=payload,
            timeout=20,
        )
        if response.status_code != 200:
            return None
        return response.json()

    def get(self, path: str, token: str) -> requests.Response:
        return requests.get(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )

    def get_json(
        self,
        path: str,
        token: str,
        property_id: Optional[str] = None,
    ) -> tuple[requests.Response, Any]:
        response = requests.get(
            f"{self.base_url}{path}",
            headers=self.build_headers(token, property_id=property_id),
            timeout=20,
        )
        try:
            return response, response.json()
        except ValueError:
            return response, response.text

    def get_without_auth(self, path: str) -> requests.Response:
        return requests.get(f"{self.base_url}{path}", timeout=20)

    def build_headers(self, token: str, property_id: Optional[str] = None) -> Dict[str, Any]:
        headers: Dict[str, Any] = {"Authorization": f"Bearer {token}"}
        if property_id:
            headers["x-property-id"] = property_id
        return headers