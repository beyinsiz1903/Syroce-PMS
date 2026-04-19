"""Base adapter contract for Syroce Xchange partners."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..schemas import XchangeEnvelope


@dataclass
class DeliveryResult:
    ok: bool
    status_code: int | None = None
    response_excerpt: str | None = None  # first 1KB of partner response
    error: str | None = None
    request_payload_excerpt: str | None = None  # XML/JSON payload excerpt
    dry_run: bool = False


class BaseAdapter(ABC):
    """Each partner adapter implements deliver() for a single envelope.

    Adapters MUST be idempotent — the bus may retry the same
    envelope (with the same envelope.message_id) on transient errors.
    """

    code: str = "base"

    def __init__(self, config: dict[str, Any]):
        self.config = config or {}

    @property
    def is_dry_run(self) -> bool:
        """If essential creds are missing, run in dry-run mode."""
        return False

    @abstractmethod
    async def deliver(self, envelope: XchangeEnvelope) -> DeliveryResult:
        ...
