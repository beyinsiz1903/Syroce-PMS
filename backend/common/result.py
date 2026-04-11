"""
Common — Service Result Object
Standardized return type for all service methods.
"""
from typing import Any


class ServiceResult:
    """Wraps service method outcomes with success/failure metadata."""

    __slots__ = ("ok", "data", "error", "code", "meta")

    def __init__(
        self,
        ok: bool = True,
        data: Any = None,
        error: str | None = None,
        code: str | None = None,
        meta: dict[str, Any] | None = None,
    ):
        self.ok = ok
        self.data = data
        self.error = error
        self.code = code
        self.meta = meta or {}

    @classmethod
    def success(cls, data: Any = None, **meta) -> "ServiceResult":
        return cls(ok=True, data=data, meta=meta)

    @classmethod
    def fail(cls, error: str, code: str = "ERROR", **meta) -> "ServiceResult":
        return cls(ok=False, error=error, code=code, meta=meta)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"ok": self.ok}
        if self.ok:
            d["data"] = self.data
        else:
            d["error"] = self.error
            d["code"] = self.code
        if self.meta:
            d["meta"] = self.meta
        return d


class PaginatedResult:
    """Standard paginated data envelope."""

    __slots__ = ("items", "total", "limit", "offset")

    def __init__(self, items: list[Any], total: int, limit: int, offset: int):
        self.items = items
        self.total = total
        self.limit = limit
        self.offset = offset

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
            "has_more": (self.offset + self.limit) < self.total,
        }
