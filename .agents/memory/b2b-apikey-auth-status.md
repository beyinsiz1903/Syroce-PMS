---
name: B2B API-key auth deny-path status
description: Why missing X-API-Key must return 401 not 422 across b2b sub-routers, and the FastAPI required-header gotcha behind it.
---

# B2B API-key auth deny-path status

The `/api/b2b/*` sub-routers authenticate via an `X-API-Key` header inside a shared
`get_b2b_agency` dependency that is **inlined/auto-split into ~13 separate files**
(`backend/routers/b2b_api/*.py`) — each file carries its own copy, so any change to
the auth dependency must be applied to all of them in lockstep.

## Rule
A **missing** (or empty-string) `X-API-Key` must return **401** (auth deny), not 422.

**Why:** If the header param is declared required (`Header(..., alias="X-API-Key")`),
FastAPI rejects a missing header with a **422 request-validation error before the
handler runs**, so the auth logic never executes. The stress auth-matrix spec
(`41B-b2b-subrouter-matrix`, added after the Run #162 baseline) asserts the deny path
must be 401/403/404 (a 2xx would be a P0 bypass). 422 is not a bypass but a wrong
status that lets callers fingerprint "missing" vs "invalid" key. A 422-on-missing
caused a P1 NO-GO on the full stress suite.

## How to apply
Declare the header optional and guard explicitly at the top of `get_b2b_agency`:
```python
x_api_key: str | None = Header(None, alias="X-API-Key")
...
if not x_api_key:
    raise HTTPException(status_code=401, detail="API key gerekli")
```
Bogus-key → 401 (key_doc miss) and inactive-agency → 403 paths are unchanged.
Backend tests that assert the deny status live in `test_b2b_api.py` and
`test_b2b_webhooks.py` — keep them at 401.

**Same pattern, different surface:** `backend/routers/marketplace_b2b.py` has its own
`get_marketplace_agency` with the same required-header gotcha (still 422 on missing).
It is outside `/api/b2b/*` and was not the P1 trigger; fix it only if the policy is
"all API-key auth returns 401".
