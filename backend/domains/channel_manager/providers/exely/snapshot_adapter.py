from domains.channel_manager.ari.provider_snapshot_contract import (
    ProviderSnapshotAdapter,
    ProviderSnapshotUnavailable,
)


class ExelySnapshotAdapter(ProviderSnapshotAdapter):
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
        # we explicitly raise Unavailable.
        raise ProviderSnapshotUnavailable(
            "Exely ARI snapshot pull is not yet implemented. Cannot fetch truth."
        )
