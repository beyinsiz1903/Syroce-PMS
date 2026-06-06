---
name: Search param silently ignored + full-list cache guard coupling
description: A frontend ?search= box that returns nothing/wrong rows is often the endpoint never declaring the param; and any new filter param MUST be added to the full-list use_cache guard.
---

A search box that types a value and gets no (or wrong) results is frequently NOT a
data problem — the backend endpoint never declared the query param, so FastAPI
silently drops it (extra query params don't 422). The handler then returns the full
list and the frontend's `.slice(0,N)` shows unrelated rows → user reads it as "no
results".

**Two coupled fixes are required, not one:**
1. Declare the param (`search: str | None = None`) and apply the filter
   (tenant-scoped; for an id/number field use an ANCHORED prefix regex `^` +
   `re.escape(... .replace("\x00",""))` so it's regex-injection-safe AND
   index-serviceable when a `(tenant_id, <field>)` index exists).
2. Add the new param to the endpoint's full-list `use_cache` guard
   (`... and not search and ...`). **Why:** these read endpoints serve a cached
   FULL list when offset==0 / no filters / limit>=100. If the new filter param is
   missing from that guard, a filtered request is served the cached UNFILTERED list
   and the filter is silently ignored — a cache-shaped fake-green.

**How to apply:** whenever you add a filter/search param to a list endpoint that has
a full-list cache fast-path, grep the `use_cache = (...)` condition in the same
handler and add the new param to it in lockstep. Verify a `(tenant_id, field)` index
exists before relying on the anchored-prefix regex for performance.

Concrete instance: `GET /pms/rooms` (backend/routers/pms_rooms.py) ignored `search`;
GlobalSearch.jsx calls `/pms/rooms?search=`. Fix added the param + room_number
anchored prefix + `not search` in use_cache. Index `idx_rooms_tenant_number` already
present.
