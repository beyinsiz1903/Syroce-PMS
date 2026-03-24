from typing import Optional

from fastapi import HTTPException, Request, status

IDEMPOTENCY_HEADER = "Idempotency-Key"


def normalize_idempotency_key(key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    normalized = key.strip()
    return normalized or None


def get_idempotency_key(request: Request) -> Optional[str]:
    return normalize_idempotency_key(request.headers.get(IDEMPOTENCY_HEADER))


def ensure_idempotent_request(request: Request, required: bool = True) -> Optional[str]:
    key = get_idempotency_key(request)
    if required and not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing {IDEMPOTENCY_HEADER} header",
        )
    return key