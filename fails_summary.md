# Stress Test Failures

### ERROR 1
```
✘  720 [stress] › e2e-stress/specs/99B-folio-split-surface.spec.js:387:9 › F9E § 99B — Folio Split (Fatura Ayrıştırma) Surface › E) Anonymous (no token) split → 401/403 (10ms)
Error: [stress-teardown] ❌ Defense invariant violation(s): cleanup#1 status=401; cleanup#2 NOT idempotent (status=401 body={"error":"{\"detail\":\"Token expired - please login again\"}"}); pilot_drift=-12 (must be 0)

at ../global-teardown.js:97

95 |     if (driftStep && driftStep.drift !== 0) violations.push(`pilot_drift=${driftStep.drift} (must be 0)`);
96 |     if (violations.length) {
>  97 |         throw new Error(`[stress-teardown] ❌ Defense invariant violation(s): ${violations.join('; ')}`);
|               ^
98 |     }
Error: setup vacant pool yetersiz: eligible=15 target_total=50 required_min=30
```

### ERROR 2
```
2) [stress] › e2e-stress/specs/10-qr-requests.spec.js:46:9 › F8B § 10 — Room QR requests › A) 50 public QR submit (different rooms — under per-room RL)
Error: public submit ok>=45/50 floor; got ok=0 fail=50 throttled=0

expect(received).toBeGreaterThanOrEqual(expected)

Expected: >= 45
Received:    0

135 |         const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'public_submit_50', stressState, request, stressTokens.pilot_token);
136 |         expect(extOk, 'public_submit_50 sonrası external_calls invariant').toBe(true);
```

### ERROR 3
```
3) [stress] › e2e-stress/specs/13-messaging.spec.js:29:9 › F8B § 13 — Messaging dry-run › A) 50 send: 20 email + 15 sms + 15 whatsapp (lokal-only)
Error: messaging send floor>=48; got total_ok=35

expect(received).toBeGreaterThanOrEqual(expected)

Expected: >= 48
Received:    35

84 |         const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'send_50_all_channels', stressState, request, stressTokens.pilot_token);
85 |         expect(extOk, 'send_50 sonrası external_calls invariant').toBe(true);
```

### ERROR 4
```
4) [stress] › e2e-stress/specs/14-mice-events.spec.js:95:9 › F8C § 14 — MICE Events › B) Bulk create — N events status=lead, unique (space, date)
Error: bulk_create floor>=9; got ok=0

expect(received).toBeGreaterThanOrEqual(expected)

Expected: >= 9
Received:    0

157 |         const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'bulk_create', stressState, request, stressTokens.pilot_token);
158 |         expect(extOk).toBe(true);
```

### ERROR 5
```
5) [stress] › e2e-stress/specs/15-sales-opportunities.spec.js:54:9 › F8C § 15 — Sales-catering Opportunities › A) List + pipeline aggregation read
Error: expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

69 |         if (!ok) recFinding(testInfo, 'P2', MOD, 'Opportunity list/pipeline non-2xx',
70 |             `list=${listR.status} pipe=${pipeR.status}`);
> 71 |         expect(listR.ok).toBe(true);
|                          ^
```

### ERROR 6
```
6) [stress] › e2e-stress/specs/16-sales-leads.spec.js:33:9 › F8C § 16 — Sales Leads › A) List + funnel aggregation read
Error: expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

45 |         if (!ok) recFinding(testInfo, 'P2', MOD, 'Leads list/funnel non-2xx',
46 |             `list=${listR.status} funnel=${funnelR.status}`);
> 47 |         expect(listR.ok).toBe(true);
|                          ^
```

### ERROR 7
```
7) [stress] › e2e-stress/specs/32-hr-performance-lifecycle.spec.js:157:9 › F8D-v2 § 32 — HR Performance Review Lifecycle › C) Check-in LIST + DELETE cleanup (idempotent residue=0)
Error: list+delete+idempotent contract

expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

199 |         const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'checkin_cleanup', stressState, request, stressTokens.pilot_token);
200 |         expect(extOk).toBe(true);
```

### ERROR 8
```
8) [stress] › e2e-stress/specs/35B-hr-shift-coverage-planning.spec.js:121:9 › F8D-v3 § 35B — Shift Coverage Planning › B) Idempotency replay — same payload create twice returns the SAME rule (no 500, no duplicate)
Error: idem replay: r1=401 r2=401 id1=undefined id2=undefined replay_flag=false

expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

160 |         const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'idem_window', stressState, request, stressTokens.pilot_token);
161 |         expect(extOk).toBe(true);
```

### ERROR 9
```
9) [stress] › e2e-stress/specs/42-ai-upsell-dryrun.spec.js:58:9 › F8O § 42 — AI Upsell Dry-run › Setup: prefix + pilot baseline + LLM diagnostics + env guards + insights probe
Error: LLM diagnostics endpoint must be reachable (got status=401)

expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

71 |             rec(testInfo, { module: MOD, step: 'setup', status: 'FAIL',
72 |                 note: `ledger_baseline_unavailable status=${snap.status}` });
```

### ERROR 10
```
10) [stress] › e2e-stress/specs/43-ai-pricing-dryrun.spec.js:66:9 › F8O § 43 — AI Dynamic Pricing Dry-run › Setup: prefix + pilot baseline + LLM diagnostics + env guards + recommend probe
Error: LLM diagnostics endpoint must be reachable (got status=401)

expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

75 |             rec(testInfo, { module: MOD, step: 'setup', status: 'FAIL',
76 |                 note: `ledger_baseline_unavailable status=${snap.status}` });
```

### ERROR 11
```
11) [stress] › e2e-stress/specs/44-ai-noshow-risk-dryrun.spec.js:67:9 › F8O § 44 — AI No-Show Risk Dry-run › Setup: prefix + pilot baseline + LLM diagnostics + env guards + booking field snapshot + no-show probe
Error: LLM diagnostics endpoint must be reachable (got status=401)

expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

76 |             rec(testInfo, { module: MOD, step: 'setup', status: 'FAIL',
77 |                 note: `ledger_baseline_unavailable status=${snap.status}` });
```

### ERROR 12
```
12) [stress] › e2e-stress/specs/97-backend-router-coverage-probe.spec.js:253:9 › F9B § Backend Router Coverage Probe › invariants: probe coverage summary
Error: P1: anonymous bypass on any router probe

expect(received).toBe(expected) // Object.is equality

Expected: 0
Received: 19

262 |         // Doctrine gate: hiçbir 5xx olmamalı
263 |         expect(probeStats.p1_5xx, 'P1: backend 5xx on any router probe').toBe(0);
```

### ERROR 13
```
13) [stress] › e2e-stress/specs/98-efatura-earsiv-dryrun.spec.js:50:9 › F8X efatura/earsiv dryrun › read-only invoice surface + schema enforcement
Error: invalid customer_tax_id 123 must be 422

expect(received).toBe(expected) // Object.is equality

Expected: 422
Received: 401

143 |                             `POST /api/invoices customer_tax_id=${bad} → 422 but customer_tax_id absent from error loc; rejection may be incidental, not a tax-id guard.`);
144 |                     }
```

### ERROR 14
```
14) [stress] › e2e-stress/specs/98-fnb-beo-generator.spec.js:659:9 › F9C § 98 — F&B BEO Generator Lifecycle › K) Anonymous (headerless) GET /api/mice/events → 401/403
Error: K_anon: headerless request returned 429 (expected 401/403)

expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

679 |                 `PUBLIC SURFACE LEAK — tenant event data may be reachable without auth. body=${bodySnippet}`);
680 |         }
```

### ERROR 15
```
15) [stress] › e2e-stress/specs/98-maintenance-workorder-lifecycle.spec.js:408:9 › F9C § 98 — Maintenance Work Order Lifecycle › K) Anonymous (headerless) GET → 401/403
Error: K_anon: headerless request returned 429 (expected 401/403)

expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

428 |                 `PUBLIC SURFACE LEAK — tenant data may be reachable without auth. body=${bodySnippet}`);
429 |         }
```

### ERROR 16
```
16) [stress] › e2e-stress/specs/98-marketplace-deep-lifecycle.spec.js:477:9 › F9C § 98 — Marketplace Deep Lifecycle › J) IDOR: cross-tenant probes → no mutation / no leak
Error: J3: cross-tenant cancel unexpected status=401 (expected 403/404)

expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

535 |         }
536 |         expect(r3.status >= 400, `J3: cross-tenant PO cancel succeeded (${probeKind2})`).toBe(true);
```

### ERROR 17
```
17) [stress] › e2e-stress/specs/98-messaging-template-lifecycle.spec.js:944:9 › F9C § 98 — Messaging Template Lifecycle › K) Anonymous headerless GET /templates → 401/403
Error: K_anon: headerless request returned 429 (expected 401/403)

expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

964 |                 `PUBLIC SURFACE LEAK — template data may be reachable without auth. body=${bodySnippet}`);
965 |         }
```

### ERROR 18
```
18) [stress] › e2e-stress/specs/98-mobile-cashier-surface.spec.js:577:9 › F9C § 98 — Mobile Cashier Surface › K) Anonymous (headerless) GET → 401/403
Error: K_anon: headerless returned 429 (expected 401/403)

expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

595 |                 `PUBLIC FINANCIAL SURFACE LEAK — tenant cashier state may be reachable without auth. body=${bodySnippet}`);
596 |         }
```

### ERROR 19
```
19) [stress] › e2e-stress/specs/98-mobile-staff-surface.spec.js:467:9 › F9C § 98 — Mobile Staff Surface › K) Anonymous (headerless) GET handover list → 401/403
Error: K_anon: headerless request returned 429 (expected 401/403)

expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

486 |                 `PUBLIC SURFACE LEAK — tenant data may be reachable without auth. body=${bodySnippet}`);
487 |         }
```

### ERROR 20
```
20) [stress] › e2e-stress/specs/98-ops-surface-smoke.spec.js:86:9 › F8AH ops surface smoke stress › A) cross_property_rollup — guest-search smoke + cross-tenant leak guard
Error: stress search http=401

expect(received).toBe(expected) // Object.is equality

Expected: 200
Received: 401

105 |             const sRes = await callTimed(request, 'get',
106 |                 `/api/cross-property/guests/search?q=STRESS&limit=50`, undefined, sToken);
```

### ERROR 21
```
21) [stress] › e2e-stress/specs/98-pos-deep-lifecycle.spec.js:152:9 › F8Z v2 pos deep lifecycle › B) Lifecycle: create → close (post_to_folio=false, no folio, no Xchange)
Error: expect(received).toBeLessThan(expected)

Expected: < 300
Received:   401

167 |             }, sToken);
168 |             expect(create.status, `create http=${create.status} body=${JSON.stringify(create.body).slice(0,200)}`).toBeGreaterThanOrEqual(200);
> 169 |             expect(create.status).toBeLessThan(300);
|                                   ^
```

### ERROR 22
```
22) [stress] › e2e-stress/specs/98-pos-kds-inventory.spec.js:246:9 › F8Z.2 pos kds + fnb inventory › B) Kitchen-order lifecycle: create → preparing → ready → served + terminal-state guard
Error: create http=401 body={"detail":"Token expired - please login again"}

expect(received).toBeLessThan(expected)

Expected: < 300
Received:   401

261 |             };
262 |             const create = await callTimed(request, 'post', '/api/fnb/kitchen-order', createBody, sToken);
```

### ERROR 23
```
23) [stress] › e2e-stress/specs/98-rms-revenue-deep.spec.js:171:9 › F8AF revenue_management deep stress › B) Policy update (advisory + thresholds) + demand-forecast POST (short range)
Error: expect(received).toBeLessThan(expected)

Expected: < 300
Received:   401

190 |             expect(polPut.status, 'autopilot policy PUT must be 2xx for stress tenant')
191 |                 .toBeGreaterThanOrEqual(200);
> 192 |             expect(polPut.status).toBeLessThan(300);
|                                   ^
```

### ERROR 24
```
24) [stress] › e2e-stress/specs/98-sales-basic-lifecycle.spec.js:546:9 › F9C § 98 — Sales Basic Lifecycle › K) Anonymous (headerless) GET /api/sales/leads → 401/403
Error: K_anon: headerless request returned 429 (expected 401/403)

expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

566 |                 `PUBLIC SURFACE LEAK — tenant lead data may be reachable without auth. body=${bodySnippet}`);
567 |         }
```

### ERROR 25
```
25) [stress] › e2e-stress/specs/98-spa-wellness-operational.spec.js:66:9 › F8AB spa wellness operational stress › Setup: probe catalog surfaces + prefix
Error: spa services must seed (got 0)

expect(received).toBeGreaterThan(expected)

Expected: > 0
Received:   0

134 |             // instead of downgrading to a P2 SKIP — an empty catalog here is a real
135 |             // seeding/authorization failure, not a benign skip.
```

### ERROR 26
```
26) [stress] › e2e-stress/specs/98C-twofa-totp-lifecycle.spec.js:196:9 › F8AG § 98C — 2FA TOTP Lifecycle › Setup: pilot baseline + module probe + status snapshot
Error: 2FA status probe non-2xx status=401

expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

230 |             rec(testInfo, { module: MOD, step: 'setup', status: 'FAIL',
231 |                 note: `module_blocked=true reason=${blockedReason}` });
```

### ERROR 27
```
27) [stress] › e2e-stress/specs/98D-peer-login-throttle.spec.js:282:9 › § 98D — Peer login throttle (agency + vendor) › B) Vendor per-account boundary — 1 email × 11 wrong, 11th = 429
Error: per-account boundary expected 10 (11th=429), got trip_index=0

expect(received).toBe(expected) // Object.is equality

Expected: 10
Received: 0

341 |                     `statuses=${JSON.stringify(statuses)} trip=${trip + 1}. beklenen=${PER_ACCOUNT_CAP + 1}. — önceki round residue veya yanlış cap.`);
342 |             }
```

### ERROR 28
```
28) [stress] › e2e-stress/specs/99-finance-folio-surface.spec.js:733:9 › F9D § 99 — Finance Folio & Guest-Purchase Surface › J) Anonymous GET /api/folio/list → 401/403
Error: J_anon: headerless returned 429 (expected 401/403)

expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

751 |                 `PUBLIC FINANCIAL SURFACE LEAK — folio list reachable without auth. body=${bodySnippet}`);
752 |         }
```

### ERROR 29
```
29) [stress] › e2e-stress/specs/99-pos-extensions.spec.js:81:9 › F8AI POS Extensions › A) Currency: upsert rate + foreign payment idempotency + cross-tenant guard
Error: expect(received).toBe(expected) // Object.is equality

Expected: 200
Received: 401

89 |             const rateBody = { currency_code: 'USD', rate_to_base: 32.5, note: `${prefix}rate` };
90 |             const r1 = await callTimed(request, 'post', '/api/pos/ext/currency/rates', rateBody, sToken);
> 91 |             expect(r1.status).toBe(200);
|                               ^
```

### ERROR 30
```
30) [stress] › e2e-stress/specs/99B-folio-split-surface.spec.js:387:9 › F9E § 99B — Folio Split (Fatura Ayrıştırma) Surface › E) Anonymous (no token) split → 401/403
Error: anonymous folio split not blocked status=429

expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

403 |             status: blocked ? 'PASS' : 'FAIL', http: status, note: 'expected 401/403',
404 |         });
```

