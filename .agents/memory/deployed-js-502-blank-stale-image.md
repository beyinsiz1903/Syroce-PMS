---
name: Deployed /js 502 blank = stale/broken deployed image, not code
description: How to tell a blank deployed SPA is a stale/broken deploy image (re-publish) vs an app code bug, on the Syroce web+backend deploy.
---

# Blank deployed SPA where /js chunks 502 at the edge

Symptom: the deployed web app (`...-syroce.replit.app`, uvicorn web+backend) renders
a blank white screen.

Discriminating probes (run against the deployed host):
- `GET /` -> 200 (index.html), `GET /assets/*.css` -> 200 (even cache-busted, even gzip)
- `GET /health*` -> 200 fast; `HEAD /js/<chunk>.js` -> 200 with real content-length
- `GET /js/<chunk>.js` -> **502 `The deployment could not be reached`** (edge proxy
  body, no app headers), consistent across retries, both with and without gzip
- `GET /js/<missing>.js` -> the APP's 404 JSON (so `/js` requests DO reach the app)

Reading: the live app is healthy and `/js` routing reaches it, but the edge cannot
deliver the BODY of EXISTING `/js` files (HEAD/stat ok, GET body fails -> reset/timeout
-> 502). `/assets` served by the identical StaticFiles mount works.

Decisive test: run the SAME code locally (backend serving `frontend/build`) and
`curl localhost:8000/js/<chunk>.js`. If local returns 200 (it did), it is NOT a code
bug — it is a broken/stale deployed image/build. The deployed `index.html` referenced a
chunk hash that did not even exist in the current local build (deployed image was an
older build).

**Remedy:** re-publish that deployment with a fresh build. Do NOT change app serving
code — `/js` and `/assets` use the same mount; GZip is not the cause (CSS compresses
fine at 200). A code edit here would be fake-green.

## Two-deploy gotcha when reasoning about this
`getDeploymentInfo()` returns the repl's PRIMARY managed deploy = the STATIC mobile app
(`...-1.replit.app`, `deploymentType:"static"`, `publicDir: mobile/dist`), NOT the
`-syroce` web+backend host. `.replit` `[deployment]` is set to the static/mobile target.
`fetch_deployment_logs` is tied to that static primary, so it returns "No deployment
logs found" for the `-syroce` backend — you cannot introspect `-syroce` logs from the
agent; HTTP probing is the only lever. The two deploys coexist by design (mobile static
talks to the `-syroce` backend). Re-publishing the repl's primary would touch the static
mobile deploy, not `-syroce`; flipping `.replit` to the VM/backend target changes what
Publish deploys and risks the mobile deploy — get operator sign-off first.
