import os
from typing import Any, Dict, Optional

import requests


class TenantIsolationHarness:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or os.environ.get("REACT_APP_BACKEND_URL", "")).rstrip("/")

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

    def get(self, path: str, token: str) -> requests.Response:
        return requests.get(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )

    def build_headers(self, token: str, property_id: Optional[str] = None) -> Dict[str, Any]:
        headers: Dict[str, Any] = {"Authorization": f"Bearer {token}"}
        if property_id:
            headers["x-property-id"] = property_id
        return headers