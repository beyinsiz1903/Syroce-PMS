// F8E § 25 — Finance / City Ledger:
// city-ledger list + bulk create (corporate accounts with credit limits).
//
// Dry-run safety:
//   - No external service: city-ledger CRUD writes to db.city_ledger_accounts
//     / db.city_ledger_transactions only. No email/SMS/Iyzico.
//   - Split-payment + mobile record-payment NOT exercised in this spec —
//     they require a live folio_id + open cashier shift (covered by F8A § 04
//     folio-mass and F8E § 24 shift lifecycle respectively); we keep this
//     spec focused on standalone city-ledger account CRUD which has no
//     cross-spec dependency.
//   - module-blocked pattern: if list returns non-2xx, A/B test.skip —
//     C pilot_drift runs independently.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'finance_cityledger';
const N_CREATE = 5;

test.describe.configure({ mode: 'serial' });

test.describe('F8E § 25 — Finance City Ledger', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;

    test('Setup: prefix + pilot baseline + module probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const listR = await callTimed(request, 'get', '/api/cashiering/city-ledger', undefined, stressTokens.stress_token);
        if (!listR.ok) {
            moduleBlocked = true;
            recFinding(testInfo, 'P2', MOD, 'City-ledger list non-2xx',
                `status=${listR.status} body=${JSON.stringify(listR.body).slice(0, 120)} — A/B skipped, pilot_drift gate still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup',
            status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} list_status=${listR.status} module_blocked=${moduleBlocked}` });
        expect(typeof listR.status).toBe('number');
    });

    test('A) List city-ledger accounts', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'list_cityledger', status: 'SKIP', note: 'module blocked (see Setup)' });
            test.skip(true, 'City-ledger module blocked');
            return;
        }
        const samples = [];
        const r1 = await callTimed(request, 'get', '/api/cashiering/city-ledger', undefined, stressTokens.stress_token);
        samples.push(r1.ms);
        recPerf(testInfo, MOD, 'list_cityledger', samples, r1.ok);
        rec(testInfo, { module: MOD, step: 'list_cityledger', status: r1.ok ? 'PASS' : 'REVIEW',
            endpoint: 'GET /api/cashiering/city-ledger',
            note: `status=${r1.status} ms=${r1.ms}` });
        if (!r1.ok) recFinding(testInfo, 'P2', MOD, 'City-ledger list non-2xx', `status=${r1.status}`);
        expect(r1.ok).toBe(true);
    });

    test('B) Bulk create city-ledger accounts', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'bulk_create_cityledger', status: 'SKIP', note: 'module blocked (see Setup)' });
            test.skip(true, 'City-ledger module blocked');
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, throttled = 0, permFail = 0;
        const errs = [];
        for (let i = 0; i < N_CREATE; i++) {
            const payload = {
                account_name: `${prefix}CityLedgerB${i + 1}`,
                company_name: `${prefix}CompanyB ${i + 1}`,
                contact_person: `${prefix}ContactB ${i + 1}`,
                email: `${prefix.toLowerCase()}clb${i + 1}@e2e-stress.example.com`,
                phone: `+90555800${i + 1}000`,
                address: `${prefix} City Ledger spec25 addr ${i + 1}`,
                credit_limit: 5000 + (i * 1000),
                payment_terms: 30,
            };
            const r = await callTimedWithBackoff(request, 'post', '/api/cashiering/city-ledger',
                payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok && (r.body?.account_id || r.body?.id || r.body?.success === true)) {
                ok++;
            } else if (r.status === 403 || r.status === 401) {
                permFail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            } else {
                fail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            }
            await new Promise((res) => setTimeout(res, 1500));
        }
        if (permFail === N_CREATE) {
            recFinding(testInfo, 'P2', MOD, 'City-ledger create blocked (RBAC)',
                `n=${N_CREATE} all permFail. manage_city_ledger gate intentional; treat as informational.`);
            rec(testInfo, { module: MOD, step: 'bulk_create_cityledger', status: 'SKIP',
                endpoint: 'POST /api/cashiering/city-ledger',
                note: `n=${N_CREATE} perm_fail=${permFail} (RBAC blocked, P2 informational)` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'bulk_create_cityledger', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            test.skip(true, 'City-ledger create RBAC-blocked');
            return;
        }
        const floor = Math.ceil(N_CREATE * 0.9);
        recPerf(testInfo, MOD, 'bulk_create_cityledger', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'bulk_create_cityledger', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/cashiering/city-ledger',
            note: `n=${N_CREATE} ok=${ok} fail=${fail} perm_fail=${permFail} throttled_429=${throttled} floor>=${floor} errs=${JSON.stringify(errs)}` });
        if (ok < floor && permFail < N_CREATE) recFinding(testInfo, 'P1', MOD, 'City-ledger bulk create floor ihlal',
            `n=${N_CREATE} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'bulk_create_cityledger', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `bulk_create_cityledger floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('C) Read city-ledger account transactions (seeded account)', async ({ request, stressTokens }, testInfo) => {
        // F8E v2 tur-6 D-extension: read transactions for first seeded
        // city-ledger account via GET /cashiering/city-ledger/{id}/transactions.
        // No mutation — verifies the read endpoint + summary aggregation
        // (total_charges, total_payments, current_balance) shape. Seeded
        // accounts have no transactions yet (transactions are spec 24/folio
        // territory); empty transactions + zero summary is the expected
        // baseline. Permission gate: `view_city_ledger_transactions`.
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'cl_transactions_read', status: 'SKIP', note: 'module blocked (see Setup)' });
            test.skip(true, 'City-ledger module blocked');
            return;
        }
        const listR = await callTimed(request, 'get', '/api/cashiering/city-ledger',
            undefined, stressTokens.stress_token);
        const accounts = Array.isArray(listR.body) ? listR.body : (listR.body?.accounts || []);
        if (!listR.ok || accounts.length === 0) {
            rec(testInfo, { module: MOD, step: 'cl_transactions_read', status: 'SKIP',
                note: `no seeded account available list_status=${listR.status} accounts=${accounts.length}` });
            recFinding(testInfo, 'P2', MOD, 'cl_transactions_read no account',
                `cleanup race veya seed missing — informational.`);
            return;
        }
        const acct = accounts[0];
        const acctId = acct?.id || acct?._id || acct?.account_id;
        if (!acctId) {
            rec(testInfo, { module: MOD, step: 'cl_transactions_read', status: 'SKIP',
                note: 'account id field shape unknown — informational' });
            return;
        }
        const r = await callTimed(request, 'get',
            `/api/cashiering/city-ledger/${encodeURIComponent(acctId)}/transactions?limit=50`,
            undefined, stressTokens.stress_token);
        if (r.status === 401 || r.status === 403) {
            recFinding(testInfo, 'P2', MOD, 'cl_transactions_read RBAC short-circuit',
                `status=${r.status} (view_city_ledger_transactions gate intentional).`);
            rec(testInfo, { module: MOD, step: 'cl_transactions_read', status: 'SKIP',
                note: `status=${r.status} RBAC informational` });
            return;
        }
        const hasSummary = r.body?.summary && typeof r.body.summary.transaction_count === 'number';
        const ok = r.ok && hasSummary;
        rec(testInfo, { module: MOD, step: 'cl_transactions_read', status: ok ? 'PASS' : 'FAIL',
            endpoint: '/api/cashiering/city-ledger/{id}/transactions',
            note: `status=${r.status} account_id=${acctId} has_summary=${hasSummary} tx_count=${r.body?.summary?.transaction_count} ms=${r.ms}` });
        if (!ok) recFinding(testInfo, 'P1', MOD, 'cl_transactions_read hard floor ihlal',
            `status=${r.status} body=${JSON.stringify(r.body).slice(0, 120)}`);
        expect(r.ok, `cl-transactions status`).toBe(true);
        expect(hasSummary, `summary shape`).toBe(true);
    });

    test('D) Pilot drift = 0', async ({ request, stressTokens }, testInfo) => {
        if (!pilotBefore) { rec(testInfo, { module: MOD, step: 'pilot_drift', status: 'SKIP' }); return; }
        const after = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (after?.count ?? 0) - pilotBefore.count;
        rec(testInfo, { module: MOD, step: 'pilot_drift', status: drift === 0 ? 'PASS' : 'FAIL',
            note: `before=${pilotBefore.count} after=${after?.count} drift=${drift}` });
        if (drift !== 0) recFinding(testInfo, 'P0', MOD, 'Pilot mutation', `drift=${drift}`);
        expect(drift).toBe(0);
    });
});
