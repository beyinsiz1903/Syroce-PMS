from typing import Any

import httpx

from integrations.xchange.safety import safe_post_async

from .base import AccountingHttpConnector, ERPConnectionError, ERPSyncRejected, ERPSyncTimeout


class LogoHttpConnector(AccountingHttpConnector):
    async def send_payload(self, url: str, resource: str, payloads: list[dict], credentials: dict, sync_id: str) -> dict[str, Any]:
        api_key = credentials.get("api_key", "")
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}", "X-Syroce-Sync-Id": sync_id}

        try:
            res = await safe_post_async(f"{url}/{resource}", json=payloads, headers=headers, timeout=10.0)

            if res.status_code >= 500:
                raise ERPConnectionError(f"Logo ERP server error for {resource}", status_code=res.status_code)
            elif res.status_code >= 400:
                raise ERPSyncRejected(f"Logo ERP rejected {resource} sync: {res.text}", status_code=res.status_code)

            return {"status_code": res.status_code, "response": res.text}

        except httpx.TimeoutException as e:
            raise ERPSyncTimeout(f"Timeout while syncing {resource} to Logo ERP: {e}")
        except httpx.RequestError as e:
            raise ERPConnectionError(f"Connection error to Logo ERP for {resource}: {e}")
