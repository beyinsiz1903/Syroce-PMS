from typing import Any


class NilveraReturnAdapter:
    """
    Fail-closed adapter for sending CreateReturn requests to Nilvera.
    This acts as a guard until the Nilvera Sandbox contract spikes are completed
    and the actual payload structure is authorized.
    """

    @staticmethod
    async def create_return(
        tenant_id: str,
        source_incoming_invoice_id: str,
        payload_data: dict[str, Any]
    ) -> Any:
        # F2 requirement: "Gerçek provider payload’ı doğrulanana kadar adapter fail-closed davranacak; tahmini payload göndermeyecek."
        raise NotImplementedError(
            "F2 CreateReturn is blocked pending sandbox contract verification. "
            "No requests will be sent to the provider until the payload structure is verified."
        )
