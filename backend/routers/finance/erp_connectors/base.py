from typing import Any


class ERPCredentialsMissing(Exception):
    pass

class ERPConnectionError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code

class ERPSyncTimeout(Exception):
    pass

class ERPSyncRejected(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code

class AccountingHttpConnector:
    async def send_payload(self, url: str, resource: str, payloads: list[dict], credentials: dict, sync_id: str) -> dict[str, Any]:
        """
        Sends the ERP payload to the target provider.
        Should raise ERPConnectionError, ERPSyncTimeout, or ERPSyncRejected on failure.
        Should return a dict with relevant provider response info on success.
        """
        raise NotImplementedError
