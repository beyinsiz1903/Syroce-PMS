from typing import Any, Iterable


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