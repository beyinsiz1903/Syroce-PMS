"""
Web Push (PWA) helpers for the internal messaging domain.

Implements VAPID key bootstrapping, per-user PushSubscription storage, and a
best-effort dispatch helper used by `send_internal_message` to deliver urgent
messages to the OS notification centre even when the recipient has no tab open.

Design notes
------------
* VAPID keys are read from `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` env vars.
  If unset, we generate a fresh keypair on first use and persist it to
  `db.web_push_keys` so subsequent restarts keep using the same identifier
  (otherwise every browser subscription would silently break on restart).
* Subscriptions are stored in `db.web_push_subscriptions`, keyed by
  (tenant_id, user_id, endpoint). The endpoint is the unique browser handle.
* `pywebpush` is an *optional* dependency. If it is not installed, dispatch
  becomes a no-op and we log a single warning per process — the rest of the
  notification stack (in-app, websocket, browser-tab Notification API) keeps
  working.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from core.database import db

logger = logging.getLogger(__name__)

_VAPID_CACHE: dict[str, str] | None = None
_PYWEBPUSH_WARNED = False


def _b64url_no_pad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


async def _generate_and_store_vapid_keys() -> dict[str, str]:
    """Generate a new VAPID P-256 keypair and persist it to db.web_push_keys."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_numbers = private_key.public_key().public_numbers()

    # Web push expects the public key as the uncompressed 65-byte point
    # (0x04 prefix + 32-byte X + 32-byte Y), base64url-encoded without padding.
    x = public_numbers.x.to_bytes(32, 'big')
    y = public_numbers.y.to_bytes(32, 'big')
    pub_raw = b"\x04" + x + y
    pub_b64url = _b64url_no_pad(pub_raw)

    # Private key as base64url of the raw 32-byte scalar (pywebpush accepts this).
    priv_raw = private_key.private_numbers().private_value.to_bytes(32, 'big')
    priv_b64url = _b64url_no_pad(priv_raw)

    # Also keep PEM for potential future tooling.
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode('ascii')

    record = {
        'public_key': pub_b64url,
        'private_key': priv_b64url,
        'private_key_pem': priv_pem,
        'created_at': datetime.now(UTC).isoformat(),
        'auto_generated': True,
    }
    await db.web_push_keys.update_one(
        {'_id': 'singleton'},
        {'$set': record},
        upsert=True,
    )
    return record


async def get_vapid_keys() -> dict[str, str]:
    """Return the active VAPID keypair, generating one on first use if needed.

    Caches the result in-process so the hot path doesn't hit Mongo every time.
    """
    global _VAPID_CACHE
    if _VAPID_CACHE:
        return _VAPID_CACHE

    env_pub = os.environ.get('VAPID_PUBLIC_KEY')
    env_priv = os.environ.get('VAPID_PRIVATE_KEY')
    if env_pub and env_priv:
        _VAPID_CACHE = {'public_key': env_pub, 'private_key': env_priv}
        return _VAPID_CACHE

    record = await db.web_push_keys.find_one({'_id': 'singleton'})
    if not record:
        record = await _generate_and_store_vapid_keys()
        logger.warning(
            "web_push: generated and persisted a new VAPID keypair (no env vars provided). "
            "Set VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY for stable, multi-process deployments."
        )

    _VAPID_CACHE = {
        'public_key': record['public_key'],
        'private_key': record['private_key'],
    }
    return _VAPID_CACHE


def _vapid_subject() -> str:
    """`sub` claim required by the VAPID spec — usually a mailto: URL."""
    return os.environ.get('VAPID_SUBJECT', 'mailto:noreply@syroce.local')


async def store_subscription(
    *,
    tenant_id: str,
    user_id: str,
    department: str | None,
    subscription: dict[str, Any],
    user_agent: str | None = None,
) -> None:
    """Upsert a PushSubscription for (tenant_id, user_id, endpoint)."""
    endpoint = subscription.get('endpoint')
    keys = subscription.get('keys') or {}
    if not endpoint or not keys.get('p256dh') or not keys.get('auth'):
        raise ValueError("PushSubscription must include endpoint and keys.{p256dh,auth}")

    now = datetime.now(UTC).isoformat()
    await db.web_push_subscriptions.update_one(
        {
            'tenant_id': tenant_id,
            'user_id': user_id,
            'endpoint': endpoint,
        },
        {
            '$set': {
                'tenant_id': tenant_id,
                'user_id': user_id,
                'department': department,
                'endpoint': endpoint,
                'p256dh': keys['p256dh'],
                'auth': keys['auth'],
                'user_agent': user_agent,
                'updated_at': now,
            },
            '$setOnInsert': {'created_at': now},
        },
        upsert=True,
    )


async def remove_subscription(*, tenant_id: str, user_id: str, endpoint: str) -> int:
    res = await db.web_push_subscriptions.delete_one({
        'tenant_id': tenant_id,
        'user_id': user_id,
        'endpoint': endpoint,
    })
    return res.deleted_count or 0


async def _collect_target_subscriptions(
    *,
    tenant_id: str,
    to_user_id: str | None,
    to_department: str | None,
) -> list[dict[str, Any]]:
    """Fetch PushSubscription rows that should receive a given message."""
    query: dict[str, Any] = {'tenant_id': tenant_id}
    if to_user_id:
        query['user_id'] = to_user_id
    elif to_department:
        query['department'] = to_department
    # else broadcast → no extra filter (all tenant users)

    return await db.web_push_subscriptions.find(query, {'_id': 0}).to_list(2000)


async def dispatch_internal_message_push(
    *,
    tenant_id: str,
    payload: dict[str, Any],
    to_user_id: str | None = None,
    to_department: str | None = None,
) -> dict[str, int]:
    """Send a web push payload to all relevant subscribers.

    Returns counters for observability. Best-effort: errors per subscription
    are logged and swallowed so one bad endpoint never blocks the rest.
    """
    global _PYWEBPUSH_WARNED

    try:
        from pywebpush import WebPushException, webpush  # type: ignore
    except Exception:
        if not _PYWEBPUSH_WARNED:
            logger.warning(
                "web_push: pywebpush is not installed — urgent OS notifications "
                "are disabled. `pip install pywebpush` to enable."
            )
            _PYWEBPUSH_WARNED = True
        return {'attempted': 0, 'sent': 0, 'failed': 0, 'pruned': 0}

    subscriptions = await _collect_target_subscriptions(
        tenant_id=tenant_id, to_user_id=to_user_id, to_department=to_department
    )
    if not subscriptions:
        return {'attempted': 0, 'sent': 0, 'failed': 0, 'pruned': 0}

    keys = await get_vapid_keys()
    body = json.dumps(payload).encode('utf-8')
    sent = failed = pruned = 0

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub['endpoint'],
                    'keys': {'p256dh': sub['p256dh'], 'auth': sub['auth']},
                },
                data=body,
                vapid_private_key=keys['private_key'],
                vapid_claims={'sub': _vapid_subject()},
                ttl=3600,
            )
            sent += 1
        except WebPushException as e:  # type: ignore[name-defined]
            status_code = getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
            if status_code in (404, 410):
                # Subscription expired/unsubscribed — purge it so we stop trying.
                await db.web_push_subscriptions.delete_one({
                    'tenant_id': tenant_id,
                    'user_id': sub['user_id'],
                    'endpoint': sub['endpoint'],
                })
                pruned += 1
            else:
                failed += 1
                logger.warning(
                    "web_push: delivery failed (status=%s) endpoint=%s err=%s",
                    status_code, sub.get('endpoint', '')[:60], e,
                )
        except Exception as e:  # pragma: no cover — defensive
            failed += 1
            logger.warning(
                "web_push: delivery error endpoint=%s err=%s",
                sub.get('endpoint', '')[:60], e,
            )

    return {
        'attempted': len(subscriptions),
        'sent': sent,
        'failed': failed,
        'pruned': pruned,
    }
