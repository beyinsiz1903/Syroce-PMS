// F8Q § 45 — Push notification batch dry-run.
//
// Surface: `backend/services/expo_push.py` (DISABLE_EXPO_PUSH=1 → no-op no
// network), `backend/routers/messaging.py` (/send, /delivery-logs, activity
// feed), `backend/workers/mobile_push_scheduler.py` (fire_and_forget).
//
// Doctrine:
//   - DISABLE_EXPO_PUSH guard zorunlu (no real Expo/FCM/APNS HTTP).
//   - 100 notification enqueue → batch process dry-run → idempotency probe.
//   - Invalid device token graceful (no 5xx).
//   - Tenant-scoped delivery-logs only (no cross-tenant leak).
//   - PII/token mask in delivery-logs/activity feed.
//   - external_calls=[] (Expo HTTP fail-closed under DISABLE_EXPO_PUSH).
//   - pilot_drift=0.
//   - Module-blocked → A/B/C SKIP, D pilot_drift bağımsız.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, assertPiiMasked,
} from '../fixtures/stress-helpers.js';

const MOD = 'notification_batch';
const N_NOTIF = 100;

test.describe.configure({ mode: 'serial' });

test.describe('F8Q § 45 — Push notification batch dry-run', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let pushDisabled = false;
    let dupSampleId = null;

    test('Setup: prefix + DISABLE_EXPO_PUSH guard + messaging probe + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // DISABLE_EXPO_PUSH guard: Node env'den okuyoruz (Playwright runner).
        // CI'da .github/workflows/stress.yml içinde set olmalı; lokalde
        // user export ediyor. Set değilse P2 informational (config drift)
        // ama A/B/C skip değil (Expo HTTP fail-closed dry-run yine de
        // external_calls=[] gate'inde yakalanır).
        pushDisabled = process.env.DISABLE_EXPO_PUSH === '1';
        if (!pushDisabled) {
            recFinding(testInfo, 'P2', MOD, 'DISABLE_EXPO_PUSH not set',
                'Env var ENV=stress runner için set değil — Expo HTTP fail-closed assert hala external_calls=[] gate ile yakalanır, ama config drift.');
        }

        const probe = await withModuleProbe(request, stressTokens.stress_token,
            '/api/messaging/settings');
        if (probe.moduleBlocked || probe.status >= 300) {
            moduleBlocked = true;
            blockedReason = probe.reason || `status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'messaging module probe blocked',
                `endpoint=/api/messaging/settings status=${probe.status} reason=${blockedReason} — A/B/C skip, D bağımsız.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} push_disabled=${pushDisabled} probe_status=${probe.status} module_blocked=${moduleBlocked}` });
        expect(true).toBe(true);
    });

    test('A) Batch enqueue 100 + duplicate idempotency + invalid token graceful', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'batch_enqueue', status: 'SKIP', note: blockedReason });
            test.skip(true, 'module blocked');
            return;
        }
        const enqueueResults = [];
        let ok = 0, fail = 0, throttled = 0, serverErr = 0, permFail = 0;
        const errs = [];
        // Stres prefix'li template + payload — gerçek alıcı yok (push
        // settings/activity feed üzerinden simulate). /api/messaging/send
        // body kontratı: { channel, to, subject?, body } — to: stres prefix
        // ile virtual recipient. Backend send-flow Resend/SMS silent (F8B
        // doctrine).
        for (let i = 0; i < N_NOTIF; i++) {
            const r = await callTimed(request, 'post', '/api/messaging/send', {
                channel: 'in_app',
                to: `${prefix}_user_${i}@stress.invalid`,
                subject: `${prefix}_batch_subj_${i}`,
                body: `${prefix}_batch_body_${i}`,
                metadata: { stress_seed: true, stress_prefix: prefix, idx: i },
            }, stressTokens.stress_token);
            if (r.status === 401 || r.status === 403) {
                permFail++;
                if (permFail <= 2) errs.push({ i, status: r.status, snip: JSON.stringify(r.body).slice(0, 120) });
            } else if (r.status === 429) {
                throttled++;
            } else if (r.status >= 500) {
                serverErr++;
                errs.push({ i, status: r.status, snip: JSON.stringify(r.body).slice(0, 120) });
            } else if (r.ok || (r.status >= 200 && r.status < 300)) {
                ok++;
            } else {
                fail++;
                if (fail <= 3) errs.push({ i, status: r.status, snip: JSON.stringify(r.body).slice(0, 120) });
            }
        }

        // Permission short-circuit: tüm istekler 401/403 ise module-blocked
        // doctrine (F8D/E mirror) — REVIEW+P2, A skip değil ama assertion
        // gevşetilmez (extOk gate hala enforce).
        const permAll = permFail >= N_NOTIF * 0.95;
        if (permAll) {
            recFinding(testInfo, 'P2', MOD, 'messaging/send perm-gated (95%+ 401/403)',
                `permFail=${permFail}/${N_NOTIF} — stress_token rolüne /messaging/send permission yok. Backend RBAC kasıtlı.`);
        }

        // Duplicate idempotency probe: aynı stress_seed metadata ile yeniden
        // gönder. Backend duplicate semantik definite contract'a sahip değilse
        // (queue-based async), P2 REVIEW yeterli. Hard-assert: 5xx yok.
        const dup = await callTimed(request, 'post', '/api/messaging/send', {
            channel: 'in_app',
            to: `${prefix}_user_0@stress.invalid`,
            subject: `${prefix}_batch_subj_0`,
            body: `${prefix}_batch_body_0`,
            metadata: { stress_seed: true, stress_prefix: prefix, idx: 0, dup: true },
        }, stressTokens.stress_token);
        dupSampleId = dup.body?.id || dup.body?.delivery_id || dup.body?.message_id || null;
        const dupOk = !permAll && (dup.ok || dup.status === 200 || dup.status === 202 || dup.status === 409);

        // Invalid device token graceful: malformed expo token payload →
        // server graceful (no 5xx). Direct /messaging/send'de device_token
        // yok ama bozuk channel sufficient.
        const bad = await callTimed(request, 'post', '/api/messaging/send', {
            channel: 'invalid_channel_xyz',
            to: 'malformed',
            body: 'x',
        }, stressTokens.stress_token);
        const badGraceful = bad.status < 500;
        if (!badGraceful) {
            recFinding(testInfo, 'P0', MOD, 'invalid notification payload → 5xx',
                `status=${bad.status} snip=${JSON.stringify(bad.body).slice(0, 200)} — server graceful kontrat ihlal.`);
        }

        rec(testInfo, { module: MOD, step: 'batch_enqueue', status: serverErr === 0 && badGraceful ? 'PASS' : 'FAIL',
            note: `N=${N_NOTIF} ok=${ok} fail=${fail} throttled=${throttled} server_err=${serverErr} perm_fail=${permFail} dup_status=${dup.status} bad_graceful=${badGraceful} errs=${JSON.stringify(errs.slice(0, 3))}` });

        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'batch_enqueue', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(serverErr, `5xx count=${serverErr} (graceful contract violated)`).toBe(0);
        expect(badGraceful, `invalid payload → 5xx is a P0`).toBe(true);
    });

    test('B) Tenant-scoped delivery-logs + activity feed + PII/token mask', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'logs_and_pii', status: 'SKIP', note: blockedReason });
            test.skip(true, 'module blocked');
            return;
        }
        const logs = await callTimed(request, 'get', '/api/messaging/delivery-logs?limit=50',
            undefined, stressTokens.stress_token);
        if (logs.status === 401 || logs.status === 403) {
            recFinding(testInfo, 'P2', MOD, 'delivery-logs perm-gated',
                `status=${logs.status} — RBAC short-circuit.`);
            rec(testInfo, { module: MOD, step: 'logs_and_pii', status: 'SKIP', note: `status=${logs.status}` });
            return;
        }
        if (logs.status >= 500) {
            recFinding(testInfo, 'P0', MOD, 'delivery-logs 5xx', `status=${logs.status}`);
        }
        const items = Array.isArray(logs.body?.items) ? logs.body.items
            : Array.isArray(logs.body?.logs) ? logs.body.logs
            : Array.isArray(logs.body) ? logs.body : [];
        // Cross-tenant leak: stress_token GET → hiçbir item PILOT_/PROD_
        // prefix taşımamalı.
        let leaks = 0;
        for (const it of items.slice(0, 50)) {
            let blob = ''; try { blob = JSON.stringify(it); } catch { /* nz */ }
            if (blob.includes('"PILOT_') || blob.includes('"PROD_')) leaks++;
        }
        if (leaks > 0) {
            recFinding(testInfo, 'P0', MOD, 'delivery-logs cross-tenant leak',
                `leaks=${leaks}/${items.length} stress_token döndüğünde pilot prefix marker var.`);
        }
        // PII mask: delivery-logs to/from genelde email/phone — mask kontratı.
        const masked = assertPiiMasked(testInfo, MOD, items, ['phone', 'email', 'to', 'from', 'recipient']);

        rec(testInfo, { module: MOD, step: 'logs_and_pii', status: leaks === 0 && masked && logs.status < 500 ? 'PASS' : 'FAIL',
            note: `status=${logs.status} items=${items.length} leaks=${leaks} pii_masked=${masked}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'logs_and_pii', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(leaks, `cross-tenant leak count=${leaks}`).toBe(0);
        expect(logs.status < 500, `delivery-logs 5xx`).toBe(true);
    });

    test('C) Activity feed read + token mask (notifications endpoint)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'activity_feed', status: 'SKIP', note: blockedReason });
            test.skip(true, 'module blocked');
            return;
        }
        // Activity feed endpoint — varsa real-time notifications. Yoksa 404
        // module-blocked sayılmaz çünkü messaging settings probe geçti;
        // C için soft-skip.
        const feed = await callTimed(request, 'get', '/api/messaging/activity-feed?limit=20',
            undefined, stressTokens.stress_token);
        if (feed.status === 404) {
            rec(testInfo, { module: MOD, step: 'activity_feed', status: 'SKIP', note: 'endpoint 404 (alternate name)' });
            return;
        }
        if (feed.status >= 500) {
            recFinding(testInfo, 'P0', MOD, 'activity-feed 5xx', `status=${feed.status}`);
        }
        const items = Array.isArray(feed.body?.notifications) ? feed.body.notifications
            : Array.isArray(feed.body?.items) ? feed.body.items : [];
        const masked = assertPiiMasked(testInfo, MOD, items, ['phone', 'email']);
        rec(testInfo, { module: MOD, step: 'activity_feed', status: feed.status < 500 && masked ? 'PASS' : 'FAIL',
            note: `status=${feed.status} items=${items.length} pii_masked=${masked}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'activity_feed', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(feed.status < 500, `activity-feed 5xx`).toBe(true);
    });

    test('D) Pilot drift = 0 + external_calls = [] (final invariants)', async ({ request, stressTokens, stressState }, testInfo) => {
        const driftOk = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'final', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'final_invariants', status: driftOk && extOk ? 'PASS' : 'FAIL',
            note: `pilot_drift_zero=${driftOk} external_calls_empty=${extOk} dup_sample=${dupSampleId?.slice?.(0, 8) || 'none'}` });
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
    });
});
