from typing import Any, Iterable
from datetime import datetime


def build_contract_snapshot(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {key: build_contract_snapshot(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [build_contract_snapshot(payload[0])] if payload else []
    if payload is None:
        return "NoneType"
    return type(payload).__name__


def assert_required_keys(payload: dict, keys: Iterable[str]) -> None:
    missing = [key for key in keys if key not in payload]
    assert not missing, f"Missing required keys: {missing}"


def assert_optional_field_types(payload: dict, field_name: str, allowed_types: tuple[type, ...]) -> None:
    if field_name not in payload or payload[field_name] is None:
        return
    assert isinstance(payload[field_name], allowed_types), (
        f"Field '{field_name}' expected {allowed_types}, got {type(payload[field_name])}"
    )


def assert_iso_datetime_string(value: str) -> None:
    datetime.fromisoformat(value.replace("Z", "+00:00"))