"""
HotelRunner Authentication Manager.
Handles token-based auth with hr_id for all HotelRunner API calls.
"""
from typing import Any


class HotelRunnerAuth:
    """Manages HotelRunner authentication headers and token lifecycle."""

    def __init__(self, token: str, hr_id: str):
        self._token = token
        self._hr_id = hr_id

    @property
    def hr_id(self) -> str:
        return self._hr_id

    def get_auth_params(self) -> dict[str, str]:
        """Returns query parameters for HotelRunner API authentication."""
        return {
            "token": self._token,
            "hr_id": self._hr_id,
        }

    def get_auth_headers(self) -> dict[str, str]:
        """Returns HTTP headers for HotelRunner API calls."""
        return {
            "Content-Type": "application/xml",
            "Accept": "application/xml",
        }

    @classmethod
    def from_credentials(cls, credentials: dict[str, Any]) -> "HotelRunnerAuth":
        """Factory from ConnectorAccount.credentials dict."""
        token = credentials.get("token", "")
        hr_id = credentials.get("hr_id", "")
        if not token or not hr_id:
            from .v1_errors import AuthenticationError
            raise AuthenticationError("Missing token or hr_id in connector credentials")
        return cls(token=token, hr_id=hr_id)
