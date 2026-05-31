---
name: SOAP/OTA fault code is not the HTTP status
description: An OTA webhook can return a SOAP fault whose Code="400" while the HTTP response is still 200; malformed-input 2xx only surfaces once an IP-gate bypass is active.
---

A SOAP/OTA fault envelope carries its own fault `Code` attribute (e.g. `"400"`,
`"404"`) inside the XML body. That attribute is NOT the HTTP status. A shared XML
response helper can default `status_code=200`, so a handler that builds a fault
body with `Code="400"` and forgets to pass the HTTP status returns **HTTP 200 +
SOAP fault** — an ambiguous "success" for invalid input.

**Why it stayed hidden:** the malformed-input branches (empty body, unparseable
XML) sit *after* the IP allowlist gate. In normal posture the gate returns 503
first, so those branches are never reached and the latent 2xx-on-garbage bug is
invisible. It only becomes a stress P0 once a test-auth bypass (e.g. Exely
`open_for_testing`) skips the IP gate and exercises the body-validation path.

**The policy that resolved it (operator-approved):**
- Transport-level malformed input (empty body, unparseable / hostile XML) →
  **HTTP 400** (pass an explicit `status_code`, do not rely on the helper default).
- Business / resource / protocol faults (unknown hotel code, tenant-binding
  violation, well-formed XML missing required OTA structure) → **HTTP 200 + SOAP
  fault**, per the OTA no-retry convention (a 4xx/5xx makes the OTA retry a
  request that will never succeed).

**How to apply:** when auditing any OTA/SOAP webhook, distinguish the fault
`Code` attribute from the HTTP status, and split malformed-transport (4xx) from
business-fault (200+fault) deliberately. When a stress finding flags 2xx on
garbage, check whether a bypass just unmasked a pre-existing branch rather than
assuming the bypass itself introduced the bug.
