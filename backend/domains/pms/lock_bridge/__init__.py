"""Lock-bridge: vendor-neutral outbound command queue for physical door locks.

Brassco (and similar offline RFID keycard systems) integrate via on-prem
software (e.g. Brassco BKY on a Windows PC) exposed only through a local DLL, not
a public cloud API. So the Syroce cloud cannot talk to the lock directly: instead
it emits hardware-agnostic lock commands (encode / revoke a card) into a
tenant-scoped, idempotent queue. A small on-prem connector pulls pending commands
over an authenticated endpoint, drives the vendor DLL to encode/cancel the
physical card, and acknowledges the result. The wire contract carries no guest
PII and is deliberately vendor-neutral so a thin per-vendor adapter can wrap it.
"""
