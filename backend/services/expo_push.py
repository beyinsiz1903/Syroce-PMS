"""
Expo Push delivery helper (Syroce mobil V3 - push integration).

Mobile (Expo) clients register an `ExponentPushToken[...]` after granting
notification permission. We persist it on the device record (see
`/api/notifications/push/register` in `backend/domains/pms/notification_router.py`)
and call this helper when an event needs to surface as a real OS-level push
notification on the user's phone.

Design choices
--------------
* Single dependency: `httpx` is already used elsewhere in the backend, so we
  avoid pulling in a separate SDK.
* Best-effort: every send is wrapped so a missing/expired token, a partial
  Expo outage, or a network glitch never crashes the caller. Failures are
  logged but never raised.
* Tenant-scoped: callers pass `tenant_id`; we only collect tokens that match
  that tenant so a multi-tenant deployment cannot cross-leak push payloads.
* Token shape filter: only tokens that look like Expo tokens
  (`ExponentPushToken[...]` or `ExpoPushToken[...]`) are sent to the Expo
  Push service. Anything else is silently skipped (legacy web push tokens
  live alongside in the same collection).
* Disabled by default in tests: setting `DISABLE_EXPO_PUSH=1` makes
  `send_expo_push` a no-op so unit tests don't hit the network.

References
----------
* Expo Push API: https://docs.expo.dev/push-notifications/sending-notifications/
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx

from core.database import db

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = os.environ.get(
    "EXPO_PUSH_URL", "https://exp.host/--/api/v2/push/send"
)
_EXPO_TIMEOUT_SEC = float(os.environ.get("EXPO_PUSH_TIMEOUT_SEC", "5"))
_EXPO_BATCH = 100  # Expo accepts up to 100 messages per request


def _is_expo_token(token: str | None) -> bool:
    if not token or not isinstance(token, str):
        return False
    return token.startswith("ExponentPushToken[") or token.startswith(
        "ExpoPushToken["
    )


def _push_disabled() -> bool:
    return os.environ.get("DISABLE_EXPO_PUSH", "").strip() == "1"


async def _collect_expo_tokens(
    tenant_id: str,
    user_ids: list[str] | None = None,
    departments: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Look up Expo-shaped tokens for the requested audience."""
    query: dict[str, Any] = {
        "tenant_id": tenant_id,
        "push_token": {"$exists": True, "$ne": None},
    }
    or_clauses: list[dict[str, Any]] = []
    if user_ids:
        or_clauses.append({"user_id": {"$in": user_ids}})
    if departments:
        or_clauses.append({"departments": {"$in": departments}})
    if or_clauses:
        query["$or"] = or_clauses
    devices = await db.push_device_tokens.find(
        query, {"_id": 0}
    ).to_list(2000)
    return [d for d in devices if _is_expo_token(d.get("push_token"))]


async def _post_expo_batch(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """POST a single Expo batch and return the per-ticket result list."""
    if not messages:
        return []
    try:
        async with httpx.AsyncClient(timeout=_EXPO_TIMEOUT_SEC) as client:
            resp = await client.post(
                EXPO_PUSH_URL,
                json=messages,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:  # network, JSON, HTTP error — all best-effort
        logger.warning("[expo_push] batch failed: %s", exc)
        return [{"status": "error", "message": str(exc)} for _ in messages]
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return [{"status": "error", "message": "unexpected_response"} for _ in messages]
    return data


async def send_expo_push(
    tenant_id: str,
    *,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    user_ids: list[str] | None = None,
    departments: list[str] | None = None,
    priority: str = "high",
    sound: str | None = "default",
    channel_id: str | None = None,
) -> dict[str, Any]:
    """Fan-out a push notification to every Expo device matching the audience.

    Returns a small summary dict so callers can log how many devices the
    notification reached. Never raises — failures are logged and counted.
    """
    if _push_disabled():
        return {"sent": 0, "skipped": True, "reason": "DISABLE_EXPO_PUSH"}
    devices = await _collect_expo_tokens(
        tenant_id, user_ids=user_ids, departments=departments
    )
    if not devices:
        return {"sent": 0, "tokens": 0, "skipped": True}

    base_data = data or {}
    messages: list[dict[str, Any]] = []
    for device in devices:
        token = device.get("push_token")
        msg: dict[str, Any] = {
            "to": token,
            "title": title,
            "body": body,
            "data": {**base_data, "device_id": device.get("device_id")},
            "priority": priority,
        }
        if sound:
            msg["sound"] = sound
        if channel_id:
            msg["channelId"] = channel_id
        messages.append(msg)

    # Batch & dispatch
    batches = [messages[i : i + _EXPO_BATCH] for i in range(0, len(messages), _EXPO_BATCH)]
    results: list[dict[str, Any]] = []
    for batch in batches:
        results.extend(await _post_expo_batch(batch))

    ok = sum(1 for r in results if r.get("status") == "ok")
    err = len(results) - ok

    # Persist a small audit log so V4 can build a delivery dashboard.
    try:
        await db.expo_push_logs.insert_one(
            {
                "tenant_id": tenant_id,
                "title": title,
                "body": body,
                "data": base_data,
                "user_ids": user_ids,
                "departments": departments,
                "tokens": len(messages),
                "ok": ok,
                "err": err,
                "results": results[:50],  # cap to keep doc small
                "sent_at": datetime.now(UTC).isoformat(),
            }
        )
    except Exception:
        logger.exception("[expo_push] failed to persist delivery log")

    return {"sent": ok, "errors": err, "tokens": len(messages)}


def fire_and_forget_expo_push(
    tenant_id: str,
    *,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    user_ids: list[str] | None = None,
    departments: list[str] | None = None,
    priority: str = "high",
) -> None:
    """Schedule send_expo_push without awaiting.

    Useful inside event-creation handlers (damage report, guest message, …)
    where we don't want to slow the HTTP response on Expo round-trip latency.
    Errors are swallowed inside `send_expo_push`, so an unhandled-task
    callback isn't required.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(
        send_expo_push(
            tenant_id,
            title=title,
            body=body,
            data=data,
            user_ids=user_ids,
            departments=departments,
            priority=priority,
        )
    )
