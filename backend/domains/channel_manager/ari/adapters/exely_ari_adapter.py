"""Canonical Exely ARI adapter backed by durable single-write delivery."""

from domains.channel_manager.ari.events import ARIDelta, ProviderResult
from domains.channel_manager.providers.exely.ari_delivery import deliver_exely_ari


class ExelyARIAdapter:
    """Translate a compiled delta into one durable Exely operation."""

    def __init__(self, exely_client=None, *, write_enabled: bool | None = None):
        self._client = exely_client
        self._write_enabled = write_enabled

    async def push_availability(self, delta: ARIDelta) -> ProviderResult:
        return await self._push(delta)

    async def push_rate(self, delta: ARIDelta) -> ProviderResult:
        return await self._push(delta)

    async def push_restrictions(self, delta: ARIDelta) -> ProviderResult:
        return await self._push(delta)

    async def _push(self, delta: ARIDelta) -> ProviderResult:
        operation = str(delta.payload.get("operation") or "")
        update = {
            "property_id": delta.property_id,
            "room_type_code": delta.room_type_code,
            "rate_plan_code": delta.rate_plan_code or "",
            "start_date": str(delta.date_from),
            "end_date": str(delta.date_to),
            "value": delta.payload.get("value"),
            "currency": delta.payload.get("currency", "TRY"),
            "operation_identity": delta.operation_identity,
        }
        result = await deliver_exely_ari(
            delta.tenant_id,
            operation,
            update,
            provider=self._client,
            write_enabled=self._write_enabled,
        )
        delivery_state = "confirmed" if result.success else result.state
        return ProviderResult(
            success=result.success,
            provider="exely",
            status_code=200 if result.success else None,
            response_payload=result.safe_metadata(),
            error=result.error_code or None,
            duration_ms=0,
            retryable=False,
            delivery_state=delivery_state,
            provider_write_count=result.provider_write_count,
        )
