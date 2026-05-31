// F8X § 98 — E-fatura / E-arşiv dry-run + forbidden external call probe.
//
// Threat-model surface (threat_model.md § Tampering + Information Disclosure):
//   Türkiye pazarında PMS → fatura tarafı KRİTİK. Gerçek GİB/e-fatura/e-arşiv
//   provider çağrısı testte ASLA yapılmamalı. Bu spec invoice yüzeyini
//   read-only + schema-validation + tenant-isolation + external-call gate ile
//   doğrular.
//
// Schema parity (e-Fatura VKN/TCKN):
//   - Backend `InvoiceCreate` (`backend/models/schemas/invoicing.py`) artık
//     `customer_tax_id` alanını VKN (10 hane) / TCKN (11 hane) olarak validate
//     ediyor; bu yüzden VKN/TCKN gap'i artık P2 REVIEW DEĞİL — geçerli/geçersiz
//     vergi no senaryoları 422 yüzeyinde HARD-ASSERT edilir (section C).
//   - Backend `db.invoices` koleksiyonu STRESS_COLLECTIONS sweep'inde yok
//     (yalnız `accounting_invoices` var). Bu yüzden valid POST asla yapılmaz;
//     VKN/TCKN parity testleri her senaryoda 422'ye düşecek payload kullanır
//     (geçersiz tax_id, ya da geçerli tax_id + kasıtlı eksik zorunlu alan) →
//     db.invoices write = 0 invariant'ı korunur.
//
// Mutlak kurallar:
//   - pilot mutation = 0 (yalnız read snapshot)
//   - external_calls = [] (GİB/Logo/Netsis çağrısı yok)
//   - failedTests = 0, P0 = P1 = 0
//   - db.invoices write = 0 (cleanup blind spot guard)
//
// Doctrine:
//   - Read-only invoice list + stats probe (stress tenant).
//   - Schema enforcement probe: minimal eksik payload → 422 PASS, 2xx = P1
//     (zorunlu alanlar boş kabul ediliyor).
//   - VKN/TCKN parity: hard-assert. Geçersiz customer_tax_id → 422 + hata
//     loc'unda customer_tax_id; geçerli VKN(10)/TCKN(11) → 422 (kasıtlı eksik
//     due_date) ama customer_tax_id flag YOK. db.invoices write = 0 korunur.
//   - Cross-tenant invoice PUT IDOR (stress_token + pilot harvest ID) →
//     403/404 hard-fail, 2xx = P0.
//   - ERP sync endpoint'leri (`/finance/logo-integration/sync`,
//     `/finance/netsis-integration/sync`) → post-batch external_calls=[]
//     hard guard (mock connector olsa bile invariant tetiklenir).
//   - Final invariants try/finally ile her path'te garanti.
//
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, fetchSingle,
} from '../fixtures/stress-helpers.js';

const MOD = 'efatura_earsiv_dryrun';

test.describe.serial('F8X efatura/earsiv dryrun', () => {
    test('read-only invoice surface + schema enforcement', async ({ request, stressTokens }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        rec(testInfo, { module: MOD, step: 'pilot_baseline', status: 'INFO', note: `count=${pilotBefore?.count}` });

        try {
            // A. Read-only probes.
            for (const s of [
                { name: 'invoice_list', path: '/api/invoices?limit=5' },
                { name: 'invoice_stats', path: '/api/invoices/stats' },
            ]) {
                const probe = await withModuleProbe(request, sToken, s.path);
                if (probe.moduleBlocked) {
                    rec(testInfo, { module: MOD, step: `${s.name}_probe`, status: 'SKIP',
                        note: `module_blocked:${probe.reason} http=${probe.status}` });
                    recFinding(testInfo, 'P2', MOD, `Invoice ${s.name} surface module-blocked`,
                        `GET ${s.path} http=${probe.status} reason=${probe.reason}.`);
                } else {
                    rec(testInfo, { module: MOD, step: `${s.name}_probe`, status: 'PASS',
                        note: `http=${probe.status}` });
                }
            }

            // B. Schema enforcement probe — eksik zorunlu alanlar (customer_name,
            // customer_email, items, subtotal, tax, total, due_date) → 422 zorunlu.
            // Bu payload BACKEND'E asla başarıyla yazılmaz (alanlar eksik); db.invoices
            // write guard'ı.
            const schemaProbe = await callTimed(request, 'post', '/api/invoices',
                { invoice_number: `__SCHEMA_PROBE_${Date.now()}__`, total: 0 }, sToken);
            if (schemaProbe.status === 403 || schemaProbe.status === 404) {
                rec(testInfo, { module: MOD, step: 'invoice_schema_enforcement', status: 'SKIP',
                    note: `module_blocked http=${schemaProbe.status}` });
                recFinding(testInfo, 'P2', MOD, 'Invoice create surface module-blocked',
                    `POST /api/invoices http=${schemaProbe.status}; schema enforcement cannot be exercised.`);
            } else if (schemaProbe.status === 422 || schemaProbe.status === 400) {
                rec(testInfo, { module: MOD, step: 'invoice_schema_enforcement', status: 'PASS',
                    note: `http=${schemaProbe.status} (required fields enforced)` });
            } else if (schemaProbe.status >= 200 && schemaProbe.status < 300) {
                recFinding(testInfo, 'P1', MOD, 'InvoiceCreate accepts payload missing required fields',
                    `POST /api/invoices missing customer_email/items/subtotal/tax/total/due_date → http=${schemaProbe.status}. Schema enforcement broken. Yazılan invoice id: ${JSON.stringify(schemaProbe.body).slice(0, 200)}`);
            } else {
                rec(testInfo, { module: MOD, step: 'invoice_schema_enforcement', status: 'REVIEW',
                    note: `http=${schemaProbe.status} (unexpected; backend may be unreachable)` });
            }

            // C. VKN/TCKN schema parity — HARD-ASSERT (e-Fatura VKN/TCKN şema
            // paritesi). `InvoiceCreate.customer_tax_id`
            // (backend/models/schemas/invoicing.py) artık VKN (10 hane) /
            // TCKN (11 hane) validate ediyor. Geçerli/geçersiz vergi no
            // senaryoları 422 yüzeyinde doğrulanır.
            //
            // db.invoices write = 0 invariant'ı korunur: hiçbir senaryoda tam-geçerli
            // payload gönderilmez.
            //   - Geçersiz tax_id → diğer tüm zorunlu alanlar geçerli, yalnız
            //     customer_tax_id 422'ye düşer → hata loc'unda customer_tax_id beklenir.
            //   - Geçerli tax_id → due_date KASITLI eksik → yine 422 (yazma YOK)
            //     ve customer_tax_id'nin hata listesinde OLMADIĞI doğrulanır
            //     (validator geçerli VKN/TCKN'i kabul ediyor).
            const taxBase = {
                booking_id: null,
                customer_name: '__E2E_STRESS_TAXID_PROBE__',
                customer_email: 'stress.taxid@example.invalid',
                items: [{ description: 'probe', quantity: 1, unit_price: 1, total: 1 }],
                subtotal: 1, tax: 0, total: 1,
            };
            const taxIdFlagged = (body) => Array.isArray(body?.detail)
                && body.detail.some((e) => Array.isArray(e?.loc) && e.loc.includes('customer_tax_id'));

            const invalidTaxIds = ['123', '123456789', '123456789012', '12345abc90', 'ABCDEFGHIJ'];
            const validTaxIds = ['1234567890', '12345678901']; // VKN(10) + TCKN(11)

            // Module-block guard via first invalid sample (otherwise valid payload
            // → only customer_tax_id can fail).
            const taxProbe = await callTimed(request, 'post', '/api/invoices',
                { ...taxBase, due_date: '2026-12-31', customer_tax_id: invalidTaxIds[0] }, sToken);
            if (taxProbe.status === 403 || taxProbe.status === 404) {
                rec(testInfo, { module: MOD, step: 'taxid_schema_parity', status: 'SKIP',
                    note: `module_blocked http=${taxProbe.status}` });
                recFinding(testInfo, 'P2', MOD, 'Invoice create surface module-blocked',
                    `POST /api/invoices http=${taxProbe.status}; VKN/TCKN parity cannot be exercised.`);
            } else {
                // C1. Geçersiz VKN/TCKN → 422 ve customer_tax_id hata loc'unda.
                for (const bad of invalidTaxIds) {
                    const r = bad === invalidTaxIds[0]
                        ? taxProbe
                        : await callTimed(request, 'post', '/api/invoices',
                            { ...taxBase, due_date: '2026-12-31', customer_tax_id: bad }, sToken);
                    if (r.status >= 200 && r.status < 300) {
                        recFinding(testInfo, 'P1', MOD, 'InvoiceCreate accepts invalid VKN/TCKN',
                            `POST /api/invoices customer_tax_id=${bad} → http=${r.status} (must be 422). Schema parity broken; a malformed Turkish tax identifier could persist.`);
                    } else if (r.status === 422 && !taxIdFlagged(r.body)) {
                        recFinding(testInfo, 'P1', MOD, 'InvoiceCreate 422 not attributed to VKN/TCKN',
                            `POST /api/invoices customer_tax_id=${bad} → 422 but customer_tax_id absent from error loc; rejection may be incidental, not a tax-id guard.`);
                    }
                    expect(r.status, `invalid customer_tax_id ${bad} must be 422`).toBe(422);
                    expect(taxIdFlagged(r.body), `422 for ${bad} must flag customer_tax_id`).toBe(true);
                    rec(testInfo, { module: MOD, step: 'taxid_invalid_rejected', status: 'PASS',
                        note: `customer_tax_id=${bad} → 422 (VKN/TCKN guard)` });
                }

                // C2. Geçerli VKN(10)/TCKN(11) → due_date kasıtlı eksik → 422 ama
                // customer_tax_id flag YOK (yazma YOK, validator kabul ediyor).
                for (const good of validTaxIds) {
                    const r = await callTimed(request, 'post', '/api/invoices',
                        { ...taxBase, customer_tax_id: good }, sToken); // due_date omitted on purpose
                    if (r.status >= 200 && r.status < 300) {
                        recFinding(testInfo, 'P1', MOD, 'InvoiceCreate persisted probe payload',
                            `POST /api/invoices customer_tax_id=${good} (due_date omitted) → http=${r.status}; expected 422 for missing field. db.invoices write guard breached.`);
                    } else if (r.status === 422 && taxIdFlagged(r.body)) {
                        recFinding(testInfo, 'P1', MOD, 'InvoiceCreate rejects valid VKN/TCKN',
                            `POST /api/invoices customer_tax_id=${good} → 422 flagging customer_tax_id; validator over-strict, rejects a legal Turkish identifier.`);
                    }
                    expect(r.status, `valid customer_tax_id ${good} payload (missing due_date) must be 422`).toBe(422);
                    expect(taxIdFlagged(r.body), `valid customer_tax_id ${good} must NOT be flagged`).toBe(false);
                    rec(testInfo, { module: MOD, step: 'taxid_valid_accepted', status: 'PASS',
                        note: `customer_tax_id=${good} accepted (only missing due_date flagged)` });
                }
            }

            // D. Cross-tenant invoice PUT IDOR.
            if (pToken) {
                const pilotInv = await fetchSingle(request, pToken, '/api/invoices?limit=5');
                const items = pilotInv?.raw?.invoices || pilotInv?.raw?.items || pilotInv?.list || [];
                const pilotInvId = items[0]?.id || items[0]?._id || null;
                if (pilotInvId) {
                    const r = await callTimed(request, 'put', `/api/invoices/${pilotInvId}`,
                        { status: 'sent' }, sToken);
                    if (r.status >= 200 && r.status < 300) {
                        recFinding(testInfo, 'P0', MOD, 'Cross-tenant invoice update IDOR',
                            `stress_token PUT /api/invoices/${pilotInvId} → ${r.status} (PILOT tenant invoice mutated). KESIN tenant breach.`);
                        expect(r.status, 'cross-tenant invoice update must be 403/404').toBeGreaterThanOrEqual(400);
                    } else {
                        rec(testInfo, { module: MOD, step: 'cross_tenant_invoice_put', status: 'PASS',
                            note: `http=${r.status} (4xx guard enforced)` });
                    }
                } else {
                    rec(testInfo, { module: MOD, step: 'cross_tenant_invoice_put', status: 'SKIP',
                        note: 'pilot invoice harvest empty' });
                }
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'invoice_readonly_schema_batch',
                stressTokens.seed_state ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('ERP integration sync — forbidden real provider HTTP', async ({ request, stressTokens }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);

        try {
            const surfaces = [
                { name: 'logo_sync', path: '/api/finance/logo-integration/sync' },
                { name: 'netsis_sync', path: '/api/finance/netsis-integration/sync' },
            ];
            for (const s of surfaces) {
                const r = await callTimed(request, 'post', s.path, { dry_run: true }, sToken);
                if (r.status === 403 || r.status === 404) {
                    rec(testInfo, { module: MOD, step: `erp_${s.name}_probe`, status: 'SKIP',
                        note: `module_blocked http=${r.status}` });
                    recFinding(testInfo, 'P2', MOD, `ERP ${s.name} surface module-blocked`,
                        `POST ${s.path} http=${r.status}; provider isolation cannot be exercised here.`);
                } else {
                    rec(testInfo, { module: MOD, step: `erp_${s.name}_probe`, status: 'PASS',
                        note: `http=${r.status}` });
                }
            }
        } finally {
            // ERP sync batch sonrası dispatcher delta=0 ZORUNLU. Gerçek GIB/Logo/Netsis
            // HTTP çağrısı tetiklenmiş olsaydı burada P0 verir.
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'erp_sync_batch',
                stressTokens.seed_state ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });
});
