from typing import Any

import httpx

from .base import AccountingHttpConnector, ERPConnectionError, ERPSyncRejected, ERPSyncTimeout


class LogoHttpConnector(AccountingHttpConnector):
    async def send_payload(self, url: str, payloads: list[dict], credentials: dict, sync_id: str) -> dict[str, Any]:
        api_key = credentials.get("api_key", "")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "X-Syroce-Sync-Id": sync_id
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(f"{url}/invoices", json=payloads, headers=headers)

                if res.status_code >= 500:
                    raise ERPConnectionError("Logo ERP server error", status_code=res.status_code)
                elif res.status_code >= 400:
                    raise ERPSyncRejected(f"Logo ERP rejected sync: {res.text}", status_code=res.status_code)

                return {
                    "status_code": res.status_code,
                    "response": res.text
                }

        except httpx.TimeoutException as e:
            raise ERPSyncTimeout(f"Timeout while syncing to Logo ERP: {e}")
        except httpx.RequestError as e:
            raise ERPConnectionError(f"Connection error to Logo ERP: {e}")
