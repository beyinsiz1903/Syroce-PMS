"""Wave 9 — Messaging activity feed PII / RBAC.

`/api/messaging-center/activity` is only `get_current_user`-guarded, while
`/api/messaging-center/delivery-logs` requires `view_guest_list` (VIEW_REPORTS)
precisely because delivery logs embed the recipient (guest email/phone). The
activity feed reuses those same delivery-log rows in a free-text `message`
field, so without masking it leaked recipient PII to any authenticated role
(e.g. HOUSEKEEPING) that cannot read the guest list.

These tests lock the contract:
  - `_mask_recipient` masks the identifying part (email local-part / phone
    digits) but keeps the non-identifying domain for operational context.
  - The activity handler shows the raw recipient ONLY to roles holding
    `view_guest_list`; non-privileged roles get the masked form.
  - Tenant scoping is carried on every query (no cross-tenant fetch).

No guard is loosened and no role gains new access — failures here mean a real
PII regression.
"""

from types import SimpleNamespace

import pytest

import routers.messaging as messaging
from models.enums import UserRole


# ── _mask_recipient unit ───────────────────────────────────────────────

def test_mask_recipient_email_keeps_domain_masks_localpart():
    assert messaging._mask_recipient("ahmet.yilmaz@gmail.com") == "a***@gmail.com"


def test_mask_recipient_phone_keeps_last_two():
    masked = messaging._mask_recipient("+905301234567")
    assert masked.endswith("67")
    assert "5301234" not in masked
    assert set(masked[:-2]) == {"*"}


def test_mask_recipient_empty_stays_empty():
    assert messaging._mask_recipient("") == ""
    assert messaging._mask_recipient(None) == ""


# ── activity handler masking via RBAC ─────────────────────────────────

class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def sort(self, *a, **k):
        return self

    async def to_list(self, n):
        return list(self._rows[:n])


class _Coll:
    def __init__(self, rows):
        self._rows = rows
        self.queries = []

    def find(self, query, projection=None, *a, **k):
        self.queries.append(query)
        return _Cursor(self._rows)


def _fake_db():
    notifications = _Coll([])  # focus on delivery-log derived rows
    delivery = _Coll([
        {
            "id": "d1",
            "tenant_id": "t1",
            "channel": "email",
            "status": "sent",
            "recipient": "guest.one@example.com",
            "use_case": "checkin_reminder",
            "created_at": "2026-05-30T10:00:00Z",
        }
    ])
    db = SimpleNamespace(notifications=notifications, messaging_delivery_logs=delivery)
    return db, notifications, delivery


def _user(role):
    return SimpleNamespace(tenant_id="t1", role=role, granted_permissions=None)


@pytest.mark.asyncio
async def test_activity_masks_recipient_for_non_privileged_role(monkeypatch):
    db, _, _ = _fake_db()
    monkeypatch.setattr(messaging, "_get_db", lambda: db)
    res = await messaging.get_messaging_activity(
        limit=20, current_user=_user(UserRole.HOUSEKEEPING)
    )
    msg = res["activities"][0]["message"]
    assert "guest.one@example.com" not in msg
    assert "g***@example.com" in msg


@pytest.mark.asyncio
async def test_activity_shows_recipient_for_view_guest_list_role(monkeypatch):
    db, _, _ = _fake_db()
    monkeypatch.setattr(messaging, "_get_db", lambda: db)
    res = await messaging.get_messaging_activity(
        limit=20, current_user=_user(UserRole.FRONT_DESK)
    )
    assert "guest.one@example.com" in res["activities"][0]["message"]


@pytest.mark.asyncio
async def test_activity_shows_recipient_for_admin(monkeypatch):
    db, _, _ = _fake_db()
    monkeypatch.setattr(messaging, "_get_db", lambda: db)
    res = await messaging.get_messaging_activity(
        limit=20, current_user=_user(UserRole.ADMIN)
    )
    assert "guest.one@example.com" in res["activities"][0]["message"]


@pytest.mark.asyncio
async def test_activity_queries_are_tenant_scoped(monkeypatch):
    db, notifications, delivery = _fake_db()
    monkeypatch.setattr(messaging, "_get_db", lambda: db)
    await messaging.get_messaging_activity(
        limit=20, current_user=_user(UserRole.HOUSEKEEPING)
    )
    assert all(q.get("tenant_id") == "t1" for q in notifications.queries)
    assert all(q.get("tenant_id") == "t1" for q in delivery.queries)


# ── _mask_freetext_pii unit ───────────────────────────────────────────

def test_mask_freetext_pii_masks_inline_email_keeps_domain():
    out = messaging._mask_freetext_pii("Hatırlatma ahmet.yilmaz@example.com gönderildi")
    assert "ahmet.yilmaz@example.com" not in out
    assert "a***@example.com" in out


def test_mask_freetext_pii_masks_inline_phone_keeps_last_two():
    out = messaging._mask_freetext_pii("WhatsApp +90 532 123 45 67 iletildi")
    assert "532 123 45 67" not in out
    assert out.endswith("67 iletildi")


def test_mask_freetext_pii_leaves_non_pii_amounts_intact():
    txt = "Toplam 1234.56 TL tahsil edildi (oda 204)"
    assert messaging._mask_freetext_pii(txt) == txt


# ── notification free-text masking via RBAC ───────────────────────────

def _db_with_notification(message, title="Otomasyon"):
    notifications = _Coll([
        {
            "id": "n1",
            "tenant_id": "t1",
            "type": "messaging_automation",
            "title": title,
            "message": message,
            "priority": "normal",
            "created_at": "2026-05-30T11:00:00Z",
            "read": False,
        }
    ])
    delivery = _Coll([])
    db = SimpleNamespace(notifications=notifications, messaging_delivery_logs=delivery)
    return db


@pytest.mark.asyncio
async def test_activity_masks_notification_freetext_for_non_privileged(monkeypatch):
    db = _db_with_notification("Misafir ahmet@example.com için onay e-postası")
    monkeypatch.setattr(messaging, "_get_db", lambda: db)
    res = await messaging.get_messaging_activity(
        limit=20, current_user=_user(UserRole.HOUSEKEEPING)
    )
    msg = res["activities"][0]["message"]
    assert "ahmet@example.com" not in msg
    assert "a***@example.com" in msg


@pytest.mark.asyncio
async def test_activity_shows_notification_freetext_for_privileged(monkeypatch):
    db = _db_with_notification("Misafir ahmet@example.com için onay e-postası")
    monkeypatch.setattr(messaging, "_get_db", lambda: db)
    res = await messaging.get_messaging_activity(
        limit=20, current_user=_user(UserRole.FRONT_DESK)
    )
    assert "ahmet@example.com" in res["activities"][0]["message"]
