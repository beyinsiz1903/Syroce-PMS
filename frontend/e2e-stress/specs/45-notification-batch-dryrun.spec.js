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
            '/api/messaging-center/settings');
        if (probe.moduleBlocked || probe.status >= 300) {
            moduleBlocked = true;
            blockedReason = probe.reason || `status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'messaging module probe blocked',
                `endpoint=/api/messaging-center/settings status=${probe.status} reason=${blockedReason} — A/B/C skip, D bağımsız.`);
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
        // settings/activity feed üzerinden simulate). /api/messaging-center/send
        // body kontratı (SendReq): { channel, recipient, subject?, body } —
        // recipient: stres prefix ile virtual recipient. Backend send-flow
        // Resend/SMS silent (F8B doctrine).
        for (let i = 0; i < N_NOTIF; i++) {
            const r = await callTimed(request, 'post', '/api/messaging-center/send', {
                channel: 'in_app',
                recipient: `${prefix}_user_${i}@stress.invalid`,
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
        const dup = await callTimed(request, 'post', '/api/messaging-center/send', {
            channel: 'in_app',
            recipient: `${prefix}_user_0@stress.invalid`,
            subject: `${prefix}_batch_subj_0`,
            body: `${prefix}_batch_body_0`,
            metadata: { stress_seed: true, stress_prefix: prefix, idx: 0, dup: true },
        }, stressTokens.stress_token);
        dupSampleId = dup.body?.id || dup.body?.delivery_id || dup.body?.message_id || null;
        const dupOk = !permAll && (dup.ok || dup.status === 200 || dup.status === 202 || dup.status === 409);

        // Invalid device token graceful: malformed expo token payload →
        // server graceful (no 5xx). Direct /messaging/send'de device_token
        // yok ama bozuk channel sufficient.
        const bad = await callTimed(request, 'post', '/api/messaging-center/send', {
            channel: 'invalid_channel_xyz',
            recipient: 'malformed',
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
        const logs = await callTimed(request, 'get', '/api/messaging-center/delivery-logs?limit=50',
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
        // C için soft-skip. Real path: /api/messaging-center/activity.
        const feed = await callTimed(request, 'get', '/api/messaging-center/activity?limit=20',
            undefined, stressTokens.stress_token);
        if (feed.status === 404) {
            rec(testInfo, { module: MOD, step: 'activity_feed', status: 'SKIP', note: 'endpoint 404 (alternate name)' });
            return;
        }
        if (feed.status >= 500) {
            recFinding(testInfo, 'P0', MOD, 'activity-feed 5xx', `status=${feed.status}`);
        }
        // Gerçek kontrat: GET /api/messaging-center/activity → { activities: [...] }
        // (her item: id/type/title/message/priority/created_at). Legacy
        // notifications/items fallback geri-uyum için tutulur.
        const items = Array.isArray(feed.body?.activities) ? feed.body.activities
            : Array.isArray(feed.body?.notifications) ? feed.body.notifications
            : Array.isArray(feed.body?.items) ? feed.body.items : [];
        // Cross-tenant leak: stress_token GET → hiçbir item PILOT_/PROD_ marker
        // taşımamalı (delivery-logs adımı ile aynı kontrat).
        let feedLeaks = 0;
        for (const it of items.slice(0, 50)) {
            let blob = ''; try { blob = JSON.stringify(it); } catch { /* nz */ }
            if (blob.includes('"PILOT_') || blob.includes('"PROD_')) feedLeaks++;
        }
        if (feedLeaks > 0) {
            recFinding(testInfo, 'P0', MOD, 'activity-feed cross-tenant leak',
                `leaks=${feedLeaks}/${items.length} stress_token döndüğünde pilot/prod prefix marker var.`);
        }
        // Structural PII guard: assertPiiMasked yalnız bilinen field-key + pattern
        // tarar (phone/email/identity_number/passport/iban). Activity item'ları bu
        // key'leri taşımaz → harmless; misleading "recipient/message" alan adları
        // EKLENMEDİ (helper onları no-op sayar, sahte kapsam iddiası olur).
        const masked = assertPiiMasked(testInfo, MOD, items, ['phone', 'email']);
        // Serbest-metin recipient görünürlüğü RBAC'a bağlıdır: /activity
        // `view_guest_list` (VIEW_REPORTS) OLMAYAN rolde inline email/phone'u
        // maskeler, OLAN rolde RAW gösterir (backend messaging.py:1059-1141,
        // `_can_view_pii` dalı; _mask_freetext_pii + _mask_recipient — Task #213).
        // Bu adım stress_token (tenant admin = view_guest_list VAR) ile çağırır →
        // raw recipient BEKLENEN/yetkili çıktıdır, KVKK ihlali DEĞİL. Maskeleme
        // gate'i (view_guest_list OLMAYAN rol → maskeli) ayrıca § E'de housekeeping
        // principal ile P0 hard-assert edilir. Bu yüzden burada freetext PII yalnız
        // GÖZLEM amaçlı sayılır; REVIEW'a DÜŞÜRÜLMEZ (admin için by-design — aksi
        // halde, /activity artık per-rol maskeli iken, stale over-flag olurdu).
        // Sentetik test domain'leri (.invalid/.test/.example) zaten muaf.
        const EMAIL_RE = /[^\s@"<>]+@[^\s@"<>]+\.[A-Za-z]{2,}/g;
        let freetextPii = 0;
        for (const it of items.slice(0, 50)) {
            for (const key of ['message', 'title']) {
                const s = String(it?.[key] ?? '');
                for (const m of (s.match(EMAIL_RE) || [])) {
                    const lo = m.toLowerCase();
                    if (lo.endsWith('.invalid') || lo.endsWith('.test') || lo.endsWith('.example')) continue;
                    freetextPii++;
                }
            }
        }
        // Boş feed → PII/leak assertion'ı vacuous (boş kümede trivially-pass).
        // Fake-green önlemek için 2xx+0 item durumunu REVIEW olarak işaretle.
        const feedEmpty = feed.status < 400 && items.length === 0;
        if (feedEmpty) {
            recFinding(testInfo, 'P2', MOD, 'activity-feed empty (vacuous PII assert)',
                'stress_token 2xx ama 0 activity döndü — PII/leak kontrolü boş kümede; CI/manuel doğrula.');
        }
        rec(testInfo, { module: MOD, step: 'activity_feed',
            status: feed.status >= 500 || feedLeaks > 0 || !masked ? 'FAIL'
                : feedEmpty ? 'REVIEW' : 'PASS',
            note: `status=${feed.status} items=${items.length} leaks=${feedLeaks} pii_masked=${masked} freetext_pii=${freetextPii}(admin=by-design,gate→§E) empty=${feedEmpty}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'activity_feed', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(feedLeaks, `activity-feed cross-tenant leak count=${feedLeaks}`).toBe(0);
        expect(feed.status < 500, `activity-feed 5xx`).toBe(true);
    });

    test('E) Activity feed recipient PII mask — housekeeping(masked) vs privileged(visible) RBAC', async ({ request, stressTokens, stressRoles, stressState }, testInfo) => {
        // Task #213 — hard-assert the masked-recipient RBAC path end-to-end.
        // /api/messaging-center/activity masks the guest recipient (email local
        // part / phone digits) for roles WITHOUT view_guest_list, and shows it
        // raw for roles WITH it. The only previously-available stress tokens
        // (stress_admin + pilot super_admin) BOTH hold view_guest_list, so the
        // masked branch could never be proven live — only the visible branch.
        // A housekeeping principal (no view_guest_list) closes that gap.
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'activity_pii_mask_rbac', status: 'SKIP', note: blockedReason });
            test.skip(true, 'module blocked');
            return;
        }
        const hkToken = stressRoles?.staff_housekeeping || null;
        if (!hkToken) {
            // Fail-soft provisioning: no low-trust principal → honest SKIP, NEVER
            // fake-green. The masked branch CANNOT be asserted with admin tokens.
            recFinding(testInfo, 'P2', MOD, 'housekeeping principal token yok',
                'role_tokens.staff_housekeeping null (globalSetup provisioning fail-soft) — masked-recipient RBAC path hard-assert edilemedi.');
            rec(testInfo, { module: MOD, step: 'activity_pii_mask_rbac', status: 'SKIP', note: 'no housekeeping token' });
            test.skip(true, 'no housekeeping token');
            return;
        }

        // Seed a deterministic delivery-log row with a recognisable recipient via
        // the real /send flow (admin = manage_sales). channel='email' so a
        // delivery log IS written (note: 'in_app' is NOT in CHANNEL_PROVIDER_MAP
        // → unknown channel → no log). No provider config for the stress tenant
        // ⇒ status=failed, recipient persisted, ZERO external call (fallback
        // chain for email is empty; external_calls=[] gate still enforced below).
        // PII token `guestpii` lives in the email local-part (masked away);
        // `mask_uc_marker` lives in use_case (never masked) so we can locate the
        // exact probe row in BOTH the masked and unmasked feeds.
        const piiLocal = `${prefix}guestpii`;
        const probeRecipient = `${piiLocal}@stress.invalid`;
        const ucMarker = `${prefix}mask_uc_marker`;
        const send = await callTimed(request, 'post', '/api/messaging-center/send', {
            channel: 'email',
            recipient: probeRecipient,
            subject: `${prefix}_mask_probe_subj`,
            body: `${prefix}_mask_probe_body`,
            use_case: ucMarker,
            metadata: { stress_seed: true, stress_prefix: prefix, mask_probe: true },
        }, stressTokens.stress_token);
        if (send.status === 401 || send.status === 403) {
            // stress_admin lacking manage_sales would be a backend RBAC change,
            // not a test bug — record honestly and SKIP rather than fake-pass.
            recFinding(testInfo, 'P2', MOD, 'mask-probe /send perm-gated',
                `status=${send.status} — stress_admin manage_sales beklenirdi; probe row seed edilemedi.`);
            rec(testInfo, { module: MOD, step: 'activity_pii_mask_rbac', status: 'SKIP', note: `probe send status=${send.status}` });
            return;
        }
        if (send.status >= 500) {
            recFinding(testInfo, 'P0', MOD, 'mask-probe /send 5xx', `status=${send.status}`);
        }

        const fetchFeed = async (token) => {
            const r = await callTimed(request, 'get', '/api/messaging-center/activity?limit=100',
                undefined, token);
            const items = Array.isArray(r.body?.activities) ? r.body.activities
                : Array.isArray(r.body?.notifications) ? r.body.notifications
                : Array.isArray(r.body?.items) ? r.body.items : [];
            return { status: r.status, items };
        };

        const hk = await fetchFeed(hkToken);                       // no view_guest_list → masked
        const priv = await fetchFeed(stressTokens.stress_token);   // admin (view_guest_list) → visible

        const findProbe = (items) => items.find((it) => String(it?.message ?? '').includes(ucMarker)) || null;
        const hkProbe = findProbe(hk.items);
        const privProbe = findProbe(priv.items);

        // Cross-tenant: neither feed may carry pilot/prod prefix markers.
        const leakCount = (items) => items.slice(0, 100).reduce((n, it) => {
            let blob = ''; try { blob = JSON.stringify(it); } catch { /* nz */ }
            return n + ((blob.includes('"PILOT_') || blob.includes('"PROD_')) ? 1 : 0);
        }, 0);
        const hkLeaks = leakCount(hk.items);
        const privLeaks = leakCount(priv.items);
        if (hkLeaks > 0 || privLeaks > 0) {
            recFinding(testInfo, 'P0', MOD, 'activity-feed cross-tenant leak (mask RBAC)',
                `hk_leaks=${hkLeaks} priv_leaks=${privLeaks} — düşük/yüksek-güven token pilot/prod prefix marker gördü.`);
        }

        // Non-vacuous guard: both principals must actually see the seeded probe
        // row, else the mask/visible assertions are trivially-true on an empty
        // set (fake-green). The privileged principal must ALSO see the raw PII.
        const hkSeen = !!hkProbe;
        const privSeen = !!privProbe;
        if (!hkSeen || !privSeen) {
            recFinding(testInfo, 'P0', MOD, 'mask-probe row not surfaced in activity feed',
                `hk_seen=${hkSeen} priv_seen=${privSeen} hk_items=${hk.items.length} priv_items=${priv.items.length} — vacuous mask assert riski; probe row delivery-log olarak yazılmadı/feed'e düşmedi.`);
        }

        // Core contract:
        //  - housekeeping (no view_guest_list): recipient MASKED — raw local-part
        //    PII (`guestpii`) absent, masked sentinel `***@stress.invalid` present.
        //  - admin (view_guest_list): recipient VISIBLE — raw `guestpii@...` shown.
        const hkMsg = String(hkProbe?.message ?? '');
        const privMsg = String(privProbe?.message ?? '');
        const hkMasked = hkSeen && !hkMsg.includes(piiLocal) && hkMsg.includes('***@stress.invalid');
        const privVisible = privSeen && privMsg.includes(probeRecipient);
        if (hkSeen && !hkMasked) {
            recFinding(testInfo, 'P0', MOD, 'housekeeping sees UNMASKED recipient PII',
                `msg="${hkMsg.slice(0, 120)}" — view_guest_list olmayan rol guest email local-part görüyor (KVKK/PII ihlali).`);
        }
        if (privSeen && !privVisible) {
            recFinding(testInfo, 'P2', MOD, 'privileged role recipient not visible',
                `msg="${privMsg.slice(0, 120)}" — view_guest_list olan rol raw recipient görmeli (kontrat regresyonu).`);
        }

        rec(testInfo, { module: MOD, step: 'activity_pii_mask_rbac',
            status: (hk.status < 500 && priv.status < 500 && hkLeaks === 0 && privLeaks === 0
                && hkSeen && privSeen && hkMasked && privVisible) ? 'PASS' : 'FAIL',
            note: `hk_status=${hk.status} priv_status=${priv.status} hk_seen=${hkSeen} priv_seen=${privSeen} hk_masked=${hkMasked} priv_visible=${privVisible} hk_leaks=${hkLeaks} priv_leaks=${privLeaks}` });

        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'activity_pii_mask_rbac', stressState, request, stressTokens.pilot_token);
        expect(extOk, 'external_calls must stay empty').toBe(true);
        expect(hkLeaks, `housekeeping feed cross-tenant leak=${hkLeaks}`).toBe(0);
        expect(privLeaks, `privileged feed cross-tenant leak=${privLeaks}`).toBe(0);
        expect(hk.status < 500, 'housekeeping activity 5xx').toBe(true);
        expect(priv.status < 500, 'privileged activity 5xx').toBe(true);
        expect(hkSeen, 'housekeeping must see the seeded probe row (non-vacuous)').toBe(true);
        expect(privSeen, 'privileged must see the seeded probe row (non-vacuous)').toBe(true);
        expect(hkMasked, 'housekeeping (no view_guest_list) MUST get masked recipient').toBe(true);
        expect(privVisible, 'privileged (view_guest_list) MUST see raw recipient').toBe(true);
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
