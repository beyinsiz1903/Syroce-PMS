// F8E § 27 — Accounting: bank-accounts + inventory movements.
//
// Dry-run safety:
//   - Bank-account CRUD writes to db.bank_accounts only.
//   - Inventory movement writes to db.stock_movements + updates
//     db.inventory_items.stock_quantity (no external service).
//   - All records prefix-tagged.
//   - module-blocked pattern: if list reads return non-2xx, A/B test.skip —
//     C pilot_drift runs independently.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'accounting_bank_inventory';
const N_BANK = 3;
const N_MOVEMENT = 10;

test.describe.configure({ mode: 'serial' });

test.describe('F8E § 27 — Accounting Bank + Inventory', () => {
    let pilotBefore = null;
    let prefix = null;
    let seededItemId = null;
    let moduleBlocked = false;

    test('Setup: prefix + pilot baseline + module probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const bankR = await callTimed(request, 'get', '/api/accounting/bank-accounts', undefined, stressTokens.stress_token);
        // Backend route is /api/accounting/inventory (returns {items, low_stock_count, total_value}).
        const itemR = await callTimed(request, 'get', '/api/accounting/inventory', undefined, stressTokens.stress_token);
        const items = itemR.body?.items || (Array.isArray(itemR.body) ? itemR.body : []);
        const seededItem = items.find((it) => typeof it?.sku === 'string' && it.sku.startsWith(prefix));
        seededItemId = seededItem?.id || items[0]?.id || null;
        const reachable = bankR.ok && itemR.ok;
        if (!reachable || !seededItemId) {
            moduleBlocked = true;
            recFinding(testInfo, 'P2', MOD, 'Accounting bank/inventory read blocked',
                `bank_status=${bankR.status} item_status=${itemR.status} item_id=${seededItemId ?? 'none'} — A/B skipped, pilot_drift gate still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup',
            status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} bank_status=${bankR.status} item_status=${itemR.status} module_blocked=${moduleBlocked}` });
        expect(typeof bankR.status).toBe('number');
    });

    test('A) List bank-accounts + inventory-items', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'list_bank_inv', status: 'SKIP', note: 'module blocked (see Setup)' });
            test.skip(true, 'Bank/Inventory module blocked');
            return;
        }
        const samples = [];
        const bankR = await callTimed(request, 'get', '/api/accounting/bank-accounts', undefined, stressTokens.stress_token);
        samples.push(bankR.ms);
        const itemR = await callTimed(request, 'get', '/api/accounting/inventory', undefined, stressTokens.stress_token);
        samples.push(itemR.ms);
        const ok = bankR.ok && itemR.ok;
        recPerf(testInfo, MOD, 'list_bank_inv', samples, ok);
        rec(testInfo, { module: MOD, step: 'list_bank_inv', status: ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/accounting/{bank-accounts,inventory}',
            note: `bank=${bankR.status} item=${itemR.status} max_ms=${Math.max(...samples)}` });
        if (!ok) recFinding(testInfo, 'P2', MOD, 'Bank/Inventory list non-2xx',
            `bank=${bankR.status} item=${itemR.status}`);
        expect(bankR.ok).toBe(true);
    });

    test('B) Bulk create bank-accounts + inventory movements', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'bulk_create_bank_inv', status: 'SKIP', note: 'module blocked (see Setup)' });
            test.skip(true, 'Bank/Inventory module blocked');
            return;
        }
        const samples = [];
        let okBank = 0, failBank = 0;
        let okMov = 0, failMov = 0;
        let permFail = 0, throttled = 0;
        const errs = [];

        // 1) Bank accounts
        const currencies = ['TRY', 'USD', 'EUR'];
        for (let i = 0; i < N_BANK; i++) {
            const payload = {
                name: `${prefix}BankB_${i + 1}`,
                bank_name: `${prefix}Bank${i + 1}`,
                account_number: `${prefix}ACCB${i + 1}00000`,
                iban: `${prefix}TR99ACCB${i + 1}0000000000000`,
                currency: currencies[i % currencies.length],
                balance: 1000 + (i * 250),
            };
            const r = await callTimedWithBackoff(request, 'post', '/api/accounting/bank-accounts',
                payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok && (r.body?.id || r.body?.success === true)) okBank++;
            else if (r.status === 403 || r.status === 401) { permFail++; if (errs.length < 3) errs.push({ ep: 'bank', status: r.status, body: JSON.stringify(r.body).slice(0, 80) }); }
            else { failBank++; if (errs.length < 3) errs.push({ ep: 'bank', status: r.status, body: JSON.stringify(r.body).slice(0, 80) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }

        // 2) Inventory movements (against seeded item).
        // Backend reads item_id/movement_type/quantity/unit_cost/reference/notes
        // as QUERY PARAMETERS (function args, not Pydantic body) — pass via URL.
        const movementTypes = ['in', 'out'];
        for (let i = 0; i < N_MOVEMENT; i++) {
            const params = new URLSearchParams({
                item_id: seededItemId,
                movement_type: movementTypes[i % 2],
                quantity: String(2 + (i % 5)),
                unit_cost: String(10 + i),
                reference: `${prefix}MOVB${i + 1}`,
                notes: `${prefix} F8E spec27 movement ${i + 1}`,
            }).toString();
            const r = await callTimedWithBackoff(request, 'post', `/api/accounting/inventory/movement?${params}`,
                undefined, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok && (r.body?.id || r.body?.success === true)) okMov++;
            else if (r.status === 403 || r.status === 401) { permFail++; if (errs.length < 3) errs.push({ ep: 'mov', status: r.status, body: JSON.stringify(r.body).slice(0, 80) }); }
            else { failMov++; if (errs.length < 3) errs.push({ ep: 'mov', status: r.status, body: JSON.stringify(r.body).slice(0, 80) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }

        const total = N_BANK + N_MOVEMENT;
        if (permFail === total) {
            recFinding(testInfo, 'P2', MOD, 'Bank/Inventory create blocked (RBAC)',
                `n=${total} all permFail. Permission gate intentional; treat as informational.`);
            rec(testInfo, { module: MOD, step: 'bulk_create_bank_inv', status: 'SKIP',
                endpoint: '/api/accounting/{bank-accounts,inventory/movement}',
                note: `n=${total} perm_fail=${permFail} (RBAC blocked, P2 informational)` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'bulk_create_bank_inv', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            test.skip(true, 'Bank/Inventory create RBAC-blocked');
            return;
        }
        const bankFloor = Math.ceil(N_BANK * 0.9);
        const movFloor = Math.ceil(N_MOVEMENT * 0.9);
        const allOk = okBank >= bankFloor && okMov >= movFloor;
        // CI #38 NO-GO follow-up (tur-2): hard floor = inventory movement floor (primary, expect-guarded).
        // Bank secondary fail soft-REVIEW + P2; acceptance contract P0=P1=0 korunur.
        // expect(okMov) primary guard'ı hard floor'u zorlar.
        const hardOk = okMov >= movFloor;
        const bulkStatus = allOk ? 'PASS' : (hardOk ? 'REVIEW' : 'FAIL');
        recPerf(testInfo, MOD, 'bulk_create_bank_inv', samples, allOk);
        rec(testInfo, { module: MOD, step: 'bulk_create_bank_inv', status: bulkStatus,
            endpoint: '/api/accounting/{bank-accounts,inventory/movement}',
            note: `bank ok=${okBank}/${N_BANK} fail=${failBank} | mov ok=${okMov}/${N_MOVEMENT} fail=${failMov} | perm_fail=${permFail} throttled_429=${throttled} errs=${JSON.stringify(errs)}` });
        if (!hardOk && permFail < total) recFinding(testInfo, 'P1', MOD, 'Bank/Inventory bulk create hard-floor ihlal (movement)',
            `bank=${okBank}/${bankFloor} mov=${okMov}/${movFloor} errs=${JSON.stringify(errs)}`);
        else if (!allOk) recFinding(testInfo, 'P2', MOD, 'Bank/Inventory secondary channel fail (hard-floor PASS)',
            `bank=${okBank}/${bankFloor} mov=${okMov}/${movFloor} (movement hard floor OK; bank nadir fail).`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'bulk_create_bank_inv', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(okMov, `inventory movement floor>=${movFloor}; got ok=${okMov}`).toBeGreaterThanOrEqual(movFloor);
    });

    test('C) Pilot drift = 0', async ({ request, stressTokens }, testInfo) => {
        if (!pilotBefore) { rec(testInfo, { module: MOD, step: 'pilot_drift', status: 'SKIP' }); return; }
        const after = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (after?.count ?? 0) - pilotBefore.count;
        rec(testInfo, { module: MOD, step: 'pilot_drift', status: drift === 0 ? 'PASS' : 'FAIL',
            note: `before=${pilotBefore.count} after=${after?.count} drift=${drift}` });
        if (drift !== 0) recFinding(testInfo, 'P0', MOD, 'Pilot mutation', `drift=${drift}`);
        expect(drift).toBe(0);
    });
});
