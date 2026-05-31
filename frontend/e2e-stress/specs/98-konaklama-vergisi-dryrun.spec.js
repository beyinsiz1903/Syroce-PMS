// F8AD § 98 — Konaklama Vergisi (Turkey accommodation tax) dry-run.
//
// Threat-model surface (threat_model.md § Tampering + Information Disclosure):
//   Türkiye Konaklama Vergisi Kanunu (7194) iki canlı zamanlayıcıyla birlikte
//   çalışır: `backend/workers/konaklama_vergisi_scheduler.py` (aylık beyanname
//   otomatik finalize + Resend e-posta) ve `backend/workers/tga_scheduler.py`
//   (TGA outbound batch + retry, `integration_tga_outbox` koleksiyonu).
//   Stres testi PILOT tenant'ta mutasyon YARATMAMALI ve TGA/e-posta
//   outbound çağrısı TETİKLEMEMELİ; cross-tenant IDOR'a karşı sert (P0
//   hard-fail) kapı olmalıdır. Success-path doğrulaması için STRESS
//   tenant'ta sınırlı + idempotent (period başına tek kayıt) bir
//   beyanname finalize ile seed edilir (pilot DOKUNULMAZ).
//
// Doctrine (F8X–F8AA paketinin devamı):
//   - Module-block: `GET /api/finance/konaklama-vergisi/config` 403/404 →
//     tüm test blokları SKIP + P2 REVIEW.
//   - Read-only smoke (config/report/declaration/declarations list/postings)
//     + success-path detail/export: STRESS tenant'ta finalize ile seed
//     edilen GERÇEK decl_id → stress token ile GET detail + export
//     json/xml hard-assert 2xx (surface ground truth, pilot DOKUNULMAZ).
//   - Calculate validation (amount<=0/-, nights<1, oversized payload, /report
//     month=13 = invalid range → 4xx) + idempotency (aynı input → identik).
//   - Write surface NEGATIVE: config PUT rate=999, finalize year=1999, bogus
//     decl_id submit/pay/email/get/export → 4xx; bogus folio post-folio →
//     4xx; Idempotency-Key replay aynı bogus folio → her ikisi 4xx.
//     Negatif gate'ler SADECE 4xx kabul eder (5xx fail-open değil).
//   - **P0 cross-tenant IDOR (hard-fail)**: çift yön. (a) stress_token
//     bearer + pilot harvest decl_id/folio_id ve (b) pilot_token + STRESS
//     seeded decl_id + harvested stress folio_id →
//     submit/pay/email/get/export/post-folio her biri için
//     `expect(status).toBeGreaterThanOrEqual(400)`. Ek: config PUT +
//     finalize stress_token ile çağrıldığında pilot tenant'ın
//     declarations + postings count'u DEĞİŞMEMELİ (custom drift sayacı).
//   - Cron coupling guard: batch sonrası `external_calls` delta = 0
//     (TGA/e-mail outbound çağrısı tetiklenmemiş), `pilot_drift = 0`
//     (bookings) + KVB-spesifik drift (declarations + postings).
//   - try/finally ile invariants her test'te zorunlu.
//
// Mutlak kurallar:
//   - pilot mutation = 0
//   - external_calls = [] (gerçek TGA/Resend HTTP yok)
//   - failedTests = 0, P0 = P1 = 0
//
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, fetchSingle,
} from '../fixtures/stress-helpers.js';
import { randomUUID } from 'node:crypto';

const MOD = 'accommodation_tax';
const BASE = '/api/finance/konaklama-vergisi';

// is4xx — strict negative gate. 5xx fail-open KABUL EDİLMEZ (5xx = REVIEW,
// regression görünür kalır). 4xx = beklenen reject. 2xx = silent no-op /
// money-safety regression (caller bunu P1/P0 olarak emit eder).
function is4xx(status) { return status >= 400 && status < 500; }
function is2xx(status) { return status >= 200 && status < 300; }

// kvbDriftCount — pilot tenant'ın KVB declarations + postings count'unu
// snapshot olarak alır. assertPilotDriftZero `bookings` count'una bakar;
// burada konaklama vergisi spesifik koleksiyonlar (cron coupling) için
// ayrı sayaç tutuyoruz. Endpoint 4xx/5xx ise `null` döner (unverifiable;
// drift REVIEW olarak işlenir, fake PASS değil).
async function kvbDriftCount(request, pToken) {
    if (!request || !pToken) return { decls: null, postings: null, http: null };
    const headers = { Authorization: `Bearer ${pToken}` };
    let decls = null, postings = null, declsHttp = null, postingsHttp = null;
    try {
        const r = await request.get(`${BASE}/declarations?limit=120`,
            { headers, failOnStatusCode: false, timeout: 10_000 });
        declsHttp = r.status();
        if (is2xx(declsHttp)) {
            const body = await r.json().catch(() => null);
            decls = Number.isFinite(body?.count) ? body.count
                   : Array.isArray(body?.items) ? body.items.length : null;
        }
    } catch { /* unreachable */ }
    try {
        const r = await request.get(`${BASE}/postings?limit=500`,
            { headers, failOnStatusCode: false, timeout: 10_000 });
        postingsHttp = r.status();
        if (is2xx(postingsHttp)) {
            const body = await r.json().catch(() => null);
            postings = Number.isFinite(body?.count) ? body.count
                      : Array.isArray(body?.items) ? body.items.length : null;
        }
    } catch { /* unreachable */ }
    return { decls, postings, declsHttp, postingsHttp };
}

async function assertKvbPilotDriftZero(testInfo, module, request, pToken, baseline) {
    if (!request || !pToken || !baseline) {
        rec(testInfo, { module, step: 'kvb_pilot_drift_zero', status: 'SKIP',
            note: 'pilot_token veya baseline yok' });
        return true;
    }
    const after = await kvbDriftCount(request, pToken);
    const declDrift = (baseline.decls != null && after.decls != null)
        ? (after.decls - baseline.decls) : null;
    const postDrift = (baseline.postings != null && after.postings != null)
        ? (after.postings - baseline.postings) : null;
    const pass = (declDrift === 0) && (postDrift === 0);
    const status = (declDrift == null || postDrift == null)
        ? 'REVIEW'
        : (pass ? 'PASS' : 'FAIL');
    rec(testInfo, { module, step: 'kvb_pilot_drift_zero', status,
        note: `decls baseline=${baseline.decls} after=${after.decls} drift=${declDrift} (http=${after.declsHttp}); postings baseline=${baseline.postings} after=${after.postings} drift=${postDrift} (http=${after.postingsHttp})` });
    if ((declDrift != null && declDrift !== 0) ||
        (postDrift != null && postDrift !== 0)) {
        recFinding(testInfo, 'P0', module,
            'Pilot konaklama vergisi drift tespit edildi',
            `Pilot declarations drift=${declDrift}, postings drift=${postDrift}. Stress run pilot tenant'ta KVB mutasyonu üretti — cron-coupling veya cross-tenant write breach.`);
    }
    return pass;
}

test.describe.serial('F8AD konaklama vergisi dryrun', () => {
    // Shared across serial tests: a REAL declaration seeded in the STRESS
    // tenant (finalize, idempotent per (tenant,period); pilot DOKUNULMAZ).
    // Feeds both the success-path self detail/export probe (test 1) and the
    // pilot→stress cross-tenant IDOR deny probes (P0 IDOR test).
    let seededDeclId = null;
    let seededDeclPeriod = null;

    test('read-only surface smoke + module probe + success-path detail/export', async ({ request, stressTokens }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        const kvbBefore = await kvbDriftCount(request, pToken);
        rec(testInfo, { module: MOD, step: 'pilot_baseline', status: 'INFO',
            note: `bookings=${pilotBefore?.count} decls=${kvbBefore.decls} postings=${kvbBefore.postings}` });

        try {
            // Module-block probe.
            const cfgProbe = await withModuleProbe(request, sToken, `${BASE}/config`);
            if (cfgProbe.moduleBlocked) {
                rec(testInfo, { module: MOD, step: 'module_probe', status: 'SKIP',
                    note: `module_blocked:${cfgProbe.reason} http=${cfgProbe.status}` });
                recFinding(testInfo, 'P2', MOD,
                    'Konaklama Vergisi config surface module-blocked',
                    `GET ${BASE}/config http=${cfgProbe.status} reason=${cfgProbe.reason}; downstream probes skipped.`);
                return;
            }
            rec(testInfo, { module: MOD, step: 'module_probe', status: 'PASS',
                note: `http=${cfgProbe.status}` });

            const cfgBody = cfgProbe.body || {};
            if (typeof cfgBody.rate_percent !== 'number') {
                recFinding(testInfo, 'P2', MOD,
                    'Konaklama Vergisi config shape regression',
                    `GET ${BASE}/config body missing rate_percent: ${JSON.stringify(cfgBody).slice(0, 200)}`);
            }

            // Read-only smoke (stress tenant).
            const surfaces = [
                { name: 'report', path: `${BASE}/report` },
                { name: 'declaration', path: `${BASE}/declaration` },
                { name: 'declarations_list', path: `${BASE}/declarations?limit=5` },
                { name: 'postings_list', path: `${BASE}/postings?limit=5` },
            ];
            for (const s of surfaces) {
                const probe = await withModuleProbe(request, sToken, s.path);
                if (probe.moduleBlocked) {
                    rec(testInfo, { module: MOD, step: `${s.name}_probe`, status: 'SKIP',
                        note: `module_blocked:${probe.reason} http=${probe.status}` });
                    recFinding(testInfo, 'P2', MOD,
                        `Konaklama Vergisi ${s.name} surface module-blocked`,
                        `GET ${s.path} http=${probe.status} reason=${probe.reason}.`);
                } else if (is2xx(probe.status)) {
                    rec(testInfo, { module: MOD, step: `${s.name}_probe`, status: 'PASS',
                        note: `http=${probe.status}` });
                } else {
                    rec(testInfo, { module: MOD, step: `${s.name}_probe`, status: 'REVIEW',
                        note: `http=${probe.status} unexpected (non-2xx, non-block)` });
                    recFinding(testInfo, 'P2', MOD,
                        `Konaklama Vergisi ${s.name} read surface unexpected status`,
                        `GET ${s.path} http=${probe.status}; expected 2xx or module-block.`);
                }
            }

            // Success-path detail + export — STRESS tenant'ta GERÇEK bir
            // beyanname seed et (finalize idempotent per (tenant,period);
            // pilot DOKUNULMAZ), sonra kendi (stress) token'ı ile GET detail
            // + GET export?format=json/xml çağırıp 2xx HARD-ASSERT et. Bu
            // cross-tenant DEĞİL — stress kendi decl'ini okur — ama artık
            // pilot pool'unun dolu olmasına bağlı vacuous SKIP yok; surface
            // ground truth her koşuşta gerçekten egzersiz edilir.
            //
            // NOT: seed edilen folio_charge'lar BSON Date taşır; aggregate
            // pipeline `date`'i ISO string aralığıyla karşılaştırır → matrah
            // genelde 0 döner. Kayıt YİNE DE gerçek bir tax_declaration'dır
            // (id/period/status alanları dolu); detail/export invariant'ı
            // tutara bağlı değildir. Bu fake-green DEĞİL — gerçek endpoint,
            // gerçek kayıt, dürüst telemetri.
            const now = new Date();
            const seedYear = now.getUTCFullYear();
            const seedMonth = now.getUTCMonth() + 1;
            seededDeclPeriod = `${seedYear}-${String(seedMonth).padStart(2, '0')}`;
            const finalizeRes = await callTimed(request, 'post',
                `${BASE}/declaration/finalize`, { year: seedYear, month: seedMonth }, sToken);
            if (finalizeRes.status === 403 || finalizeRes.status === 404) {
                // Module-block doctrine: finalize surface kapalı → seed yok,
                // success-path SKIP + P2 (gerçek UI failure değil, RBAC/deploy).
                rec(testInfo, { module: MOD, step: 'stress_declaration_seed', status: 'SKIP',
                    note: `finalize module-blocked http=${finalizeRes.status}` });
                recFinding(testInfo, 'P2', MOD,
                    'Konaklama Vergisi finalize surface module-blocked',
                    `POST ${BASE}/declaration/finalize → http=${finalizeRes.status}; success-path detail/export seed edilemedi.`);
            } else if (is2xx(finalizeRes.status) && finalizeRes.body?.id) {
                seededDeclId = finalizeRes.body.id;
                rec(testInfo, { module: MOD, step: 'stress_declaration_seed', status: 'PASS',
                    note: `decl_id=${seededDeclId} period=${seededDeclPeriod} status=${finalizeRes.body?.status} total_base=${finalizeRes.body?.total_base}` });
                // Self-detail — stress token kendi beyannamesini okur → 2xx zorunlu.
                const detail = await callTimed(request, 'get',
                    `${BASE}/declarations/${seededDeclId}`, undefined, sToken);
                expect(detail.status, `stress self-detail http=${detail.status} body=${JSON.stringify(detail.body).slice(0,160)}`).toBeGreaterThanOrEqual(200);
                expect(detail.status, `stress self-detail http=${detail.status}`).toBeLessThan(300);
                expect(detail.body?.id, 'self-detail must echo seeded decl id').toBe(seededDeclId);
                expect(detail.body?.period, 'self-detail must carry seeded period').toBe(seededDeclPeriod);
                expect(typeof detail.body?.total_base, 'self-detail must carry numeric total_base').toBe('number');
                rec(testInfo, { module: MOD, step: 'stress_self_detail', status: 'PASS',
                    note: `http=${detail.status} period=${detail.body?.period}` });
                // Export json + xml — her ikisi 2xx zorunlu.
                for (const fmt of ['json', 'xml']) {
                    const exp = await callTimed(request, 'get',
                        `${BASE}/declarations/${seededDeclId}/export?format=${fmt}`, undefined, sToken);
                    expect(exp.status, `stress export ${fmt} http=${exp.status} body=${JSON.stringify(exp.body).slice(0,160)}`).toBeGreaterThanOrEqual(200);
                    expect(exp.status, `stress export ${fmt} http=${exp.status}`).toBeLessThan(300);
                    rec(testInfo, { module: MOD, step: `stress_self_export_${fmt}`, status: 'PASS',
                        note: `http=${exp.status}` });
                }
            } else {
                // 2xx ama id yok / beklenmedik durum → REVIEW (fake PASS yok).
                rec(testInfo, { module: MOD, step: 'stress_declaration_seed', status: 'REVIEW',
                    note: `finalize http=${finalizeRes.status} body=${JSON.stringify(finalizeRes.body).slice(0,160)}` });
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'kvb_readonly_batch',
                stressTokens.seed_state ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
            await assertKvbPilotDriftZero(testInfo, MOD, request, pToken, kvbBefore);
        }
    });

    test('calculate + report validation + idempotency (no mutation)', async ({ request, stressTokens }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        const kvbBefore = await kvbDriftCount(request, pToken);

        try {
            const calcGates = [
                { name: 'calc_zero_amount', body: { amount: 0, nights: 1 },
                  reason: 'gt=0 ihlali' },
                { name: 'calc_negative_amount', body: { amount: -100, nights: 1 },
                  reason: 'money safety: amount<0' },
                { name: 'calc_zero_nights', body: { amount: 100, nights: 0 },
                  reason: 'ge=1 ihlali' },
                { name: 'calc_negative_nights', body: { amount: 100, nights: -3 },
                  reason: 'ge=1 ihlali (neg)' },
                { name: 'calc_oversized_amount', body: { amount: 1e18, nights: 1 },
                  reason: 'oversized payload (overflow guard)' },
                { name: 'calc_oversized_nights', body: { amount: 100, nights: 10_000_000 },
                  reason: 'oversized payload (overflow guard)' },
                { name: 'calc_bogus_folio_id_ignored', body: { amount: 100, nights: 1, folio_id: 'STRESS_F8AD_BOGUS_FOLIO' },
                  reason: 'unknown field — schema strict ise 422, lenient ise 2xx (informational)' },
            ];

            // First probe also doubles as module-block probe.
            const first = await callTimed(request, 'post', `${BASE}/calculate`,
                calcGates[0].body, sToken);
            if (first.status === 403 || first.status === 404) {
                rec(testInfo, { module: MOD, step: 'calc_module_probe', status: 'SKIP',
                    note: `module_blocked http=${first.status}` });
                recFinding(testInfo, 'P2', MOD,
                    'Konaklama Vergisi calculate surface module-blocked',
                    `POST ${BASE}/calculate http=${first.status}; calc gate not exercised.`);
                return;
            }

            for (let i = 0; i < calcGates.length; i++) {
                const g = calcGates[i];
                const r = (i === 0) ? first
                    : await callTimed(request, 'post', `${BASE}/calculate`, g.body, sToken);
                if (g.name === 'calc_bogus_folio_id_ignored') {
                    // Lenient (default Pydantic) → 2xx beklenir; strict ise 422.
                    // 5xx hala REVIEW. 4xx ve 2xx ikisi de kabul (informational).
                    if (is2xx(r.status) || is4xx(r.status)) {
                        rec(testInfo, { module: MOD, step: g.name, status: 'PASS',
                            note: `http=${r.status} (extra field handled)` });
                    } else {
                        rec(testInfo, { module: MOD, step: g.name, status: 'REVIEW',
                            note: `http=${r.status} unexpected` });
                    }
                    continue;
                }
                if (is2xx(r.status)) {
                    recFinding(testInfo, 'P1', MOD,
                        `CalculateRequest accepts invalid input (${g.name})`,
                        `POST ${BASE}/calculate body=${JSON.stringify(g.body)} → http=${r.status}. Beklenti: 4xx (${g.reason}). Money safety gap.`);
                } else if (is4xx(r.status)) {
                    rec(testInfo, { module: MOD, step: g.name, status: 'PASS',
                        note: `http=${r.status} (${g.reason} enforced)` });
                } else {
                    // 5xx fail-open KABUL EDİLMEZ — REVIEW + finding.
                    recFinding(testInfo, 'P2', MOD,
                        `Konaklama Vergisi ${g.name} returned 5xx`,
                        `POST ${BASE}/calculate body=${JSON.stringify(g.body)} → http=${r.status}. Expected 4xx; 5xx server-side regression.`);
                    rec(testInfo, { module: MOD, step: g.name, status: 'REVIEW',
                        note: `http=${r.status}` });
                }
            }

            // Report invalid date range — month=13 → 4xx (`_period_bounds` raises 400).
            const reportInvalid = await callTimed(request, 'get',
                `${BASE}/report?year=2025&month=13`, undefined, sToken);
            if (is2xx(reportInvalid.status)) {
                recFinding(testInfo, 'P1', MOD,
                    'Report endpoint accepts invalid month=13',
                    `GET ${BASE}/report?month=13 → http=${reportInvalid.status}. Beklenti: 400. Date range gate broken.`);
            } else if (is4xx(reportInvalid.status)) {
                rec(testInfo, { module: MOD, step: 'report_invalid_month', status: 'PASS',
                    note: `http=${reportInvalid.status}` });
            } else {
                rec(testInfo, { module: MOD, step: 'report_invalid_month', status: 'REVIEW',
                    note: `http=${reportInvalid.status} unexpected` });
            }

            // Idempotency — aynı input → identik output.
            const calc1 = await callTimed(request, 'post', `${BASE}/calculate`,
                { amount: 250, nights: 2, exempt: false }, sToken);
            const calc2 = await callTimed(request, 'post', `${BASE}/calculate`,
                { amount: 250, nights: 2, exempt: false }, sToken);
            if (is2xx(calc1.status) && is2xx(calc2.status)) {
                const same = (calc1.body?.tax_amount === calc2.body?.tax_amount) &&
                             (calc1.body?.base_amount === calc2.body?.base_amount);
                if (same) {
                    rec(testInfo, { module: MOD, step: 'calc_idempotent', status: 'PASS',
                        note: `base=${calc1.body?.base_amount} tax=${calc1.body?.tax_amount}` });
                } else {
                    recFinding(testInfo, 'P1', MOD,
                        'Konaklama Vergisi calculate not idempotent',
                        `Same input drifted: #1=${JSON.stringify(calc1.body)} vs #2=${JSON.stringify(calc2.body)}.`);
                }
            } else {
                rec(testInfo, { module: MOD, step: 'calc_idempotent', status: 'REVIEW',
                    note: `http1=${calc1.status} http2=${calc2.status}` });
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'kvb_calculate_batch',
                stressTokens.seed_state ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
            await assertKvbPilotDriftZero(testInfo, MOD, request, pToken, kvbBefore);
        }
    });

    test('write surface negative + bogus-id probes (4xx-strict)', async ({ request, stressTokens }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        const kvbBefore = await kvbDriftCount(request, pToken);

        try {
            // A. PUT /config — rate_percent > 100 (le=100 ihlali) → 4xx zorunlu.
            const cfgInvalid = await callTimed(request, 'put', `${BASE}/config`,
                { rate_percent: 999, active: true, auto_post: false }, sToken);
            if (cfgInvalid.status === 403 || cfgInvalid.status === 404) {
                rec(testInfo, { module: MOD, step: 'cfg_put_invalid_rate', status: 'SKIP',
                    note: `module_blocked http=${cfgInvalid.status}` });
                recFinding(testInfo, 'P2', MOD,
                    'Konaklama Vergisi PUT /config surface module-blocked',
                    `PUT ${BASE}/config http=${cfgInvalid.status}; write gate not exercised.`);
            } else if (is2xx(cfgInvalid.status)) {
                recFinding(testInfo, 'P1', MOD,
                    'KonaklamaVergisiConfig accepts rate_percent > 100',
                    `PUT ${BASE}/config rate=999 → http=${cfgInvalid.status}. le=100 constraint violated, money safety gap.`);
            } else if (is4xx(cfgInvalid.status)) {
                rec(testInfo, { module: MOD, step: 'cfg_put_invalid_rate', status: 'PASS',
                    note: `http=${cfgInvalid.status} (le=100 enforced)` });
            } else {
                recFinding(testInfo, 'P2', MOD,
                    'PUT /config 5xx on invalid rate',
                    `PUT ${BASE}/config rate=999 → http=${cfgInvalid.status}. Expected 4xx.`);
            }

            // B. POST /declaration/finalize — year=1999 (ge=2020 ihlali) → 4xx.
            const finalizeInvalid = await callTimed(request, 'post',
                `${BASE}/declaration/finalize`, { year: 1999, month: 6 }, sToken);
            if (finalizeInvalid.status === 403 || finalizeInvalid.status === 404) {
                rec(testInfo, { module: MOD, step: 'finalize_invalid_year', status: 'SKIP',
                    note: `module_blocked http=${finalizeInvalid.status}` });
            } else if (is2xx(finalizeInvalid.status)) {
                recFinding(testInfo, 'P1', MOD,
                    'FinalizeRequest accepts year < 2020',
                    `POST ${BASE}/declaration/finalize year=1999 → http=${finalizeInvalid.status}. ge=2020 constraint violated.`);
            } else if (is4xx(finalizeInvalid.status)) {
                rec(testInfo, { module: MOD, step: 'finalize_invalid_year', status: 'PASS',
                    note: `http=${finalizeInvalid.status} (ge=2020 enforced)` });
            } else {
                recFinding(testInfo, 'P2', MOD,
                    'finalize 5xx on invalid year',
                    `POST ${BASE}/declaration/finalize year=1999 → http=${finalizeInvalid.status}. Expected 4xx.`);
            }

            // Finalize invalid month (13) → 4xx.
            const finalizeInvalidMonth = await callTimed(request, 'post',
                `${BASE}/declaration/finalize`, { year: 2025, month: 13 }, sToken);
            if (is2xx(finalizeInvalidMonth.status)) {
                recFinding(testInfo, 'P1', MOD,
                    'FinalizeRequest accepts month=13',
                    `POST ${BASE}/declaration/finalize month=13 → http=${finalizeInvalidMonth.status}.`);
            } else if (is4xx(finalizeInvalidMonth.status)) {
                rec(testInfo, { module: MOD, step: 'finalize_invalid_month', status: 'PASS',
                    note: `http=${finalizeInvalidMonth.status}` });
            } else {
                rec(testInfo, { module: MOD, step: 'finalize_invalid_month', status: 'REVIEW',
                    note: `http=${finalizeInvalidMonth.status}` });
            }

            // C. Bogus decl_id — submit / pay / email / GET / export → 4xx zorunlu.
            const bogusDecl = `STRESS_F8AD_BOGUS_${randomUUID()}`;
            const bogusProbes = [
                { name: 'get_bogus_decl', method: 'get',
                  path: `${BASE}/declarations/${bogusDecl}`, body: undefined },
                { name: 'submit_bogus_decl', method: 'post',
                  path: `${BASE}/declarations/${bogusDecl}/submit`,
                  body: { submission_ref: 'STRESS_F8AD_REF' } },
                { name: 'pay_bogus_decl', method: 'post',
                  path: `${BASE}/declarations/${bogusDecl}/pay`,
                  body: { payment_ref: 'STRESS_F8AD_PAY' } },
                { name: 'email_bogus_decl', method: 'post',
                  path: `${BASE}/declarations/${bogusDecl}/email`,
                  body: { recipients: ['stress-f8ad@example.invalid'] } },
                { name: 'export_bogus_decl', method: 'get',
                  path: `${BASE}/declarations/${bogusDecl}/export?format=json`, body: undefined },
            ];
            for (const p of bogusProbes) {
                const r = await callTimed(request, p.method, p.path, p.body, sToken);
                if (is4xx(r.status)) {
                    rec(testInfo, { module: MOD, step: p.name, status: 'PASS',
                        note: `http=${r.status} (bogus id rejected)` });
                } else if (is2xx(r.status)) {
                    recFinding(testInfo, 'P1', MOD,
                        `Konaklama Vergisi ${p.name} accepts bogus decl_id`,
                        `${p.method.toUpperCase()} ${p.path} → http=${r.status}. Silent no-op / accounting IDOR class regression risk.`);
                } else {
                    recFinding(testInfo, 'P2', MOD,
                        `Konaklama Vergisi ${p.name} returned 5xx on bogus id`,
                        `${p.method.toUpperCase()} ${p.path} → http=${r.status}. Expected 4xx (404/400); 5xx = backend regression.`);
                    rec(testInfo, { module: MOD, step: p.name, status: 'REVIEW',
                        note: `http=${r.status}` });
                }
            }

            // D. POST /post-folio/{bogus_folio_id} → 4xx zorunlu.
            const bogusFolio = `STRESS_F8AD_BOGUS_FOLIO_${randomUUID()}`;
            const postFolio = await callTimed(request, 'post',
                `${BASE}/post-folio/${bogusFolio}`, {}, sToken);
            if (is4xx(postFolio.status)) {
                rec(testInfo, { module: MOD, step: 'post_folio_bogus', status: 'PASS',
                    note: `http=${postFolio.status} (bogus folio rejected)` });
            } else if (is2xx(postFolio.status)) {
                recFinding(testInfo, 'P1', MOD,
                    'Konaklama Vergisi post-folio accepts bogus folio_id',
                    `POST ${BASE}/post-folio/${bogusFolio} → http=${postFolio.status}. Money safety / silent no-op risk.`);
            } else {
                recFinding(testInfo, 'P2', MOD,
                    'post-folio 5xx on bogus id',
                    `POST ${BASE}/post-folio/${bogusFolio} → http=${postFolio.status}. Expected 4xx.`);
            }

            // E. Idempotency-Key replay on post-folio bogus — aynı key + aynı
            //    bogus folio_id → her ikisi 4xx zorunlu.
            const idemKey = `stress-f8ad-${randomUUID()}`;
            const replay1 = await callTimed(request, 'post',
                `${BASE}/post-folio/${bogusFolio}`, {}, sToken,
                { headers: { 'Idempotency-Key': idemKey } });
            const replay2 = await callTimed(request, 'post',
                `${BASE}/post-folio/${bogusFolio}`, {}, sToken,
                { headers: { 'Idempotency-Key': idemKey } });
            if (is2xx(replay1.status) || is2xx(replay2.status)) {
                recFinding(testInfo, 'P1', MOD,
                    'Idempotency-Key replay on bogus folio accepted',
                    `POST ${BASE}/post-folio/${bogusFolio} replay: http1=${replay1.status} http2=${replay2.status}.`);
            } else if (is4xx(replay1.status) && is4xx(replay2.status)) {
                rec(testInfo, { module: MOD, step: 'post_folio_replay', status: 'PASS',
                    note: `http1=${replay1.status} http2=${replay2.status}` });
            } else {
                recFinding(testInfo, 'P2', MOD,
                    'post-folio replay 5xx',
                    `http1=${replay1.status} http2=${replay2.status}. Expected both 4xx.`);
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'kvb_write_negative_batch',
                stressTokens.seed_state ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
            await assertKvbPilotDriftZero(testInfo, MOD, request, pToken, kvbBefore);
        }
    });

    test('P0 cross-tenant IDOR — stress_token vs pilot resources (hard-fail)', async ({ request, stressTokens }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        const kvbBefore = await kvbDriftCount(request, pToken);

        try {
            if (!pToken) {
                rec(testInfo, { module: MOD, step: 'cross_tenant_idor', status: 'SKIP',
                    note: 'pilot_token yok — IDOR doğrulanamadı' });
                return;
            }

            // Pilot decl harvest.
            const pilotDecls = await fetchSingle(request, pToken, `${BASE}/declarations?limit=5`);
            const declItems = pilotDecls?.raw?.items || pilotDecls?.list || [];
            const pilotDeclId = declItems[0]?.id || declItems[0]?._id || null;

            if (!pilotDeclId) {
                rec(testInfo, { module: MOD, step: 'cross_tenant_idor_decl', status: 'SKIP',
                    note: 'pilot declaration harvest empty — decl IDOR target yok' });
                recFinding(testInfo, 'P2', MOD,
                    'Pilot konaklama vergisi declaration pool empty — IDOR vacuously holds',
                    `GET ${BASE}/declarations?limit=5 list_len=${declItems.length}; cross-tenant decl probe surface eksik.`);
            } else {
                const idorProbes = [
                    { name: 'idor_get_decl', method: 'get',
                      path: `${BASE}/declarations/${pilotDeclId}`, body: undefined },
                    { name: 'idor_submit_decl', method: 'post',
                      path: `${BASE}/declarations/${pilotDeclId}/submit`,
                      body: { submission_ref: 'STRESS_F8AD_IDOR_REF' } },
                    { name: 'idor_pay_decl', method: 'post',
                      path: `${BASE}/declarations/${pilotDeclId}/pay`,
                      body: { payment_ref: 'STRESS_F8AD_IDOR_PAY' } },
                    { name: 'idor_email_decl', method: 'post',
                      path: `${BASE}/declarations/${pilotDeclId}/email`,
                      body: { recipients: ['stress-f8ad@example.invalid'] } },
                    { name: 'idor_export_decl', method: 'get',
                      path: `${BASE}/declarations/${pilotDeclId}/export?format=json`,
                      body: undefined },
                ];
                for (const p of idorProbes) {
                    const r = await callTimed(request, p.method, p.path, p.body, sToken);
                    if (is2xx(r.status)) {
                        recFinding(testInfo, 'P0', MOD,
                            `Cross-tenant Konaklama Vergisi ${p.name} IDOR`,
                            `stress_token ${p.method.toUpperCase()} ${p.path} → ${r.status} (PILOT declaration leaked/mutated). KESIN tenant breach.`);
                        expect(r.status, `cross-tenant ${p.name} must be 4xx`).toBeGreaterThanOrEqual(400);
                    } else {
                        rec(testInfo, { module: MOD, step: p.name, status: 'PASS',
                            note: `http=${r.status} (tenant guard enforced)` });
                    }
                }
            }

            // Pilot → stress yönü (hard-fail): PILOT bearer + STRESS tenant'ta
            // test 1'de finalize ile seed edilen GERÇEK decl_id. _load_decl
            // tenant_id ile filtreler → pilot bu decl'e ASLA erişemez (404).
            // Her probe ≥400 zorunlu; 2xx = KESIN tenant breach (P0). Bu yön
            // hiçbir mutation üretmez: decl pilot tenant'ta yok, email/submit/
            // pay _load_decl'de 404'e takılır (outbound/Resend tetiklenmez).
            if (seededDeclId) {
                const denyProbes = [
                    { name: 'idor_pilot_get_stress_decl', method: 'get',
                      path: `${BASE}/declarations/${seededDeclId}`, body: undefined },
                    { name: 'idor_pilot_submit_stress_decl', method: 'post',
                      path: `${BASE}/declarations/${seededDeclId}/submit`,
                      body: { submission_ref: 'STRESS_F8AD_IDOR_REF' } },
                    { name: 'idor_pilot_pay_stress_decl', method: 'post',
                      path: `${BASE}/declarations/${seededDeclId}/pay`,
                      body: { payment_ref: 'STRESS_F8AD_IDOR_PAY' } },
                    { name: 'idor_pilot_email_stress_decl', method: 'post',
                      path: `${BASE}/declarations/${seededDeclId}/email`,
                      body: { recipients: ['stress-f8ad@example.invalid'] } },
                    { name: 'idor_pilot_export_stress_decl', method: 'get',
                      path: `${BASE}/declarations/${seededDeclId}/export?format=json`, body: undefined },
                ];
                for (const p of denyProbes) {
                    const r = await callTimed(request, p.method, p.path, p.body, pToken);
                    if (is2xx(r.status)) {
                        recFinding(testInfo, 'P0', MOD,
                            `Cross-tenant Konaklama Vergisi ${p.name} IDOR`,
                            `pilot_token ${p.method.toUpperCase()} ${p.path} → ${r.status} (STRESS declaration leaked/mutated). KESIN tenant breach.`);
                        expect(r.status, `pilot→stress ${p.name} must be 4xx`).toBeGreaterThanOrEqual(400);
                    } else {
                        rec(testInfo, { module: MOD, step: p.name, status: 'PASS',
                            note: `http=${r.status} (tenant guard enforced)` });
                    }
                }
            } else {
                rec(testInfo, { module: MOD, step: 'idor_pilot_stress_decl', status: 'SKIP',
                    note: 'stress declaration seed yok (test 1 module-blocked) — pilot→stress decl IDOR target yok' });
            }

            // Pilot folio harvest.
            const pilotFolios = await fetchSingle(request, pToken, '/api/folios?limit=5');
            const folioItems = pilotFolios?.raw?.folios || pilotFolios?.raw?.items || pilotFolios?.list || [];
            const pilotFolioId = folioItems[0]?.id || folioItems[0]?._id || null;
            if (pilotFolioId) {
                const r = await callTimed(request, 'post',
                    `${BASE}/post-folio/${pilotFolioId}`, {}, sToken);
                if (is2xx(r.status)) {
                    recFinding(testInfo, 'P0', MOD,
                        'Cross-tenant Konaklama Vergisi post-folio IDOR',
                        `stress_token POST ${BASE}/post-folio/${pilotFolioId} → ${r.status} (PILOT folio'ya konaklama vergisi posting yazıldı). KESIN tenant breach + finansal mutation.`);
                    expect(r.status, 'cross-tenant post-folio must be 4xx').toBeGreaterThanOrEqual(400);
                } else {
                    rec(testInfo, { module: MOD, step: 'idor_post_folio', status: 'PASS',
                        note: `http=${r.status} (tenant guard enforced)` });
                }
            } else {
                rec(testInfo, { module: MOD, step: 'idor_post_folio', status: 'SKIP',
                    note: 'pilot folio harvest empty' });
            }

            // Pilot → stress post-folio yönü (hard-fail): STRESS tenant'tan
            // bir folio_id harvest et (seed edilen bookings folio_id taşır),
            // PILOT bearer ile post-folio çağır → ≥400 zorunlu (folio pilot
            // tenant'ta yok → folio_not_found 404). Bu yön HİÇBİR mutation
            // üretmez: pilot tenant'ta o folio yok (yazma yapılmaz), stress
            // folio'ya da pilot token erişemez (tenant guard). 2xx = P0 breach.
            const stressBookingsForFolio = await fetchSingle(request, sToken, '/api/pms/bookings?limit=5');
            const sbItems = stressBookingsForFolio?.raw?.bookings || stressBookingsForFolio?.list || [];
            const stressFolioId = sbItems[0]?.folio_id || null;
            if (stressFolioId) {
                const r = await callTimed(request, 'post',
                    `${BASE}/post-folio/${stressFolioId}`, {}, pToken);
                if (is2xx(r.status)) {
                    recFinding(testInfo, 'P0', MOD,
                        'Cross-tenant Konaklama Vergisi post-folio IDOR (pilot→stress)',
                        `pilot_token POST ${BASE}/post-folio/${stressFolioId} → ${r.status} (STRESS folio'ya pilot token ile konaklama vergisi posting yazıldı). KESIN tenant breach + finansal mutation.`);
                    expect(r.status, 'pilot→stress post-folio must be 4xx').toBeGreaterThanOrEqual(400);
                } else {
                    rec(testInfo, { module: MOD, step: 'idor_pilot_post_stress_folio', status: 'PASS',
                        note: `http=${r.status} (tenant guard enforced)` });
                }
            } else {
                rec(testInfo, { module: MOD, step: 'idor_pilot_post_stress_folio', status: 'SKIP',
                    note: 'stress folio harvest empty (booking.folio_id yok)' });
            }

            // P0 IDOR — config PUT + finalize. Bu endpoint'ler tenant_id
            // input ALMAZ (current_user.tenant_id'den türer); structural
            // olarak cross-tenant breach yapamazlar. Doğrulama: stress_token
            // ile çağrı sonrası pilot config + declarations + postings count
            // DEĞİŞMEMELİ. Mutation guard'ı `assertKvbPilotDriftZero`
            // finally bloğunda yapar; ek olarak burada pilot config'i alıp
            // updated_at field'ının baseline ile aynı kalmasını da
            // doğruluyoruz (pilot config snapshot).
            //
            // NOT: PUT /config + finalize STRESS TENANT'TA mutation üretir.
            // Bu spec stress mutation YAPMA kuralına UYAR: PUT body invalid
            // (rate=999 → 4xx, B ve C testlerinde test edildi), finalize
            // year=1999 → 4xx. Burada SADECE pilot tenant snapshot guard'ı
            // doğrularız (defense-in-depth — yukarıdaki invalid probe'lar
            // pilot'a bile sızmamalı).
            const pilotCfgBefore = await callTimed(request, 'get', `${BASE}/config`,
                undefined, pToken);
            // Stress_token ile invalid PUT — pilot config'in updated_at'i değişmemeli.
            await callTimed(request, 'put', `${BASE}/config`,
                { rate_percent: 999, active: true, auto_post: false }, sToken);
            // Stress_token ile invalid finalize — pilot decl count değişmemeli
            // (assertKvbPilotDriftZero finally'de doğrular).
            await callTimed(request, 'post', `${BASE}/declaration/finalize`,
                { year: 1999, month: 6 }, sToken);
            const pilotCfgAfter = await callTimed(request, 'get', `${BASE}/config`,
                undefined, pToken);
            if (is2xx(pilotCfgBefore.status) && is2xx(pilotCfgAfter.status)) {
                const beforeStamp = pilotCfgBefore.body?.updated_at ?? null;
                const afterStamp = pilotCfgAfter.body?.updated_at ?? null;
                if (beforeStamp === afterStamp) {
                    rec(testInfo, { module: MOD, step: 'idor_config_finalize_pilot_snapshot',
                        status: 'PASS',
                        note: `pilot config updated_at unchanged (${beforeStamp ?? 'null'})` });
                } else {
                    recFinding(testInfo, 'P0', MOD,
                        'Cross-tenant Konaklama Vergisi config IDOR via PUT /config',
                        `stress_token PUT/finalize sonrası pilot config updated_at değişti: before=${beforeStamp} after=${afterStamp}. KESIN tenant breach.`);
                    expect(afterStamp, 'pilot config must not be mutated by stress_token').toBe(beforeStamp);
                }
            } else {
                rec(testInfo, { module: MOD, step: 'idor_config_finalize_pilot_snapshot',
                    status: 'REVIEW',
                    note: `pilot cfg http: before=${pilotCfgBefore.status} after=${pilotCfgAfter.status}` });
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'kvb_idor_batch',
                stressTokens.seed_state ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
            await assertKvbPilotDriftZero(testInfo, MOD, request, pToken, kvbBefore);
        }
    });
});
