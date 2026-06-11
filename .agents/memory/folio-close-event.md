---
name: folio.closed.v1 e-Fatura readiness event
description: Why the folio-close SXI event is reference-based (no PII), how the off-hot-path outbox sweep stays idempotent, and the bus-DB rebind needed under Celery.
---

# folio.closed.v1 — reference-based e-Fatura event

The PMS is the authoritative data provider for Turkish e-Fatura. On folio close it
publishes a REFERENCE-BASED SXI event: identifiers + light monetary context + a
signed, time-limited fetch URL only. External middleware pulls authoritative,
decrypted invoice data from the signed public endpoint.

## Why no PII ever goes in the envelope
The `generic_webhook` adapter records a request-payload EXCERPT into
`xchange_deliveries` (delivery records). Any guest PII placed in the event payload
would therefore leak into those persisted delivery rows, not just to the partner
wire. So the payload carries ZERO PII; PII is only ever served by the
token-authenticated pull endpoint and audited there.
**How to apply:** never add guest name/email/tc_no/etc. to any SXI envelope that a
logging adapter can excerpt; keep PII behind the signed-URL pull.

## Off-hot-path delivery (no folio-close site is wired)
Delivery is a Celery beat sweep (`folio_closed_event_sweep_task`, */5) keyed off
the folio document itself — the source of truth — so NO folio-close request path is
modified. Trade-off accepted: a few-minutes latency vs. zero hot-path risk.

## Enabling on an existing DB must not replay history
The sweep is gated on `FOLIO_EVENT_EMIT_SINCE` (ISO-8601 watermark, MANDATORY) plus
`PUBLIC_APP_URL` and a signing secret; unset => no-op. Closed folios OLDER than the
watermark are TOMBSTONED (marker stamped, NOT published) so turning the feature on
does not flood middleware with the entire close history.
**Why:** an outbox sweep over a historical collection will otherwise emit every
past close on first run.

## Idempotency model
Marker field `folio_closed_event_emitted_for` = the RAW `closed_at` value; the
re-scan query uses `$expr {$ne:["$closed_at", marker]}` which naturally covers
never-emitted (missing marker = null) AND reopen/reclose (new closed_at != marker)
with no cross-type datetime/string compare. EMIT-then-MARK, mark guarded on the
same `closed_at`. A crash between publish and mark re-publishes, deduped by the
bus' `(tenant_id, message_id, partner_code)` unique index (message_id = event +
folio_id + closed_at, so a reclose is a legitimate NEW message).

## Bus DB rebind under Celery (distinct from the night-audit rebind)
`bus.db` resolves live via a property -> `get_system_db()` -> `core.database._raw_db`.
Night-audit rebinds the ENGINE module globals; the bus needs the CORE.DATABASE
globals rebound. The sweep rebinds `core.database.{client,_raw_db,db}` to a fresh
loop-bound Motor client (asyncio.run closes the loop) and restores + closes in
`finally`. Safe only under prefork (one task/process); would race under
threaded/gevent pools — same constraint the existing tasks already accept.

## Public pull endpoint posture
`GET /api/public/finance/folio/{id}/einvoice-data?tenant_id&exp&token`. No JWT;
the HMAC token IS the authorization, bound to (tenant_id, folio_id, STORED
closed_at, exp) so a reopen/reclose invalidates any previously-issued token. Gating
read is raw db + explicit tenant filter (no context), then `set_tenant_context`
AFTER verification to reuse scoped helpers (`_legacy_get_folio_details`, audit);
the tenant middleware's finally-block clears it. Already throttled by the global
`/api` rate limiter (no per-route limiter needed). Missing secret => 503
(fail-closed), bad/expired token => 403, missing/foreign/not-closed folio => 404.
