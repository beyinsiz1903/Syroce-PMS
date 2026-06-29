from abc import ABC, abstractmethod


class ProviderSnapshotUnavailable(Exception):
    """Raised when the provider does not support snapshot pull or is temporarily down."""
    pass


class CredentialsMissing(Exception):
    """Raised when the tenant has no credentials configured for the provider."""
    pass


class UnsupportedProvider(Exception):
    """Raised when an unknown provider is requested for snapshot pull."""
    pass


class ProviderSnapshotAdapter(ABC):
    """Interface for fetching ARI snapshots from external Channel Managers (HotelRunner, Exely)."""

    @abstractmethod
    async def fetch_snapshot(
        self,
        tenant_id: str,
        property_id: str,
        credentials: dict,
        *,
        date_from: str,
        date_to: str,
    ) -> list[dict]:
        """
        Fetch the current snapshot from the provider and normalize it.

        Must return a list of dictionaries with the exact format:
        {
            "room_type_code": str,
            "rate_plan_code": str,
            "date": str,
            "availability": int | None,
            "rate": float | None,
            "restrictions": dict
        }

        Should raise ProviderSnapshotUnavailable if the API is missing/failing,
        so the caller does not falsely assume a drift_false state.
        """
        pass
