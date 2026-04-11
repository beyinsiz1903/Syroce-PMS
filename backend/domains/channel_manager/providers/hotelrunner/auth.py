"""
HotelRunner Provider — Centralized Authentication
===================================================

HotelRunner uses query parameter authentication: token + hr_id.
Single source of truth for all auth param generation.
"""

from .errors import HotelRunnerAuthError


def build_auth_params(token: str, hr_id: str) -> dict[str, str]:
    """Build query params for HotelRunner API authentication."""
    return {"token": token, "hr_id": hr_id}


def validate_credentials(token: str, hr_id: str) -> None:
    """Validate that credentials are non-empty before any API call."""
    if not token or not token.strip():
        raise HotelRunnerAuthError("Missing or empty API token")
    if not hr_id or not hr_id.strip():
        raise HotelRunnerAuthError("Missing or empty HR ID (hotel ID)")


def extract_credentials(credentials: dict[str, str]) -> tuple[str, str]:
    """Extract token and hr_id from a credentials dict, handling key aliases."""
    token = credentials.get("token") or credentials.get("api_key", "")
    hr_id = credentials.get("hr_id") or credentials.get("hotel_id", "")
    return token.strip(), hr_id.strip()
