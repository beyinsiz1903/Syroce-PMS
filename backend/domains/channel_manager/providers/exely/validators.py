"""
Exely Provider — Pre-flight Validators
=========================================

Validates credentials and payloads before sending to the SOAP API.
Catches obvious errors early, before consuming network resources.
"""
from typing import Dict, Any, Optional

from .errors import ExelyValidationError


def validate_credentials(username: str, password: str, hotel_code: str) -> None:
    if not username or not username.strip():
        raise ExelyValidationError("Username is required", field="username")
    if not password or not password.strip():
        raise ExelyValidationError("Password is required", field="password")
    if not hotel_code or not hotel_code.strip():
        raise ExelyValidationError("Hotel code is required", field="hotel_code")


def extract_credentials(credentials: Dict[str, str]) -> tuple:
    """Extract username, password, hotel_code from a credentials dict."""
    username = credentials.get("username", "").strip()
    password = credentials.get("password", "").strip()
    hotel_code = (
        credentials.get("hotel_code")
        or credentials.get("hotel_id", "")
    ).strip()
    return username, password, hotel_code


def validate_ari_payload(
    room_type_code: str,
    rate_plan_code: str,
    start_date: str,
    end_date: str,
) -> None:
    if not room_type_code:
        raise ExelyValidationError("room_type_code is required", field="room_type_code")
    if not rate_plan_code:
        raise ExelyValidationError("rate_plan_code is required", field="rate_plan_code")
    if not start_date:
        raise ExelyValidationError("start_date is required", field="start_date")
    if not end_date:
        raise ExelyValidationError("end_date is required", field="end_date")
    if end_date < start_date:
        raise ExelyValidationError(
            f"end_date ({end_date}) must be >= start_date ({start_date})",
            field="end_date",
        )


def validate_date_range(from_date: Optional[str], to_date: Optional[str]) -> None:
    if from_date and to_date and to_date < from_date:
        raise ExelyValidationError(
            f"to_date ({to_date}) must be >= from_date ({from_date})",
            field="to_date",
        )
