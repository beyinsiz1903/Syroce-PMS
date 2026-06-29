from domains.channel_manager.ari.provider_snapshot_contract import (
    ProviderSnapshotAdapter,
    ProviderSnapshotUnavailable,
)


class HotelRunnerSnapshotAdapter(ProviderSnapshotAdapter):
    async def fetch_snapshot(
        self,
        tenant_id: str,
        property_id: str,
        credentials: dict,
        *,
        date_from: str,
        date_to: str,
    ) -> list[dict]:
        # Fail-closed doctrine: 
        # Until the actual HTTP pull endpoint documentation is provided and implemented,
        # we explicitly raise Unavailable. Returning a mock "success" or empty list
        # would create a false "drift_false" state in the system.
        raise ProviderSnapshotUnavailable(
            "HotelRunner ARI snapshot pull is not yet implemented. Cannot fetch truth."
        )
