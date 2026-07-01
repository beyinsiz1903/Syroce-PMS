"""Mailing placeholder substitution defenses (Bug CN — April 2026).

`_personalize()` substitutes `{{name}}`, `{{hotel}}`, `{{misafir}}`, `{{otel}}`
into outbound mailing campaign HTML and subject. Pre-CN both substitutions
were a raw `str.replace`, which let three classes of payload bleed through:

1. **HTML injection in `name`** — guest_name is populated by sources we do
   NOT fully control (online check-in form, kiosk, channel-manager push,
   agency import). A guest_name like
       <a href="https://evil/phish">Bedava içecek için tıklayın</a>
   appears verbatim inside the hotel's branded transactional email. The
   recipient sees a phish link wearing the hotel's `From:` header — a
   classic brand-spoofing amplifier.

2. **HTML injection in `hotel`** — `tenant.property_name` is set by the
   tenant admin. Pre-CN a malicious `<script>...</script>` reached every
   guest mail this tenant ever sent (and any cross-tenant operator viewing
   the mail in a help-desk webview).

3. **Header injection via subject (`\r\n`)** — subject also runs through
   the same substitution. CRLF in `name` produced a subject string with
   embedded `\r\n` that some SMTP relays will gladly turn into a `Bcc:`
   header (provider-dependent; Resend's JSON body is mostly safe today,
   but the defense must not depend on the provider's filtering).

This module provides two narrow sanitizers:

- `safe_html_value(v)` — `html.escape(v, quote=True)` for HTML body cells.
  Guest/hotel names are inline text, never markup, so this is loss-free.
- `safe_subject_value(v)` — strips CR / LF / NUL / other C0 controls so
  the subject can never break the header line.
"""

from __future__ import annotations

import html as _html

# C0 + DEL — anything that could split a header or hide payload.
_BAD_SUBJECT_CHARS = {chr(c) for c in range(0x00, 0x20)} | {"\x7f"}


def safe_html_value(v) -> str:
    """HTML-escape a substitution value before injecting into a mail body."""
    if v is None:
        return ""
    return _html.escape(str(v), quote=True)


def safe_subject_value(v) -> str:
    """Strip control chars from a substitution value before injecting into a subject."""
    if v is None:
        return ""
    return "".join(ch for ch in str(v) if ch not in _BAD_SUBJECT_CHARS)
