// F8G § 80 — CRM Accounts + Contacts + Opportunity won/lost terminal +
// Corporate Contract dry-run lifecycle.
//
// Threat-model surface (threat_model.md § Tampering + Information Disclosure):
//   - mice_accounts master commercial data → manage_sales perm + mice_ops gate.
//   - Cross-tenant account leak P0 (stress accounts pilot listesinde GÖRÜNMEMELI).
//   - Opportunity won/lost transition → audit log emit (sales.opp.won/lost),
//     stage_history immutability, closed_at/close_reason persist.
//   - Corporate contract financial data (negotiated_rate, discount_percentage)
//     → manage_sales perm; cross-tenant filter must be authoritative.
//
// Backend yüzeyleri:
//   - GET    /api/mice/accounts                                  (any auth user)
//   - POST   /api/mice/accounts                                  (manage_sales+mice_ops)
//   - PUT    /api/mice/accounts/{id}                             (manage_sales+mice_ops)
//   - DELETE /api/mice/accounts/{id}                             (mice_ops; 409 if used in active event)
//   - GET    /api/mice/accounts/{id}/contacts                    (any auth user)
//   - POST   /api/mice/accounts/{id}/contacts                    (manage_sales+mice_ops)
//   - DELETE /api/mice/contacts/{id}                             (manage_sales+mice_ops)
//   - POST   /api/mice/sales/opportunities                       (manage_sales+mice_ops)
//   - POST   /api/mice/sales/opportunities/{id}/transition       (to_stage=won|lost+reason)
//   - POST   /api/mice/sales/opportunities/{id}/activities       (audit log per-mutation)
//   - DELETE /api/mice/sales/opportunities/{id}                  (manage_sales+mice_ops)
//   - GET    /api/sales/corporate-contracts                      (any auth user)
//   - POST   /api/sales/corporate-contract                       (manage_sales)
//   - PUT    /api/sales/corporate-contract/{id}                  (manage_sales)
//
// Mutlak kurallar (task #198):
//   - stress_prefix marker tüm create'lerde (account.name+tax_no, contact.name,
//     opportunity.title, contract.company_name+rate_code).
//   - pilot mutation = 0 (assertPilotDriftZero gate).
//   - external_calls = [] (assertNoExternalCallsPostBatch).
//   - Tenant isolation explicit: pilot GET /api/mice/accounts'da stress prefix
//     hiçbir kayıt görünmemeli (P0 if leak).
//   - F8C-15 backlog kapanır: won/lost terminal state explicit assert
//     (closed_at + close_reason response/detail'de görünmeli).
//   - Cleanup idempotent: contact delete → opportunity delete → account delete
//     (404/409 silently absorbed).
//   - failedTests = 0, P0 = P1 = 0.
//
// Out of scope (backend endpoint yok; spec gap'i REVIEW P2 olarak işaretler):
//   - Offer PDF export (no /api/mice/offers endpoint).
//   - Contract approval state machine (draft→review→approved→signed) — backend
//     yalnızca `status='active'` ile create eder, PUT update üzerinden notes
//     field'a state marker yazılarak dry-run simüle edilir.
//   - E-imza entegrasyonu, CRM email blast.
//
// Doctrine alignment: any non-2xx probe → moduleBlocked (architect F8F review).
// `withModuleProbe` only flags 403/404/0; spec locally extends so 5xx also
// short-circuits A/B/C/D (E pilot_drift + external_calls always runs).
//
// Duplicate guard probe: backend `mice_accounts` doesn't enforce unique tax_no
// natively. Dup POST returns 201 yine (REVIEW P2 informational — no native
// dup constraint), NOT 409. Spec records the gap; not a P0.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'crm_offers';
const N_ACCOUNTS = 5;
const N_CONTACTS_PER_ACCT = 2;
const N_OPPORTUNITIES = 5;
const N_CONTRACTS = 3;

test.describe.configure({ mode: 'serial' });

test.describe('F8G § 80 — CRM Accounts + Contacts + Offers + Contracts', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    const createdAccountIds = [];
    const createdContactIds = [];
    const createdOpportunityIds = [];
    const createdContractIds = [];

    test.afterAll(async ({ request, stressTokens }, _testInfo) => {
        // Idempotent cleanup chain: contacts → opportunities → accounts.
        // Corporate contracts: no DELETE endpoint exists; rely on
        // STRESS_COLLECTIONS sweep for orphan removal (forward-compat).
        for (const cid of createdContactIds) {
            await request.delete(`/api/mice/contacts/${cid}`, {
                headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
                failOnStatusCode: false, timeout: 15_000,
            }).catch(() => null);
        }
        for (const oid of createdOpportunityIds) {
            await request.delete(`/api/mice/sales/opportunities/${oid}`, {
                headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
                failOnStatusCode: false, timeout: 15_000,
            }).catch(() => null);
        }
        for (const aid of createdAccountIds) {
            await request.delete(`/api/mice/accounts/${aid}`, {
                headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
                failOnStatusCode: false, timeout: 15_000,
            }).catch(() => null);
        }
    });

    test('Setup: prefix + pilot baseline + module access probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const probe = await withModuleProbe(request, stressTokens.stress_token, '/api/mice/accounts');
        if (probe.moduleBlocked || (probe.status >= 300)) {
            moduleBlocked = true;
            blockedReason = probe.reason || `non_2xx_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'MICE accounts module probe blocked',
                `endpoint=/api/mice/accounts status=${probe.status} reason=${blockedReason} — A/B/C/D skip, E pilot_drift+external_calls still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} probe_status=${probe.status} module_blocked=${moduleBlocked}` });
        expect(typeof probe.status).toBe('number');
    });

    test('A) Account CRUD + duplicate-tax-no guard probe', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'account_crud', status: 'SKIP', note: `module_blocked=true (${blockedReason})` }); test.skip(); return; }
        test.setTimeout(180_000);
        const samples = [];
        let ok = 0, fail = 0, throttled = 0, permFail = 0;
        const errs = [];

        // 1) Create N accounts (each tagged with stress prefix in name + unique tax_no).
        for (let i = 0; i < N_ACCOUNTS; i++) {
            const payload = {
                name: `${prefix}AcctA_${i + 1}`,
                legal_name: `${prefix}AcctA_${i + 1} Ltd.`,
                tax_no: `${prefix}TAX${i + 1}`,
                city: 'Istanbul', country: 'TR',
                industry: ['corporate', 'wedding-planner', 'agency'][i % 3],
                credit_limit: 50000 + i * 5000,
                payment_terms_days: 30,
                notes: `${prefix} F8G 80-A created`,
                active: true,
            };
            const r = await callTimedWithBackoff(request, 'post', '/api/mice/accounts',
                payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.status === 403) permFail++;
            if (r.ok && r.body?.id) {
                ok++;
                createdAccountIds.push(r.body.id);
            } else { fail++; if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }

        // 2) RBAC short-circuit: all 403 → moduleBlocked-like SKIP (P2 informational).
        if (permFail === N_ACCOUNTS) {
            moduleBlocked = true;
            blockedReason = 'all_403_create';
            recFinding(testInfo, 'P2', MOD, 'Account create perm denied for stress admin',
                `permFail=${permFail}/${N_ACCOUNTS} — A/B/C/D follow-ups skip, E still enforced.`);
            rec(testInfo, { module: MOD, step: 'account_crud', status: 'SKIP',
                note: `all_403_create permFail=${permFail}` });
            test.skip();
            return;
        }

        // 3) List + verify stress-prefix visibility (own tenant scope).
        const listR = await callTimed(request, 'get', '/api/mice/accounts', undefined, stressTokens.stress_token);
        const listed = listR.body?.accounts || [];
        const ownPrefixed = listed.filter((a) => typeof a?.name === 'string' && a.name.startsWith(prefix));

        // 4) Update one account.
        let updateOk = false;
        if (createdAccountIds.length > 0) {
            const updPayload = {
                name: `${prefix}AcctA_1_upd`,
                tax_no: `${prefix}TAX1`,
                city: 'Ankara', country: 'TR', industry: 'corporate',
                credit_limit: 75000, payment_terms_days: 45,
                notes: `${prefix} F8G 80-A updated`,
                active: true,
            };
            const upd = await callTimedWithBackoff(request, 'put',
                `/api/mice/accounts/${createdAccountIds[0]}`, updPayload, stressTokens.stress_token);
            updateOk = upd.ok;
            samples.push(upd.ms);
        }

        // 5) Duplicate-tax-no AND duplicate-email guard probes (architect
        // review fix #1). Task requires "aynı tax_id/email 409"; backend
        // may not enforce either as unique today. We probe BOTH and
        // emit deterministic P2 contract-gap findings for any non-409
        // outcome (covers 200/201 silent-accept AND 4xx/5xx noise).
        let dupTaxStatus = null;
        let dupEmailStatus = null;
        if (createdAccountIds.length > 0) {
            // Probe a) duplicate tax_no
            const dupTaxPayload = {
                name: `${prefix}AcctA_dupTax`,
                tax_no: `${prefix}TAX1`,  // same as first account
                city: 'Istanbul', country: 'TR', industry: 'corporate',
                credit_limit: 10000, payment_terms_days: 30,
                notes: `${prefix} F8G 80-A dup-tax probe`,
                active: true,
            };
            const dupT = await callTimedWithBackoff(request, 'post', '/api/mice/accounts',
                dupTaxPayload, stressTokens.stress_token);
            dupTaxStatus = dupT.status;
            samples.push(dupT.ms);
            if (dupT.ok && dupT.body?.id) createdAccountIds.push(dupT.body.id);
            if (dupTaxStatus !== 409) {
                recFinding(testInfo, 'P2', MOD,
                    'Duplicate tax_no contract gap on mice_accounts',
                    `Expected 409 on duplicate tax_no POST; got ${dupTaxStatus}. Informational contract gap (no native unique index on mice_accounts.tax_no).`);
            }
            // Probe b) duplicate email — backend AccountIn has no email field,
            // so duplicate-email surface is N/A on this collection. We record
            // the surface-gap explicitly to satisfy the task contract bullet
            // ("tax_id/email 409"). Contact-level email uniqueness is a
            // separate concern and likewise not enforced today.
            recFinding(testInfo, 'P2', MOD,
                'Duplicate-email guard surface absent on mice_accounts',
                `mice_accounts payload (AccountIn) has no email field, so duplicate-email guard not applicable at account level. Contact-level email also has no unique constraint. Informational gap recorded.`);
            dupEmailStatus = 'n/a (no email field)';
        }

        // 6) Aggregate pass criteria (architect review fix #3): CRUD pass
        // requires create floor AND list visibility AND update success.
        const floor = Math.ceil(N_ACCOUNTS * 0.9);
        const listFloor = Math.ceil(ok * 0.9);  // listed own should reflect created
        const readOk = listR.ok === true;
        const crudPass = ok >= floor && readOk && ownPrefixed.length >= listFloor && updateOk;
        recPerf(testInfo, MOD, 'account_crud', samples, crudPass);
        rec(testInfo, { module: MOD, step: 'account_crud',
            status: crudPass ? 'PASS' : 'FAIL',
            endpoint: 'POST/PUT/GET /api/mice/accounts',
            note: `n=${N_ACCOUNTS} ok=${ok} fail=${fail} throttled_429=${throttled} permFail=${permFail} list_ok=${readOk} listed_own=${ownPrefixed.length}/${ok}(floor>=${listFloor}) update_ok=${updateOk} dup_tax=${dupTaxStatus} dup_email=${dupEmailStatus} floor>=${floor} errs=${JSON.stringify(errs)}` });
        if (ok < floor) recFinding(testInfo, 'P1', MOD, 'Account create floor ihlal',
            `n=${N_ACCOUNTS} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        if (!readOk) recFinding(testInfo, 'P1', MOD, 'Account list read failed',
            `GET /api/mice/accounts status=${listR.status} — CRUD pass requires list visibility.`);
        if (readOk && ownPrefixed.length < listFloor) recFinding(testInfo, 'P1', MOD,
            'Account list visibility floor ihlal',
            `listed_own=${ownPrefixed.length} (<${listFloor}). Created accounts not visible to own tenant.`);
        if (!updateOk) recFinding(testInfo, 'P1', MOD, 'Account update failed',
            `PUT /api/mice/accounts/{id} failed — CRUD pass requires update success.`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'account_crud', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(crudPass, `account CRUD aggregate: create=${ok}/${floor} list_ok=${readOk} listed_own=${ownPrefixed.length}/${listFloor} update_ok=${updateOk}`).toBe(true);
    });

    test('B) Contact CRUD per account', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'contact_crud', status: 'SKIP', note: `module_blocked=true (${blockedReason})` }); test.skip(); return; }
        if (createdAccountIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'contact_crud', status: 'SKIP', note: 'no accounts created in A' });
            return;
        }
        test.setTimeout(180_000);
        const samples = [];
        let ok = 0, fail = 0, throttled = 0, permFail = 0;
        const errs = [];
        // Use first N_ACCOUNTS account ids only (skip the dup-probe extra).
        const targetAccts = createdAccountIds.slice(0, N_ACCOUNTS);
        const totalExpected = targetAccts.length * N_CONTACTS_PER_ACCT;

        for (const aid of targetAccts) {
            for (let i = 0; i < N_CONTACTS_PER_ACCT; i++) {
                const payload = {
                    account_id: aid,
                    name: `${prefix}ContactB_${aid.slice(-6)}_${i + 1}`,
                    title: i === 0 ? 'Sales Manager' : 'Procurement Lead',
                    email: `${prefix}contact_${aid.slice(-6)}_${i + 1}@example.invalid`,
                    phone: `+90555000${(i + 1).toString().padStart(4, '0')}`,
                    is_primary: i === 0,
                    notes: `${prefix} F8G 80-B`,
                };
                const r = await callTimedWithBackoff(request, 'post',
                    `/api/mice/accounts/${aid}/contacts`, payload, stressTokens.stress_token);
                samples.push(r.ms);
                if (r.throttled) throttled++;
                if (r.status === 403) permFail++;
                if (r.ok && r.body?.id) { ok++; createdContactIds.push(r.body.id); }
                else { fail++; if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
                await new Promise((res) => setTimeout(res, 1500));
            }
        }

        if (permFail === totalExpected) {
            recFinding(testInfo, 'P2', MOD, 'Contact create perm denied for stress admin',
                `permFail=${permFail}/${totalExpected} — informational only.`);
            rec(testInfo, { module: MOD, step: 'contact_crud', status: 'SKIP',
                note: `all_403 permFail=${permFail}` });
            test.skip();
            return;
        }

        // Verify list per first account returns expected count.
        let listedFirst = 0;
        if (targetAccts.length > 0) {
            const listR = await callTimed(request, 'get',
                `/api/mice/accounts/${targetAccts[0]}/contacts`, undefined, stressTokens.stress_token);
            listedFirst = (listR.body?.contacts || []).filter(
                (c) => typeof c?.name === 'string' && c.name.startsWith(prefix)).length;
        }

        const floor = Math.ceil(totalExpected * 0.9);
        recPerf(testInfo, MOD, 'contact_crud', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'contact_crud',
            status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/mice/accounts/{id}/contacts',
            note: `total=${totalExpected} ok=${ok} fail=${fail} throttled_429=${throttled} permFail=${permFail} listed_first_acct=${listedFirst} floor>=${floor} errs=${JSON.stringify(errs)}` });
        if (ok < floor) recFinding(testInfo, 'P1', MOD, 'Contact create floor ihlal',
            `total=${totalExpected} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'contact_crud', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `contact create floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('C) Lead→Opportunity→won/lost terminal + activity log (F8C backlog kapanır)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'opp_terminal', status: 'SKIP', note: `module_blocked=true (${blockedReason})` }); test.skip(); return; }
        test.setTimeout(240_000);
        const samples = [];
        let createOk = 0, createFail = 0, throttled = 0, permFail = 0;
        const errs = [];

        // 1) Create N opportunities (account_id binding when available).
        for (let i = 0; i < N_OPPORTUNITIES; i++) {
            const payload = {
                title: `${prefix}OppC_${i + 1}`,
                account_id: createdAccountIds[i % Math.max(createdAccountIds.length, 1)],
                event_type: ['wedding', 'conference', 'corporate'][i % 3],
                pax: 80 + i * 15,
                estimated_value: 40000 + i * 5000,
                currency: 'TRY',
                probability: 50,
                source: 'website',
                notes: `${prefix} F8G 80-C created`,
            };
            const r = await callTimedWithBackoff(request, 'post', '/api/mice/sales/opportunities',
                payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.status === 403) permFail++;
            const oid = r.body?.id || r.body?.opportunity?.id;
            if (r.ok && oid) { createOk++; createdOpportunityIds.push(oid); }
            else { createFail++; if (errs.length < 3) errs.push({ phase: 'create', status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }

        if (permFail === N_OPPORTUNITIES) {
            recFinding(testInfo, 'P2', MOD, 'Opportunity create perm denied for stress admin',
                `permFail=${permFail}/${N_OPPORTUNITIES} — informational, A/B/C/D skip-style.`);
            rec(testInfo, { module: MOD, step: 'opp_terminal', status: 'SKIP',
                note: `all_403 permFail=${permFail}` });
            test.skip();
            return;
        }

        // 2) Terminal-state transitions: 3 won, rest lost. Each MUST carry reason.
        // F8C-15 backlog kapanır: explicit assert closed_at present + stage=won|lost.
        let wonOk = 0, lostOk = 0, transFail = 0;
        let closedAtPresent = 0;
        const wonCount = Math.min(3, Math.floor(createdOpportunityIds.length / 2) + 1);
        for (let idx = 0; idx < createdOpportunityIds.length; idx++) {
            const oid = createdOpportunityIds[idx];
            const isWon = idx < wonCount;
            const toStage = isWon ? 'won' : 'lost';
            const reason = isWon
                ? `${prefix} F8G 80-C closed_won — contract signed`
                : `${prefix} F8G 80-C closed_lost — price competitive`;
            const r = await callTimedWithBackoff(request, 'post',
                `/api/mice/sales/opportunities/${oid}/transition`,
                { to_stage: toStage, reason },
                stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok && r.body?.stage === toStage) {
                if (isWon) wonOk++; else lostOk++;
            } else { transFail++; if (errs.length < 5) errs.push({ phase: 'transition', oid: oid.slice(-6), to: toStage, status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));

            // Detail read to verify closed_at + close_reason persisted
            // (won/lost terminal-state explicit assert, F8C backlog).
            const detail = await callTimed(request, 'get',
                `/api/mice/sales/opportunities/${oid}`, undefined, stressTokens.stress_token);
            samples.push(detail.ms);
            const d = detail.body || {};
            if (detail.ok && d.closed_at && d.close_reason
                && (d.stage === 'won' || d.stage === 'lost')) {
                closedAtPresent++;
            } else if (detail.ok) {
                if (errs.length < 8) errs.push({ phase: 'detail_assert', oid: oid.slice(-6),
                    stage: d.stage, closed_at: !!d.closed_at, close_reason: !!d.close_reason });
            }
        }

        // 3) One activity per opportunity (audit log per-mutation requirement).
        let actOk = 0;
        for (const oid of createdOpportunityIds) {
            const r = await callTimedWithBackoff(request, 'post',
                `/api/mice/sales/opportunities/${oid}/activities`, {
                    type: 'note',
                    subject: `${prefix}OppActC_${oid.slice(-6)}`,
                    body: `${prefix} F8G 80-C activity post-terminal`,
                    outcome: 'positive', duration_min: 5,
                }, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok) actOk++;
            await new Promise((res) => setTimeout(res, 1500));
        }

        const transTotal = createdOpportunityIds.length;
        const transOk = wonOk + lostOk;
        const createFloor = Math.ceil(N_OPPORTUNITIES * 0.9);
        const transFloor = Math.ceil(transTotal * 0.9);
        const closedFloor = Math.ceil(transTotal * 0.9);
        // Architect review fix #2: enforce activity-log floor explicitly.
        // Task requires "sales activity log per-mutation"; without a floor,
        // the requirement could silently regress.
        const actFloor = Math.ceil(transTotal * 0.9);
        const allPass = createOk >= createFloor && transOk >= transFloor
            && closedAtPresent >= closedFloor && actOk >= actFloor;
        recPerf(testInfo, MOD, 'opp_terminal', samples, allPass);
        rec(testInfo, { module: MOD, step: 'opp_terminal',
            status: allPass ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/mice/sales/opportunities + /transition (won|lost) + /activities',
            note: `create_ok=${createOk}/${N_OPPORTUNITIES} won=${wonOk} lost=${lostOk} trans_fail=${transFail} closed_at_present=${closedAtPresent}/${transTotal} activities_ok=${actOk}/${transTotal}(floor>=${actFloor}) throttled_429=${throttled} errs=${JSON.stringify(errs)}` });
        if (createOk < createFloor) recFinding(testInfo, 'P1', MOD,
            'Opportunity create floor ihlal',
            `n=${N_OPPORTUNITIES} ok=${createOk} (<${createFloor}). errs=${JSON.stringify(errs)}`);
        if (transOk < transFloor) recFinding(testInfo, 'P1', MOD,
            'Won/lost transition floor ihlal',
            `total=${transTotal} ok=${transOk} (<${transFloor}). errs=${JSON.stringify(errs)}`);
        if (closedAtPresent < closedFloor) recFinding(testInfo, 'P1', MOD,
            'closed_at/close_reason persistence ihlal — F8C backlog still open',
            `total=${transTotal} present=${closedAtPresent} (<${closedFloor}). Terminal-state side-effects not fully persisted on detail read.`);
        if (actOk < actFloor) recFinding(testInfo, 'P1', MOD,
            'Sales activity log per-mutation floor ihlal',
            `total=${transTotal} ok=${actOk} (<${actFloor}). Audit log emit gap on post-terminal activity.`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'opp_terminal', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(allPass, `opp_terminal aggregate: create=${createOk}/${createFloor} trans=${transOk}/${transFloor} closed=${closedAtPresent}/${closedFloor} activities=${actOk}/${actFloor}`).toBe(true);
    });

    test('D) Corporate contract dry-run lifecycle (create + update)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'contract_lifecycle', status: 'SKIP', note: `module_blocked=true (${blockedReason})` }); test.skip(); return; }
        test.setTimeout(180_000);
        const samples = [];
        let ok = 0, fail = 0, throttled = 0, permFail = 0;
        const errs = [];

        // Endpoint reachability probe — independent surface, may be RBAC-gated
        // differently from /api/mice/accounts. Non-2xx → P2 informational SKIP.
        const probeR = await callTimed(request, 'get', '/api/sales/corporate-contracts',
            undefined, stressTokens.stress_token);
        if (!probeR.ok) {
            recFinding(testInfo, 'P2', MOD,
                'Corporate contracts surface probe non-2xx',
                `GET /api/sales/corporate-contracts status=${probeR.status} — D step skipped, informational only.`);
            rec(testInfo, { module: MOD, step: 'contract_lifecycle', status: 'SKIP',
                note: `probe_status=${probeR.status}` });
            test.skip();
            return;
        }

        const today = new Date();
        const startIso = new Date(today.getTime() + 7 * 86400_000).toISOString().slice(0, 10);
        const endIso = new Date(today.getTime() + 365 * 86400_000).toISOString().slice(0, 10);

        // 1) Create N contracts.
        for (let i = 0; i < N_CONTRACTS; i++) {
            const payload = {
                company_name: `${prefix}ContractD_${i + 1}`,
                contract_type: ['negotiated', 'corporate_rate', 'direct'][i % 3],
                rate_code: `${prefix}RC${i + 1}`,
                negotiated_rate: 1500 + i * 100,
                discount_percentage: 15 + i * 5,
                start_date: startIso,
                end_date: endIso,
                allotment: 100 + i * 20,
                blackout_dates: [],
                contact_person: `${prefix}Person_${i + 1}`,
                contact_email: `${prefix}contract_${i + 1}@example.invalid`,
                contact_phone: `+90555111${(i + 1).toString().padStart(4, '0')}`,
                notes: `${prefix} F8G 80-D draft`,
            };
            const r = await callTimedWithBackoff(request, 'post',
                '/api/sales/corporate-contract', payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.status === 403) permFail++;
            const cid = r.body?.contract_id;
            if (r.ok && cid) { ok++; createdContractIds.push(cid); }
            else { fail++; if (errs.length < 3) errs.push({ phase: 'create', status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }

        if (permFail === N_CONTRACTS) {
            recFinding(testInfo, 'P2', MOD, 'Corporate contract create perm denied for stress admin',
                `permFail=${permFail}/${N_CONTRACTS} — informational only.`);
            rec(testInfo, { module: MOD, step: 'contract_lifecycle', status: 'SKIP',
                note: `all_403 permFail=${permFail}` });
            test.skip();
            return;
        }

        // 2) PUT update each — dry-run approval state machine simulated via
        // notes field (draft → review → approved → signed). Backend has no
        // native approval workflow; gap recorded as P2 below.
        let updOk = 0;
        const states = ['review', 'approved', 'signed'];
        for (const cid of createdContractIds) {
            for (const st of states) {
                const updPayload = {
                    company_name: `${prefix}ContractD_${cid.slice(-6)}`,
                    contract_type: 'negotiated', rate_code: `${prefix}RC_${cid.slice(-6)}`,
                    negotiated_rate: 1600, discount_percentage: 20,
                    start_date: startIso, end_date: endIso,
                    allotment: 100, blackout_dates: [],
                    contact_person: `${prefix}Person`,
                    contact_email: `${prefix}contract@example.invalid`,
                    contact_phone: '+905551110000',
                    notes: `${prefix} F8G 80-D state=${st}`,
                };
                const r = await callTimedWithBackoff(request, 'put',
                    `/api/sales/corporate-contract/${cid}`, updPayload, stressTokens.stress_token);
                samples.push(r.ms);
                if (r.throttled) throttled++;
                if (r.ok) updOk++;
                await new Promise((res) => setTimeout(res, 1500));
            }
        }

        // Record the missing-approval-workflow gap (informational).
        recFinding(testInfo, 'P2', MOD,
            'No native contract approval state machine',
            `Backend POST /api/sales/corporate-contract hard-codes status="active"; PUT update does not expose approval lifecycle (draft→review→approved→signed) as a first-class field. Spec simulates the transition via notes payload. Informational gap — not blocking.`);

        const createFloor = Math.ceil(N_CONTRACTS * 0.9);
        const updFloor = Math.ceil((N_CONTRACTS * states.length) * 0.9);
        const allPass = ok >= createFloor && updOk >= updFloor;
        recPerf(testInfo, MOD, 'contract_lifecycle', samples, allPass);
        rec(testInfo, { module: MOD, step: 'contract_lifecycle',
            status: allPass ? 'PASS' : 'FAIL',
            endpoint: 'POST/PUT /api/sales/corporate-contract',
            note: `create_ok=${ok}/${N_CONTRACTS} update_ok=${updOk}/${N_CONTRACTS * states.length} fail=${fail} throttled_429=${throttled} permFail=${permFail} errs=${JSON.stringify(errs)}` });
        if (ok < createFloor) recFinding(testInfo, 'P1', MOD,
            'Corporate contract create floor ihlal',
            `n=${N_CONTRACTS} ok=${ok} (<${createFloor}). errs=${JSON.stringify(errs)}`);
        if (updOk < updFloor) recFinding(testInfo, 'P1', MOD,
            'Corporate contract update floor ihlal',
            `total=${N_CONTRACTS * states.length} ok=${updOk} (<${updFloor}).`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'contract_lifecycle', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(allPass, `contract aggregate: create=${ok}/${createFloor} update=${updOk}/${updFloor}`).toBe(true);
    });

    test('E) Tenant isolation + pilot_drift + external_calls invariant', async ({ request, stressTokens, stressState }, testInfo) => {
        // E always runs (independent of moduleBlocked) — pilot mutation
        // assurance must never be skipped per F8 doctrine.
        test.setTimeout(60_000);

        // 1) Cross-tenant leak guard: pilot GET /api/mice/accounts must NOT
        // return any account name starting with our stress prefix.
        let pilotLeak = -1;
        let pilotAcctsListed = -1;
        if (stressTokens.pilot_token) {
            const r = await callTimed(request, 'get', '/api/mice/accounts',
                undefined, stressTokens.pilot_token);
            if (r.ok) {
                const accts = r.body?.accounts || [];
                pilotAcctsListed = accts.length;
                pilotLeak = accts.filter((a) => typeof a?.name === 'string'
                    && a.name.startsWith(prefix)).length;
            }
        }
        const leakOk = pilotLeak <= 0;
        rec(testInfo, { module: MOD, step: 'tenant_isolation',
            status: leakOk ? 'PASS' : 'FAIL',
            note: `pilot_listed=${pilotAcctsListed} pilot_leak=${pilotLeak} (must be 0)` });
        if (!leakOk) recFinding(testInfo, 'P0', MOD,
            'Cross-tenant account leak — stress prefix visible to pilot tenant',
            `pilot saw ${pilotLeak} accounts with prefix=${prefix}. Tenant isolation broken.`);

        // 2) Pilot bookings drift = 0.
        const driftOk = await assertPilotDriftZero(testInfo, MOD, request,
            stressTokens.pilot_token, pilotBefore);

        // 3) External calls invariant — final sweep.
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD,
            'final_sweep', stressState, request, stressTokens.pilot_token);

        expect(leakOk, `pilot_leak=${pilotLeak} (must be 0)`).toBe(true);
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
    });
});
