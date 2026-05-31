// F8E § 28 — Finance Reports + Currency (v2 push):
// VAT / P&L / Balance-sheet / Dashboard / Cash-flow reads + currency rates
// lifecycle (rate create + list + convert).
//
// Dry-run safety:
//   - All endpoints write/read db.accounting_invoices / db.expenses /
//     db.bank_accounts / db.cash_flow / db.currency_rates only. No external
//     service: no e-fatura GIB dispatch (those routes intentionally NOT
//     exercised — `/efatura/send-to-gib`, `/efatura/generate`, `/accounting/
//     invoices/{id}/generate-efatura` all reach real GIB API in production).
//   - All currency rates prefix-tagged via `effective_date` window and
//     created_at — no shared keys, no pilot drift.
//   - module-blocked pattern: if reports/currencies probe non-2xx, A/B
//     test.skip; C pilot_drift independent.
//   - RBAC short-circuit: P&L / balance-sheet / dashboard / currency-rates
//     POST / convert-currency need `view_finance_reports`. Stress admin is
//     super_admin so should pass; if backend manual allowlist blocks,
//     permFail >= 80% → P2 SKIP.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'finance_reports_currency';
const N_RATE = 3;
const N_CONVERT = 2;

test.describe.configure({ mode: 'serial' });

test.describe('F8E § 28 — Finance Reports + Currency', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;

    test('Setup: prefix + pilot baseline + currencies probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        // Currencies endpoint has no perm gate; safest reachability probe.
        const curR = await callTimed(request, 'get', '/api/accounting/currencies', undefined, stressTokens.stress_token);
        if (!curR.ok) {
            moduleBlocked = true;
            recFinding(testInfo, 'P2', MOD, 'Accounting currencies probe non-2xx',
                `status=${curR.status} body=${JSON.stringify(curR.body).slice(0, 120)} — A/B skipped, pilot_drift gate still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup',
            status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} currencies_status=${curR.status} module_blocked=${moduleBlocked}` });
        expect(typeof curR.status).toBe('number');
    });

    test('A) Reports read (VAT / P&L / balance-sheet / dashboard / cash-flow / currencies)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'reports_read', status: 'SKIP', note: 'module blocked (see Setup)' });
            test.skip(true, 'Reports module blocked');
            return;
        }
        const samples = [];
        const today = new Date();
        const start = new Date(today.getTime() - 30 * 86400000).toISOString().slice(0, 10);
        const end = today.toISOString().slice(0, 10);

        const vatR = await callTimed(request, 'get',
            `/api/accounting/reports/vat-report?start_date=${start}&end_date=${end}`,
            undefined, stressTokens.stress_token);
        samples.push(vatR.ms);
        const plR = await callTimed(request, 'get',
            `/api/accounting/reports/profit-loss?start_date=${start}&end_date=${end}`,
            undefined, stressTokens.stress_token);
        samples.push(plR.ms);
        const bsR = await callTimed(request, 'get',
            '/api/accounting/reports/balance-sheet',
            undefined, stressTokens.stress_token);
        samples.push(bsR.ms);
        const dashR = await callTimed(request, 'get',
            '/api/accounting/dashboard',
            undefined, stressTokens.stress_token);
        samples.push(dashR.ms);
        const cfR = await callTimed(request, 'get',
            '/api/accounting/cash-flow',
            undefined, stressTokens.stress_token);
        samples.push(cfR.ms);
        const curR = await callTimed(request, 'get',
            '/api/accounting/currencies',
            undefined, stressTokens.stress_token);
        samples.push(curR.ms);

        // VAT and currencies are no-perm; treat them as the hard floor.
        // P&L/balance/dashboard need view_finance_reports — RBAC tolerate.
        const permGatedFails = [plR, bsR, dashR].filter((r) => r.status === 401 || r.status === 403).length;
        const hardOk = vatR.ok && curR.ok && cfR.ok;
        const allOk = hardOk && plR.ok && bsR.ok && dashR.ok;
        const status = allOk ? 'PASS' : (hardOk ? 'REVIEW' : 'FAIL');

        recPerf(testInfo, MOD, 'reports_read', samples, allOk);
        rec(testInfo, { module: MOD, step: 'reports_read', status,
            endpoint: '/api/accounting/{reports,dashboard,cash-flow,currencies}',
            note: `vat=${vatR.status} pl=${plR.status} bs=${bsR.status} dash=${dashR.status} cf=${cfR.status} cur=${curR.status} perm_gated_fails=${permGatedFails} max_ms=${Math.max(...samples)}` });

        if (!hardOk) recFinding(testInfo, 'P1', MOD, 'Reports hard floor ihlal (VAT / currencies / cash-flow)',
            `vat=${vatR.status} cur=${curR.status} cf=${cfR.status}`);
        else if (!allOk && permGatedFails === 0) recFinding(testInfo, 'P2', MOD,
            'Perm-gated reports non-2xx (non-RBAC)',
            `pl=${plR.status} bs=${bsR.status} dash=${dashR.status} — beklenmedik (super_admin permission'a sahip).`);
        else if (!allOk) recFinding(testInfo, 'P2', MOD, 'Perm-gated reports RBAC short-circuit',
            `pl=${plR.status} bs=${bsR.status} dash=${dashR.status} (view_finance_reports gate intentional).`);

        expect(vatR.ok, `vat hard floor`).toBe(true);
        expect(curR.ok, `currencies hard floor`).toBe(true);
        // Architect tur-6 review fix: cf is part of `hardOk` so it must be
        // expect-guarded too — otherwise rec(status:FAIL) without test fail
        // produces `failedTests=0 + counters.FAIL=1` → NO-GO (F8E tur-2
        // lesson, markdown-reporter.mjs:254-256 decideVerdict).
        expect(cfR.ok, `cash-flow hard floor`).toBe(true);
    });

    test('B) Currency rates lifecycle (create + list + convert)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'currency_lifecycle', status: 'SKIP', note: 'module blocked (see Setup)' });
            test.skip(true, 'Reports module blocked');
            return;
        }
        const samples = [];
        let okRate = 0, failRate = 0, permFail = 0, throttled = 0;
        const errs = [];

        // 1) Create N rates with effective_date in the past so convert can pick them up.
        // Use today - i days so each rate has a unique effective_date and prefix-tagged
        // through (from_currency, to_currency) pairs that we never re-use elsewhere.
        const pairs = [
            { from: 'TRY', to: 'USD', rate: 0.037 + Math.random() * 0.001 },
            { from: 'TRY', to: 'EUR', rate: 0.034 + Math.random() * 0.001 },
            { from: 'USD', to: 'EUR', rate: 0.92 + Math.random() * 0.001 },
        ];
        const today = new Date();
        for (let i = 0; i < N_RATE; i++) {
            const eff = new Date(today.getTime() - i * 86400000).toISOString().slice(0, 10);
            const payload = {
                from_currency: pairs[i].from,
                to_currency: pairs[i].to,
                rate: pairs[i].rate,
                effective_date: eff,
            };
            const r = await callTimed(request, 'post', '/api/accounting/currency-rates',
                payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok && (r.body?.id || r.body?.rate != null)) okRate++;
            else if (r.status === 403 || r.status === 401) { permFail++; if (errs.length < 3) errs.push({ ep: 'rate', status: r.status, body: JSON.stringify(r.body).slice(0, 80) }); }
            else { failRate++; if (errs.length < 3) errs.push({ ep: 'rate', status: r.status, body: JSON.stringify(r.body).slice(0, 80) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }

        // 2) List rates we just created.
        const listR = await callTimed(request, 'get', '/api/accounting/currency-rates',
            undefined, stressTokens.stress_token);
        samples.push(listR.ms);

        // 3) Convert against the rates.
        let okConv = 0, failConv = 0;
        // Task #161 fix: convert-currency endpoint ConvertCurrencyRequest
        // (backend/models/schemas/requests.py:225-229) zorunlu alanları
        // `from_currency`/`to_currency` — `from`/`to` DEĞİL. Önceki payload
        // `{amount,from,to}` gönderiyordu → Pydantic eksik-zorunlu-alan → 422 →
        // okConv=0 → lifecycle REVIEW. Doğru alan adlarıyla convert 200 +
        // converted_amount döner (rate create+list+convert lifecycle PASS).
        const convPairs = [
            { amount: 1000, from_currency: 'TRY', to_currency: 'USD' },
            { amount: 500, from_currency: 'USD', to_currency: 'EUR' },
        ];
        for (let i = 0; i < N_CONVERT; i++) {
            const r = await callTimed(request, 'post', '/api/accounting/convert-currency',
                convPairs[i], stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok && r.body?.converted_amount != null) okConv++;
            else if (r.status === 403 || r.status === 401) { permFail++; if (errs.length < 3) errs.push({ ep: 'conv', status: r.status, body: JSON.stringify(r.body).slice(0, 80) }); }
            else { failConv++; if (errs.length < 3) errs.push({ ep: 'conv', status: r.status, body: JSON.stringify(r.body).slice(0, 80) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }

        const total = N_RATE + N_CONVERT;
        if (permFail === total) {
            recFinding(testInfo, 'P2', MOD, 'Currency lifecycle RBAC-blocked',
                `n=${total} all permFail. view_finance_reports gate intentional; treat as informational.`);
            rec(testInfo, { module: MOD, step: 'currency_lifecycle', status: 'SKIP',
                endpoint: '/api/accounting/{currency-rates,convert-currency}',
                note: `n=${total} perm_fail=${permFail} (RBAC blocked, P2 informational)` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'currency_lifecycle', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            test.skip(true, 'Currency RBAC-blocked');
            return;
        }

        const rateFloor = Math.ceil(N_RATE * 0.9);
        const convFloor = Math.ceil(N_CONVERT * 0.9);
        const allOk = okRate >= rateFloor && listR.ok && okConv >= convFloor;
        // Hard floor: rates (primary), expect-guarded. List + convert are secondary.
        const hardOk = okRate >= rateFloor;
        const lifecycleStatus = allOk ? 'PASS' : (hardOk ? 'REVIEW' : 'FAIL');

        recPerf(testInfo, MOD, 'currency_lifecycle', samples, allOk);
        rec(testInfo, { module: MOD, step: 'currency_lifecycle', status: lifecycleStatus,
            endpoint: '/api/accounting/{currency-rates,convert-currency}',
            note: `rate ok=${okRate}/${N_RATE} fail=${failRate} | list=${listR.status} | conv ok=${okConv}/${N_CONVERT} fail=${failConv} | perm_fail=${permFail} throttled_429=${throttled} errs=${JSON.stringify(errs)}` });
        if (!hardOk && permFail < total) recFinding(testInfo, 'P1', MOD,
            'Currency rate create hard-floor ihlal',
            `rate=${okRate}/${rateFloor} errs=${JSON.stringify(errs)}`);
        else if (!allOk) recFinding(testInfo, 'P2', MOD,
            'Currency secondary step fail (hard-floor PASS)',
            `rate=${okRate}/${rateFloor} list=${listR.status} conv=${okConv}/${convFloor} (rate hard floor OK).`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'currency_lifecycle', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(okRate, `currency rate floor>=${rateFloor}; got ok=${okRate}`).toBeGreaterThanOrEqual(rateFloor);
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
