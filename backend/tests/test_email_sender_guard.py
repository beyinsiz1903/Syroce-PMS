"""Backend tests for the e-mail sender (``from``) pre-flight guard.

Resend rejects a malformed ``from`` header with a HARD "Invalid `from` field"
validation error that Sentry surfaces as a high-priority alert on EVERY send.
`send_email` therefore pre-flights the sender (``from_addr`` or the
``RESEND_FROM`` default) with the same intent as the recipient guard: a
malformed value is logged at WARNING and skipped locally instead of paging.

These tests lock in:

1. ``_is_valid_sender`` accepts the two Resend-accepted forms (bare address and
   ``Name <addr>``) and rejects everything else.
2. ``send_email`` returns ``{"sent": False, "provider": "skipped",
   "error": "invalid_sender"}`` and never reaches the provider when the sender
   is malformed.
3. A valid recipient is checked BEFORE the sender (recipient guard precedence).
"""
from __future__ import annotations

import pytest

from core.email import _is_valid_sender, send_email


class TestIsValidSender:
    @pytest.mark.parametrize(
        "sender",
        [
            "noreply@hotel.com",
            "Syroce <noreply@hotel.com>",
            "Syroce PMS <onboarding@resend.dev>",
            "  spaced@hotel.com  ",
        ],
    )
    def test_accepts_valid_forms(self, sender):
        assert _is_valid_sender(sender) is True

    @pytest.mark.parametrize(
        "sender",
        [
            None,
            "",
            "   ",
            "Just A Name",
            "missing-at-sign",
            "no-tld@hotel",
            "Name <bad-addr>",
            "Name <missing@tld>",
            "two@@ats.com",
            42,
        ],
    )
    def test_rejects_invalid_forms(self, sender):
        assert _is_valid_sender(sender) is False


class TestSendEmailSenderPreflight:
    @pytest.mark.asyncio
    async def test_malformed_from_addr_skips_without_provider(self, monkeypatch):
        # Even with an API key present, a bad sender must skip locally.
        monkeypatch.setenv("RESEND_API_KEY", "re_dummy_key")
        out = await send_email(
            to="guest@hotel.com",
            subject="hi",
            html="<p>hi</p>",
            from_addr="Just A Name",
        )
        assert out == {
            "sent": False,
            "provider": "skipped",
            "error": "invalid_sender",
        }

    @pytest.mark.asyncio
    async def test_invalid_recipient_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "re_dummy_key")
        out = await send_email(
            to="not-an-email",
            subject="hi",
            html="<p>hi</p>",
            from_addr="Just A Name",
        )
        assert out["error"] == "invalid_recipient"
