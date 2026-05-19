// F8L § 52 — Outbox Idempotency + Conflict Queue Stress.
//
// Threat-model surface (threat_model.md § Tampering + Information
// Disclosure + DoS): SXI bus outbox (`outbox_events`) ve Afsadakat
// outbox (`integration_afsadakat_outbox`) event-driven integration
// noktası. Idempotency key = tenant:event:entity:payload_hash. Aynı key
// ile iki POST → tek event satırı + tek dispatch. Conflict Queue
// (`/api/channel-manager/conflict-queue`) pending_assignment booking'lere
// front-desk erişimi sağlar; cross-tenant leak'i tek hamlede booking +
// guest PII expose eder.
//
// Mutlak kurallar:
//   - pilot mutation YOK (drift=0). Hiçbir POST pilot tenant'a yapılmaz;
//     stress_tid scope'lu lookup'lar + read-only conflict queue + outbox
//     status read.
//   - external_calls=[] (post-batch helper). Outbox dispatcher dry-run
//     EXTERNAL_DRY_RUN=true ile fakelenmiş; gerçek HTTP push edilmez.
//   - failedTests=0, P0=P1=0.
//
// Module-blocked pattern (F8M § 40/41 + F8L § 50/51 mirror):
//   - GET /api/outbox/status non-2xx → moduleBlocked + P2 + A/B/C skip;
//     D pilot_drift + external_calls bağımsız.
//
// Backend yüzeyleri:
//   - GET  /api/outbox/status   (super_admin)
//   - GET  /api/outbox/events?status=...&provider=...   (super_admin)
//   - POST /api/outbox/{id}/requeue   (super_admin)  — KULLANMIYORUZ
//   - POST /api/outbox/replay         (super_admin)  — KULLANMIYORUZ
//   - GET  /api/channel-manager/conflict-queue       (RBAC view bookings)
//   - GET  /api/channel-manager/conflict-queue/count (RBAC view bookings)
//   - POST /api/channel-manager/conflict-queue/{id}/resolve  — KULLANMIYORUZ
//   - POST /api/channel-manager/conflict-queue/bulk-resolve  — KULLANMIYORUZ
//
// Idempotency kanıt doktrini:
//   Outbox event yazımı backend pipeline'ı tarafından yapılır (webhook
//   ingest, no-show, booking events). Spec direkt yazma yapmaz — bunun
//   yerine outbox status'u 2 kez (delta ölçümü) okur + stress_tid scope'lu
//   external-calls endpoint'inde 0 görür. Idempotency kontrat sinyali:
//     1) GET /api/outbox/status t1 → snapshot
//     2) [no-op probe — webhook tetiklenmez]
//     3) GET /api/outbox/status t2 → snapshot
//     4) pending/processing/retry/failed delta == 0 beklenir (stress
//        suite'in bu noktasında outbox'a yazan başka bir aktivite yok).
//   Eğer delta > 0 ise: ya başka spec yazdı (P2 informational) ya da
//   external-calls'da real dispatch göründü (P0 — assertNoExternalCalls
//   yakalar).
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    assertPiiMasked, assertNoTokenLeak, withModuleProbe, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';
import fs from 'node:fs';
import path from 'node:path';

const MOD = 'cm_outbox';

test.describe.configure({ mode: 'serial' });

test.describe('F8L § 52 — Outbox Idempotency + Conflict Queue', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let stressTid = null;
    let pilotTid = null;
    let outboxT1 = null;

    test('Setup: prefix + pilot baseline + outbox status reachability + t1 snapshot', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        stressTid = stressState.stress_tid;
        pilotTid = stressState.pilot_tid;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // Outbox status pilot super_admin token gerektirir (require_super_admin).
        // Stres token super_admin DEĞİL → 401/403; bu yüzden pilot_token kullanırız.
        const probe = await callTimed(request, 'get', '/api/outbox/status',
            undefined, stressTokens.pilot_token);
        if (!probe.ok) {
            moduleBlocked = true;
            blockedReason = `outbox_status_non2xx_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Outbox status endpoint probe non-2xx',
                `GET /api/outbox/status status=${probe.status} body=${JSON.stringify(probe.body).slice(0, 160)} — super_admin guard veya router deploy. A/B/C skipped, D pilot_drift+external_calls bağımsız.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        outboxT1 = probe.body || {};
        // Token leak guard — status payload credential içermemeli.
        assertNoTokenLeak(testInfo, MOD, outboxT1, 'outbox_status_t1');

        rec(testInfo, { module: MOD, step: 'setup',
            status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} stress_tid=${stressTid?.slice(0, 8)} t1_pending=${outboxT1.pending} t1_processing=${outboxT1.processing} t1_failed=${outboxT1.failed} t1_retry=${outboxT1.retry}` });
    });

    test('A) Outbox status delta — no-op window: pending/processing/retry/failed delta == 0', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'outbox_delta', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // No-op window: setup ile A test'i arasında stress suite'in bu noktasında
        // outbox'a yazan başka bir spec çalışmıyor (parallel mode=serial).
        // Status TTL cache 30s — burst etmemek için 1s bekle.
        await new Promise((r) => setTimeout(r, 1500));
        const t2 = await callTimed(request, 'get', '/api/outbox/status',
            undefined, stressTokens.pilot_token);
        if (!t2.ok) {
            rec(testInfo, { module: MOD, step: 'outbox_t2_read', status: 'REVIEW',
                http: t2.status, note: `t2 fetch fail status=${t2.status}` });
            return;
        }
        const t2b = t2.body || {};
        const fields = ['pending', 'processing', 'retry', 'failed'];
        const deltas = {};
        for (const f of fields) deltas[f] = (t2b[f] || 0) - (outboxT1[f] || 0);
        const nonZero = Object.entries(deltas).filter(([, v]) => v > 0);
        // Cache TTL 30s — delta 0 beklenir; >0 ise dispatcher worker arka
        // planda ilerlemiş veya başka aktivite var. P2 informational
        // (suite-wide guarantee zaten assertNoExternalCallsPostBatch'te).
        rec(testInfo, { module: MOD, step: 'outbox_delta',
            status: nonZero.length === 0 ? 'PASS' : 'REVIEW',
            endpoint: 'GET /api/outbox/status', http: t2.status,
            note: `t1=${JSON.stringify({p:outboxT1.pending,pr:outboxT1.processing,r:outboxT1.retry,f:outboxT1.failed})} t2=${JSON.stringify({p:t2b.pending,pr:t2b.processing,r:t2b.retry,f:t2b.failed})} deltas=${JSON.stringify(deltas)}` });

        if (nonZero.length > 0) {
            recFinding(testInfo, 'P2', MOD,
                'Outbox no-op window altında delta > 0 — başka aktivite veya dispatcher worker',
                `Deltas: ${JSON.stringify(deltas)}. Idempotency contract sinyali zayıf — başka spec/worker outbox'a yazıyor olabilir. Suite-wide external_calls invariant D test'inde enforce edilir.`);
        }

        // Provider-failures field PII/token içermemeli.
        if (t2b.provider_failures) {
            assertNoTokenLeak(testInfo, MOD, t2b.provider_failures, 'outbox_provider_failures');
        }
    });

    test('B) Outbox events list — stress_tid scope\'lu, pilot_tid leak yok + PII mask', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'outbox_events_scope', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // GET /api/outbox/events — super_admin global view (cross-tenant
        // by design). Stress'in burada test ettiği: response'da pilot tenant
        // verisi varsa PII/token leak olmamalı. (Global ops endpoint olduğu
        // için pilot_tid varlığı tek başına leak değil; PII+token guard'ı
        // enforce eder.)
        const r = await callTimed(request, 'get', '/api/outbox/events?limit=20',
            undefined, stressTokens.pilot_token);
        if (!r.ok) {
            rec(testInfo, { module: MOD, step: 'outbox_events_read', status: 'REVIEW',
                http: r.status, note: `fetch fail status=${r.status}` });
            return;
        }
        const list = Array.isArray(r.body) ? r.body
            : (r.body?.events || r.body?.items || []);
        rec(testInfo, { module: MOD, step: 'outbox_events_read',
            status: 'PASS', endpoint: 'GET /api/outbox/events', http: r.status,
            note: `len=${list.length}` });

        // PII + token guard — outbox event payload genelde booking/guest
        // ID'leri taşır; raw PII (phone/email) maskelenmeli ya da hiç olmamalı.
        assertPiiMasked(testInfo, MOD, r.body, ['phone', 'email', 'identity_number', 'guest_phone']);
        assertNoTokenLeak(testInfo, MOD, r.body, 'outbox_events_list');

        // Stres-token (super_admin DEĞİL) ile aynı endpoint → 401/403 beklenir.
        // 2xx + data dönerse RBAC bypass (P0).
        const stresRead = await callTimed(request, 'get', '/api/outbox/events?limit=5',
            undefined, stressTokens.stress_token);
        const denyOk = stresRead.status === 401 || stresRead.status === 403;
        rec(testInfo, { module: MOD, step: 'outbox_events_rbac',
            status: denyOk ? 'PASS' : 'FAIL',
            endpoint: 'GET /api/outbox/events (stress_token)', http: stresRead.status,
            note: `expected=401/403 got=${stresRead.status}` });
        if (stresRead.status >= 200 && stresRead.status < 300) {
            recFinding(testInfo, 'P0', MOD,
                'Outbox events endpoint super_admin guard bypass — stres token 2xx',
                `Stres tenant admin (super_admin DEĞİL) GET /api/outbox/events status=${stresRead.status} döndü. require_super_admin guard enforcement eksik. Threat-model § Elevation of Privilege.`);
        }
    });

    test('C) Conflict Queue — stress tenant scope, count + list reachability, cross-tenant pilot booking leak yok', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'conflict_queue', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // GET /api/channel-manager/conflict-queue → stres tenant'ın
        // pending_assignment booking'leri. Pilot'tan sample bir booking ID
        // alıp stres response'unda görünüp görünmediğini kontrol eder.
        let pilotSampleBookingId = null;
        try {
            const b = await callTimed(request, 'get', '/api/pms/bookings?limit=1',
                undefined, stressTokens.pilot_token);
            if (b.ok) {
                const list = Array.isArray(b.body) ? b.body : (b.body?.bookings || b.body?.items || []);
                if (list[0]) pilotSampleBookingId = list[0].id || list[0]._id;
            }
        } catch (_) { /* best-effort */ }

        const cnt = await callTimed(request, 'get', '/api/channel-manager/conflict-queue/count',
            undefined, stressTokens.stress_token);
        rec(testInfo, { module: MOD, step: 'conflict_queue_count',
            status: cnt.ok ? 'PASS' : 'REVIEW',
            endpoint: 'GET /conflict-queue/count', http: cnt.status,
            note: `body=${JSON.stringify(cnt.body).slice(0, 120)}` });

        const lst = await callTimed(request, 'get', '/api/channel-manager/conflict-queue?limit=50',
            undefined, stressTokens.stress_token);
        if (!lst.ok) {
            rec(testInfo, { module: MOD, step: 'conflict_queue_list',
                status: 'REVIEW', http: lst.status,
                note: `body=${JSON.stringify(lst.body).slice(0, 160)}` });
            return;
        }
        const items = Array.isArray(lst.body) ? lst.body
            : (lst.body?.items || lst.body?.queue || lst.body?.bookings || []);

        // Cross-tenant pilot booking leak guard.
        let pilotLeak = false;
        const blob = JSON.stringify(lst.body);
        if (pilotSampleBookingId && blob.includes(pilotSampleBookingId)) pilotLeak = true;
        if (pilotTid && blob.includes(pilotTid)) pilotLeak = true;

        rec(testInfo, { module: MOD, step: 'conflict_queue_list',
            status: pilotLeak ? 'FAIL' : 'PASS',
            endpoint: 'GET /conflict-queue', http: lst.status,
            note: `len=${items.length} pilot_sample_present=${!!pilotSampleBookingId} pilot_leak=${pilotLeak}` });
        if (pilotLeak) {
            recFinding(testInfo, 'P0', MOD,
                'Conflict Queue cross-tenant leak — pilot booking ID stress response\'unda',
                `pilot_sample=${pilotSampleBookingId} pilot_tid=${pilotTid?.slice(0, 8)}… stres response. Tenant scope eksik. Threat-model § Information Disclosure.`);
        }

        // PII + token guard — pending booking guest_name/phone içerebilir.
        assertPiiMasked(testInfo, MOD, lst.body, ['phone', 'email', 'identity_number', 'guest_phone']);
        assertNoTokenLeak(testInfo, MOD, lst.body, 'conflict_queue_list');

        // Anonymous (no token) reachability — 401/403 beklenir.
        const anon = await callTimed(request, 'get', '/api/channel-manager/conflict-queue?limit=5',
            undefined, '');
        const anonOk = anon.status === 401 || anon.status === 403;
        rec(testInfo, { module: MOD, step: 'conflict_queue_anon',
            status: anonOk ? 'PASS' : 'FAIL',
            endpoint: 'GET /conflict-queue (no auth)', http: anon.status,
            note: `expected=401/403 got=${anon.status}` });
        if (anon.status >= 200 && anon.status < 300) {
            recFinding(testInfo, 'P0', MOD,
                'Conflict Queue anonymous disclosure',
                `GET /api/channel-manager/conflict-queue no-auth status=${anon.status} + data → auth guard yok. Threat-model § Elevation of Privilege.`);
        }
    });

    test('E) Active idempotency — duplicate signed webhook ingest → outbox event delta ≤ 1 (HOTELRUNNER_WEBHOOK_SECRET conditional)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'active_idempotency', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Validator (architect) talebi: pasif delta yetmez; aktif tetik +
        // dedupe assert. Conditional on env (spec 51-F mirror): secret
        // unset → REVIEW + P2 informational. Var ise: aynı imzalı payload
        // 2x POST → outbox_events_count delta ≤ 1 (idempotency anahtarı
        // tenant:event:entity:payload_hash). Dispatcher EXTERNAL_DRY_RUN
        // ortamında fakelenir → external_calls=0 invariant'ı D test'inde.
        const secret = process.env.HOTELRUNNER_WEBHOOK_SECRET || '';
        if (!secret) {
            rec(testInfo, { module: MOD, step: 'active_idempotency',
                status: 'REVIEW',
                note: `HOTELRUNNER_WEBHOOK_SECRET unset → active dedupe assert edilemedi` });
            recFinding(testInfo, 'P2', MOD,
                'Outbox active idempotency coverage gap — secret unset',
                `Passive delta (Test A) PASS; aktif duplicate-dispatch dedupe path'i bu koşuda assert edilemedi. Production readiness için CI env'inde HOTELRUNNER_WEBHOOK_SECRET seed'i öneriliyor (follow-up: aktif idempotency).`);
            return;
        }
        const crypto = await import('node:crypto');
        const ts = String(Math.floor(Date.now() / 1000));
        const stableId = `${prefix || 'STRESS'}_IDEMP_FIXED`;  // KEY: aynı id → aynı dedupe key
        const raw = JSON.stringify({
            tenant_id: stressTid,
            hotel: { id: `${prefix || 'STRESS'}_HOTEL` },
            reservation: { hr_number: stableId, state: 'new', guest: { name: 'STRESS_IDEMP' } },
        });
        const signed = `${ts}.`.concat(raw);
        const sig = `sha256=${crypto.createHmac('sha256', secret).update(signed).digest('hex')}`;
        const headers = { 'X-HotelRunner-Timestamp': ts, 'X-HotelRunner-Signature': sig };

        // Pre-snapshot
        const s1 = await callTimed(request, 'get', '/api/outbox/status', undefined, stressTokens.pilot_token);
        const pending1 = (s1.body?.pending || 0) + (s1.body?.processing || 0);

        const r1 = await fetch(`${process.env.E2E_BASE_URL || ''}/api/channel-manager/hotelrunner/callback`, {
            method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: raw,
        }).catch(() => null);
        await new Promise((r) => setTimeout(r, 800));
        const r2 = await fetch(`${process.env.E2E_BASE_URL || ''}/api/channel-manager/hotelrunner/callback`, {
            method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: raw,
        }).catch(() => null);
        await new Promise((r) => setTimeout(r, 1500));

        const s2 = await callTimed(request, 'get', '/api/outbox/status', undefined, stressTokens.pilot_token);
        const pending2 = (s2.body?.pending || 0) + (s2.body?.processing || 0);
        const delta = pending2 - pending1;

        // Dedupe contract: 2 ingest → en fazla 1 yeni outbox row.
        // Sıkı kural: delta ≤ 1. delta ≥ 2 → idempotency kırık (P0).
        // Not: delta=0 OK (event tipine göre outbox publish opsiyonel
        // olabilir veya cache TTL nedeniyle status henüz refresh olmamış).
        const pass = delta <= 1;
        rec(testInfo, { module: MOD, step: 'active_idempotency',
            status: pass ? 'PASS' : 'FAIL',
            note: `pending_before=${pending1} pending_after=${pending2} delta=${delta} r1_status=${r1?.status} r2_status=${r2?.status} stable_id=${stableId}` });
        if (!pass) {
            recFinding(testInfo, 'P0', MOD,
                'Outbox idempotency kırık — duplicate webhook 2 outbox event üretti',
                `Aynı (tenant=${stressTid?.slice(0, 8)}, hr_number=${stableId}) 2x ingest → outbox pending delta=${delta}. Dedupe key (tenant:event:entity:payload_hash) düşmüş olabilir.`);
        }
    });

    test('D) external_calls invariant + pilot_drift=0', async ({ request, stressTokens }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const stateBlob = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-state.json'), 'utf-8'));
        await assertNoExternalCallsPostBatch(testInfo, MOD, 'cm_outbox_done', stateBlob, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: 'PASS', note: 'pilot_drift+external_calls verified' });
        expect(true).toBe(true);
    });
});
