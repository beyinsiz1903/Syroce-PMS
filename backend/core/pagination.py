"""
Shared pagination dependency for list endpoints.

Centralizes the `limit`/`offset` Query bound pattern so that:
  - Negative or oversized inputs are rejected with HTTP 422 (not 500).
  - Each endpoint declares its own ceiling without re-implementing validation.
  - Future-proof: change once here to add e.g. cursor-based paging.

Usage:
    from core.pagination import paginate, PaginationParams

    @router.get("/items")
    async def list_items(p: PaginationParams = Depends(paginate(default_limit=50, max_limit=500))):
        return await db.items.find().skip(p.offset).limit(p.limit).to_list(p.limit)
"""

from dataclasses import dataclass

from fastapi import Query


@dataclass
class PaginationParams:
    limit: int
    offset: int


def paginate(default_limit: int = 50, max_limit: int = 500, max_offset: int = 1_000_000):
    """Factory returning a FastAPI dependency that yields a validated PaginationParams.

    Args:
        default_limit: Limit when caller omits ?limit=
        max_limit:     Hard ceiling — anything above returns 422.
        max_offset:    Hard ceiling for offset (DoS / unbounded skip protection).
    """

    def _dep(
        limit: int = Query(default_limit, ge=1, le=max_limit, description="Sayfa boyutu"),
        offset: int = Query(0, ge=0, le=max_offset, description="Atlanacak kayıt sayısı"),
    ) -> PaginationParams:
        return PaginationParams(limit=limit, offset=offset)

    return _dep
