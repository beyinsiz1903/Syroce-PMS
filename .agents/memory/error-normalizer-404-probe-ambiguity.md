---
name: Error-normalizer makes live 404 probes ambiguous
description: Why a live curl 404 can't tell route-not-mounted from a handler's own 404, and how to confirm
---

The backend's "Error response normalizer middleware" rewrites handler-raised
`HTTPException(404, "Rezervasyon bulunamadı")` bodies to the generic
`{"detail":"Not Found"}` — identical to FastAPI's route-not-matched 404.

**Why:** intentional info-leak hardening; clients must not learn which detail a
handler emitted.

**How to apply:** when probing whether a new route is mounted/reachable live,
do NOT rely on the 404 body to distinguish "route missing" from "handler's own
not-found guard". Confirm mounting via `GET /api/openapi.json` (paths list) and
compare the probe's status+body against a known-working sibling endpoint on the
same router with a bad id — if they match byte-for-byte, the new route is live
and its guard fires the same way.
