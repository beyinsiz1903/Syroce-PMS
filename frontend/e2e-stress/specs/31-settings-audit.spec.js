// F8I § 31 — Settings Mutation + Audit Trail + Cross-Tenant Drift Guard.
//
// Threat-model surface: tenant settings mutation cross-tenant leak (en kötü
// senaryoda stress tenant'ta yapılan PATCH pilot tenant settings'i de
// değiştirir → cross-tenant tampering P0). Bu spec PATCH /admin/tenants/
// {stress_tid}/info ile benign metadata mutation yapar, audit entry'nin
// stress tenant_id ile yazıldığını ve pilot tenant info'nun değişmediğini
// kanıtlar.
//
// Mutlak kurallar:
//   - pilot mutation YOK (bookings drift + settings drift = 0)
//   - external_calls=[] (post-batch)
//   - failedTests=0, P0=P1=0
//
// Module-blocked pattern:
//   - admin tenants probe 4xx → moduleBlocked, A/B/C skip + P2 informational;
//     D pilot_drift bağımsız çalışır
//
// Önemli: mutation IDEMPOTENT — orijinal değer setup'ta okunur, suite sonunda
// restore edilir. Audit_logs koleksiyonuna ASLA dokunulmaz (KVKK).
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    assertPiiMasked, withModuleProbe, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';
import fs from 'node:fs';
import path from 'node:path';

const MOD = 'settings_audit';

test.describe.configure({ mode: 'serial' });

test.describe('F8I § 31 — Settings + Audit', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let stressTenantSnapshot = null;
    let pilotTenantSnapshot = null;
    let originalDescription = null;
    let mutationMarker = null;

    test('Setup: prefix + pilot baseline + tenants probe + snapshots', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        const probe = await withModuleProbe(request, stressTokens.stress_token, '/api/admin/tenants');
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `admin_tenants_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Admin tenants probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B/C/D skipped, F pilot_drift still enforced.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }

        // Tenant list'ten stress + pilot tenant snapshot'larını al.
        const list = Array.isArray(probe.body) ? probe.body
            : (probe.body?.tenants || probe.body?.items || probe.body?.data || []);
        stressTenantSnapshot = list.find(t => (t.id || t._id) === stressState.stress_tid) || null;
        pilotTenantSnapshot = list.find(t => (t.id || t._id) === stressState.pilot_tid) || null;

        if (!stressTenantSnapshot) {
            moduleBlocked = true;
            blockedReason = 'stress_tenant_not_in_list';
            recFinding(testInfo, 'P2', MOD, 'Stress tenant not found in /admin/tenants response',
                `stress_tid=${stressState.stress_tid} list_len=${list.length} — A/B/C/D skipped.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS', note: 'module_blocked=true reason=stress_tenant_not_in_list' });
            return;
        }
        originalDescription = stressTenantSnapshot.description || '';
        mutationMarker = `${prefix}stress_audit_test_marker`;

        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} stress_snap=ok pilot_snap=${pilotTenantSnapshot ? 'ok' : 'missing'} module_blocked=false` });
        // Architect re-review #2: trivial hard expect kaldırıldı.
    });

    test('A) Settings mutation — PATCH /admin/tenants/{stress_tid}/info with prefix-tagged description', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'mutation', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const r = await callTimedWithBackoff(request, 'patch',
            `/api/admin/tenants/${stressState.stress_tid}/info`,
            { description: mutationMarker },
            stressTokens.stress_token);
        const ok = r.ok && r.body?.success === true;
        rec(testInfo, { module: MOD, step: 'mutation',
            status: ok ? 'PASS' : 'REVIEW',
            endpoint: `PATCH /admin/tenants/${stressState.stress_tid}/info`, http: r.status,
            note: ok ? `marker_set=${mutationMarker}` : `body=${JSON.stringify(r.body).slice(0, 160)}` });
        if (!ok) {
            recFinding(testInfo, 'P2', MOD, 'Stress tenant info PATCH failed',
                `status=${r.status} body=${JSON.stringify(r.body).slice(0, 160)} — B/C skip mantığı bu sonuçtan etkilenmez ama mutation izi yok.`);
            // Mutation yapamadıysak restore gereği de yok; flag at.
            mutationMarker = null;
        }
        // Architect re-review #2: trivial hard expect kaldırıldı.
    });

    test('B) Audit trail — mutation entry exists with stress tenant_id binding (architect review #3)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked || !mutationMarker) {
            rec(testInfo, { module: MOD, step: 'audit_trail', status: 'SKIP', note: 'module blocked or mutation skipped' });
            test.skip(true, 'no mutation to verify');
            return;
        }
        // 2 endpoint dener: /api/audit/timeline (in-tenant) ve /api/security/audit-logs.
        // Audit yazımı async olabilir; 3s grace + 2 retry.
        let r1, r2, reachable = false, found = false, foundEntry = null, tenantBindingOk = false;
        for (let attempt = 0; attempt < 3 && !found; attempt++) {
            if (attempt > 0) await new Promise(res => setTimeout(res, 1500));
            r1 = await callTimed(request, 'get', '/api/audit/timeline?limit=100', undefined, stressTokens.stress_token);
            r2 = await callTimed(request, 'get', '/api/security/audit-logs?days=1&limit=200', undefined, stressTokens.stress_token);
            reachable = r1.ok || r2.ok;

            // Architect review #3: mutation marker'ı içeren entry'yi bul ve
            // tenant_id == stress_tid bağlamasını doğrula.
            const harvest = (resp) => {
                if (!resp?.ok || !resp.body) return [];
                const b = resp.body;
                return Array.isArray(b) ? b
                    : (b.events || b.logs || b.items || b.audit_logs || b.data || []);
            };
            const entries = [...harvest(r1), ...harvest(r2)];
            for (const e of entries) {
                const serialized = JSON.stringify(e);
                if (mutationMarker && serialized.includes(mutationMarker)) {
                    found = true;
                    foundEntry = e;
                    const tid = e.tenant_id || e.tenantId || e.target_tenant_id;
                    if (tid && tid === stressState.stress_tid) tenantBindingOk = true;
                    break;
                }
            }
        }

        rec(testInfo, { module: MOD, step: 'audit_reachability',
            status: reachable ? 'PASS' : 'REVIEW',
            note: `timeline=${r1?.status} security_audit=${r2?.status} mutation_found=${found} tenant_bind_ok=${tenantBindingOk}` });

        // PII guard — audit log response'unda raw phone/email/identity_number bulunmamalı.
        let piiOk = true;
        if (r1?.ok) {
            const ok = assertPiiMasked(testInfo, MOD, r1.body, ['phone', 'email', 'identity_number', 'iban']);
            piiOk = piiOk && ok;
        }
        if (r2?.ok) {
            const ok = assertPiiMasked(testInfo, MOD, r2.body, ['phone', 'email', 'identity_number', 'iban']);
            piiOk = piiOk && ok;
        }
        rec(testInfo, { module: MOD, step: 'audit_pii_guard',
            status: piiOk ? 'PASS' : 'FAIL',
            note: `timeline_ok=${r1?.ok} audit_ok=${r2?.ok} pii_ok=${piiOk}` });

        if (!reachable) {
            recFinding(testInfo, 'P2', MOD, 'Audit endpoints unreachable',
                `timeline=${r1?.status} security_audit=${r2?.status} — audit verification deferred to ops review.`);
        } else if (!found) {
            // Reachable ama mutation entry yok — async deferred veya endpoint
            // tenant info PATCH'ini audit etmiyor olabilir. Informational P2.
            recFinding(testInfo, 'P2', MOD, 'Audit entry for mutation marker not found within 3 retries',
                `marker=${mutationMarker} timeline=${r1?.status} audit=${r2?.status} — async deferred yazım veya PATCH /admin/tenants/{id}/info audit kapsamı dışında olabilir.`);
        } else if (!tenantBindingOk) {
            // Bulundu AMA tenant_id ya yok ya da yanlış → P1 (cross-tenant
            // contamination riski).
            recFinding(testInfo, 'P1', MOD,
                'Audit entry tenant_id binding eksik veya yanlış',
                `entry=${JSON.stringify(foundEntry).slice(0, 200)} expected_tid=${stressState.stress_tid} — audit yazımı tenant_id\'yi taşımıyor; cross-tenant attribution riski.`);
        }
    });

    test('C) Cross-tenant settings drift — pilot tenant info baseline\'a göre ZERO drift', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked || !pilotTenantSnapshot) {
            rec(testInfo, { module: MOD, step: 'pilot_settings_drift', status: 'SKIP',
                note: `module_blocked=${moduleBlocked} pilot_snap_present=${!!pilotTenantSnapshot}` });
            test.skip(true, 'no pilot snapshot');
            return;
        }
        // Pilot tenant'ı listeden re-fetch et, baseline ile karşılaştır.
        const r = await callTimed(request, 'get', '/api/admin/tenants', undefined, stressTokens.stress_token);
        if (!r.ok) {
            recFinding(testInfo, 'P2', MOD, 'Pilot tenant re-fetch failed',
                `status=${r.status} body=${JSON.stringify(r.body).slice(0, 120)}`);
            test.skip(true, 'pilot re-fetch failed');
            return;
        }
        const list = Array.isArray(r.body) ? r.body
            : (r.body?.tenants || r.body?.items || r.body?.data || []);
        const after = list.find(t => (t.id || t._id) === stressState.pilot_tid);
        if (!after) {
            recFinding(testInfo, 'P2', MOD, 'Pilot tenant disappeared from list',
                `pilot_tid=${stressState.pilot_tid} not in re-fetched list (len=${list.length})`);
            test.skip(true, 'pilot disappeared');
            return;
        }
        // Karşılaştırma — pilot tenant'ın description / property_name / phone /
        // email / address / total_rooms baseline'a eşit olmalı. Marker pilot'ta
        // GÖRÜLMEMELİ.
        const sensitiveFields = ['description', 'property_name', 'phone', 'email', 'address', 'total_rooms', 'modules'];
        const diffs = [];
        for (const f of sensitiveFields) {
            const a = JSON.stringify(pilotTenantSnapshot[f] ?? null);
            const b = JSON.stringify(after[f] ?? null);
            if (a !== b) diffs.push({ field: f, before: a.slice(0, 80), after: b.slice(0, 80) });
        }
        // Marker spesifik kontrol — pilot description'unda marker stringi olmamalı.
        const markerLeak = mutationMarker && JSON.stringify(after).includes(mutationMarker);

        const pass = diffs.length === 0 && !markerLeak;
        rec(testInfo, { module: MOD, step: 'pilot_settings_drift',
            status: pass ? 'PASS' : 'FAIL',
            note: `diffs=${diffs.length} marker_leak=${markerLeak}` });
        if (!pass) {
            recFinding(testInfo, 'P0', MOD,
                'Cross-tenant settings drift — stress tenant mutation pilot tenant\'ı etkiledi',
                `diffs=${JSON.stringify(diffs)} marker_leak=${markerLeak}. CROSS-TENANT TAMPERING — tenant isolation kırılmış.`);
        }
        // Architect review #1: hard expect KALDIRILDI — P0 finding reporter'ı
        // NO-GO yapar, downstream restore + invariants çalışmaya devam eder.
    });

    test('D) Rate-limit boundary — admin tenants GET 20x ardışık, 5xx olmamalı', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'rate_limit_boundary', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Validation review (2026-05-19): contract = "yalnızca 200 (200-299)
        // veya 429 kabul edilir". 5xx → P1, diğer statuslar (401/403/400/409
        // vb.) → P1 contract violation (auth degrade veya unexpected fail).
        let ok2xx = 0, throttled = 0, server5xx = 0, otherContractViolations = 0;
        const statuses = [];
        const otherStatuses = [];
        for (let i = 0; i < 20; i++) {
            const r = await callTimed(request, 'get', '/api/admin/tenants', undefined, stressTokens.stress_token);
            statuses.push(r.status);
            if (r.status >= 200 && r.status < 300) ok2xx++;
            else if (r.status === 429) throttled++;
            else if (r.status >= 500) server5xx++;
            else { otherContractViolations++; otherStatuses.push(r.status); }
        }
        const pass = server5xx === 0 && otherContractViolations === 0;
        rec(testInfo, { module: MOD, step: 'rate_limit_boundary',
            status: pass ? 'PASS' : 'FAIL',
            note: `2xx=${ok2xx} 429=${throttled} 5xx=${server5xx} other=${otherContractViolations} statuses=${statuses.join(',')}` });
        if (server5xx > 0) {
            recFinding(testInfo, 'P1', MOD,
                'Admin read endpoint 5xx altında stres',
                `5xx_count=${server5xx} statuses=${statuses.join(',')} — backend admin read endpoint rate-limit altında çöküyor; 429 veya stabil 200 beklenir.`);
        }
        if (otherContractViolations > 0) {
            recFinding(testInfo, 'P1', MOD,
                'Admin read rate-limit boundary status contract ihlali',
                `Beklenen status sınıfı: 200 veya 429. Alınan diğer statuslar: ${otherStatuses.join(',')}. Tüm dağılım: ${statuses.join(',')}.`);
        }
    });

    test('E) Restore: stress tenant description orijinaline geri al', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked || mutationMarker == null) {
            rec(testInfo, { module: MOD, step: 'restore', status: 'SKIP', note: 'no mutation to restore' });
            return;
        }
        const r = await callTimed(request, 'patch',
            `/api/admin/tenants/${stressState.stress_tid}/info`,
            { description: originalDescription || ' ' },
            stressTokens.stress_token);
        const ok = r.ok;
        rec(testInfo, { module: MOD, step: 'restore',
            status: ok ? 'PASS' : 'REVIEW',
            note: ok ? 'description restored' : `status=${r.status} body=${JSON.stringify(r.body).slice(0, 160)}` });
        if (!ok) {
            recFinding(testInfo, 'P2', MOD, 'Stress tenant description restore failed',
                `status=${r.status} — marker '${mutationMarker}' kalmış olabilir; ops manuel restore edebilir.`);
        }
        // Architect re-review #2: trivial hard expect kaldırıldı + afterAll
        // belt-and-suspenders restore garanti edecek.
    });

    test('F) external_calls invariant + pilot_drift=0', async ({ request, stressTokens }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const stateBlob = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-state.json'), 'utf-8'));
        await assertNoExternalCallsPostBatch(testInfo, MOD, 'settings_audit_done', stateBlob, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: 'PASS', note: 'pilot_drift+external_calls verified' });
        expect(true).toBe(true);
    });

    // Architect review #1 (2026-05-19): garanti restore — serial mode'da
    // intermediate test fail olsa bile mutation marker'ı pilot drift gibi
    // önemli güvenlik artefaktı bırakmaması için belt-and-suspenders.
    test.afterAll(async () => {
        if (!mutationMarker) return;
        try {
            const stateBlob = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-state.json'), 'utf-8'));
            const tokenBlob = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-token.json'), 'utf-8'));
            const { request: apiReq } = await import('@playwright/test');
            const ctx = await apiReq.newContext({ baseURL: process.env.E2E_BASE_URL });
            const r = await ctx.patch(`/api/admin/tenants/${stateBlob.stress_tid}/info`, {
                headers: { Authorization: `Bearer ${tokenBlob.stress_token}` },
                data: { description: originalDescription || ' ' },
                failOnStatusCode: false,
                timeout: 30_000,
            });
            await ctx.dispose();
            console.log(`[F8I § 31 afterAll] belt-and-suspenders restore: status=${r.status()}`);
        } catch (e) {
            console.log(`[F8I § 31 afterAll] restore failed: ${e.message}`);
        }
    });
});
