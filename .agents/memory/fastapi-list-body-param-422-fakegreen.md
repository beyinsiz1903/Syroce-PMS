---
name: FastAPI list-body param 422 silently fake-greens negative tests
description: An endpoint with a list[int]|None body param + scalar query params 422s on a {} body; negative tests asserting status>=400 pass for the WRONG reason.
---

# list[int]|None body param → 422 on `{}` body

A FastAPI handler whose only body-typed parameter is `items: list[int] | None = None`
(all other params are scalars → query) expects the REQUEST BODY to be a JSON array.
Posting an empty object `{}` as the body → `422 {"type":"list_type","loc":["body"]}`
BEFORE the handler runs. Posting NO body (helper sends `null`/`undefined` → no `data`,
no Content-Type) → `items=None` → handler executes normally.

**The trap:** a happy-path test asserting `status===200` correctly catches this. But the
sibling NEGATIVE tests (bogus-id → expect 404, cross-tenant → expect >=400) assert only
`status >= 400`. A 422 body-validation error satisfies `>=400`, so those tests PASS
without ever reaching the real 404 / tenant-isolation guard — silent fake-green.

**Rule:** fix the TEST to send a null body (not `{}`) so the request reaches the handler;
the negative tests then exercise the real guard. Do NOT change the endpoint signature to
"accept" `{}` just to make the happy path green — that masks the latently-fake-green
negatives.

**How to apply:** when a transfer/action endpoint takes scalars in the query and a single
`list | None` body param, callers must send the list (or no body), never `{}`. In the
stress harness `callTimed(request, method, path, null, token)` sends no body at all.
