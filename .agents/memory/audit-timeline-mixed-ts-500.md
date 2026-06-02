---
name: Mixed-type timestamp sort & post-handler encode 500s
description: Why audit/folio aggregation endpoints 500 on production data, and the two doctrine-safe fixes (type-safe sort key + JSON-native page sanitize)
---

# Two same-class 500 modes in aggregation/read endpoints

Production/pilot Mongo holds the SAME logical field written by different writers
over time, so a single response page can mix value types. Two distinct crash
modes follow, both surfacing as an opaque HTTP 500:

## Mode A — Python `list.sort()` over mixed-type timestamps
Sorting a list where `timestamp`/`performed_at`/`voided_at` is `datetime` for
some rows and `str`/`None` for others raises
`TypeError: '<' not supported between instances of 'datetime.datetime' and 'str'`.

**Fix:** a tiny `_ts_sort_key(value)` that coerces to a comparable string
(`None`->"", `datetime`/`date`->`.isoformat()`, else `str(value)`). Use it as the
`key=` in every `.sort()` over a timestamp-ish field.
`x.get('f') or ''` is NOT enough — it only handles None, not datetime+str mix.

## Mode B — FastAPI encodes the return value OUTSIDE the handler try/except
A stray non-JSON-native field on any returned row (BSON `Decimal128`, naive
`datetime`, `ObjectId`, encrypted-field `bytes`) makes FastAPI's encode step
500 AFTER the handler returned — so the endpoint's own try/except never sees it.
Reproduces only at larger `limit` windows where a stray-typed legacy row enters
the page.

**Fix:** recursively sanitize the page to JSON-native types BEFORE returning
(`_json_safe`): datetime/date->isoformat, Decimal128->str, Decimal->float,
ObjectId->str, dict/list recurse. **bytes/bytearray -> `"<binary>"` REDACTED**,
never base64 — these can be encrypted/PII blobs, so redaction keeps it off the
disclosure path.

**Why:** these are real backend bugs the stress suite legitimately caught
(folio detail 500 -> charges=[] -> chargeId=null double-counted as
no_charge_found). Fixing the backend is doctrine-correct; loosening the spec
would be fake-green.

**How to apply:** any read/aggregation endpoint that (1) `.sort()`s a Mongo
timestamp field or (2) returns raw Mongo docs is a candidate. Many siblings
across cashier/pos/mobile/channel_manager routers still use the unsafe
`x['ts']`/`or ''` pattern — latent same-class risk, fix when their domain is
under test rather than blanket-refactoring. Caveat: ISO-string lexical sort is
crash-proof and deterministic but not strictly chronological across mixed TZ
offsets — acceptable vs a 500; switch to UTC-epoch parsing only if strict
chronology is later required.
