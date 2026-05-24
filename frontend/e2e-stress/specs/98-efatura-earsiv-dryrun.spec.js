// F8X § 98 — E-fatura / E-arşiv dry-run + forbidden external call probe.
//
// Threat-model surface (threat_model.md § Tampering + Information Disclosure):
//   Türkiye pazarında PMS → fatura tarafı KRİTİK. Gerçek GİB/e-fatura/e-arşiv
//   provider çağrısı testte ASLA yapılmamalı. Bu spec invoice yüzeyini
//   read-only + schema-validation + tenant-isolation + external-call gate ile
//   doğrular.
//
// Architect fix notes (2026-05-24 NO-GO → revised):
//   - Backend `InvoiceCreate` şeması VKN/TCKN field'ı surface ETMİYOR; bu
//     yüzden invalid-VKN/TCKN payload testi YANLIŞTI (gerçek bir validation
//     katmanı yok; tüm sample'lar 422 ile düşse de bu schema-required-field
//     hatasıdır, VKN format guard değil). VKN/TCKN gap'i P2 REVIEW olarak
//     kayda alınır — informational, fake PASS değil.
//   - Backend `db.invoices` koleksiyonu STRESS_COLLECTIONS sweep'inde yok
//     (yalnız `accounting_invoices` var). Bu yüzden valid POST asla yapılmaz;
//     sadece eksik payload → 422 PASS testi yürütülür.
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
//   - VKN/TCKN gap: P2 REVIEW (schema'da field yok).
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

            // C. VKN/TCKN field surface gap → P2 informational (NOT fake PASS).
            recFinding(testInfo, 'P2', MOD,
                'InvoiceCreate schema lacks VKN/TCKN customer identity fields',
                'Backend `InvoiceCreate` (`backend/models/schemas/invoicing.py`) yalnız customer_name + customer_email saklıyor; Türkiye e-fatura/e-arşiv UBL pratiğinde VKN (kurumsal) ve TCKN (bireysel) zorunlu. Schema genişletilmesi roadmap backlog: F8X v2.');

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
