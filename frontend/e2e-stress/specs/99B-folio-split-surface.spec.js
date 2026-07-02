// ─────────────────────────────────────────────────────────────────────────
// F9E § 99B — Folio Split (Fatura Ayrıştırma) Surface Deep Stress.
// ─────────────────────────────────────────────────────────────────────────
//
// Otel kullanım senaryosu: misafir check-out'ta "oda ücretini şirket ödesin,
// minibar/ekstraları ben ödeyeyim" der → resepsiyon folio'yu ayrıştırır.
// İki yol: (1) belirli charge'ları yeni folio'ya taşı (by charge_ids),
// (2) tutar bazlı böl (company X TL, guest kalan). Çift tıklama / yavaş ağ
// yüzünden aynı bölme iki kez gönderilirse HAYALET FOLIO oluşmamalı
// (X-Idempotency-Key sözleşmesi). Cross-tenant: bir otelin personeli başka
// otelin folio'sunu ASLA bölememeli.
//
// Backend yüzey (backend/routers/pms_hardening.py, prefix /api/pms-core):
//   POST /api/pms-core/folio/split
//        body {source_folio_id, charge_ids:[], target_folio_type:'guest', reason}
//        RBAC split_folio; X-Idempotency-Key scope `folio_split:{source}`.
//        Servis dönüşü: {success, new_folio:{id,...}, transferred_charges, ...}
//        (folio_hardening_service.split_folio:263).
//   POST /api/pms-core/folio/split-by-amount
//        body {source_folio_id, splits:[{amount, target_folio_type}], reason}
//        X-Idempotency-Key scope `folio_split_by_amount:{source}`.
//        Servis dönüşü: {success, new_folios:[...], ...} (split_folio_by_amounts:403).
//   Seed yardımcı: POST /api/folio/{id}/charge (finance/folio.py) → bölünecek charge.
//
// Senaryolar:
//   A) Split by charge_ids: seed charge'ı yeni folio'ya taşı → 2xx + new_folio.id readback.
//   B) Split-by-amount: tutar bazlı bölme (guest hedef) → 2xx/4xx + readback.
//   C) Idempotency replay: aynı X-Idempotency-Key cift-tap → hayalet folio YOK.
//      Manuel nested-ID replay (new_folio.id / new_folios[0].id çıkarımı; generic
//      assertIdempotentReplay nested id'yi göremediği için kullanılmaz). Her iki
//      çağrı 5xx-yasak hard-gate; kanıtlanmış distinct folio = P1 FAIL; same-id /
//      replay flag / 409-422 = PASS; kimlik çıkarılamazsa REVIEW (PASS DEĞİL).
//   D) IDOR: stress_token PILOT folio'yu bölmeye çalışır → 4xx zorunlu.
//      2xx = P0 cross-tenant finansal ihlal.
//   E) Anonymous (header'sız) split → 401/403. Public finansal mutasyon = P1.
//   F) Bogus folio id (var olmayan UUID) split → 4xx (5xx YOK, leak YOK).
//   G) Final invariants: pilot_drift=0 + external_calls=[].
//
// Mutlak kurallar (F9 doctrine):
//   - external_calls = []  (assertNoExternalCallsPostBatch after batch)
//   - pilot mutation = 0   (assertPilotDriftZero)
//   - P0 = P1 = 0; 5xx = 0; skip-as-pass YOK
//   - Module-blocked (RBAC split_folio yok / open folio yok) → A/B/C SKIP + P2;
//     D/E/F (security) bağımsız çalışır.
//   - Mutasyon SADECE stress-tenant; pilot tarafı read-only harvest.
//
// Reporter satırı: `folio_split`.
// ─────────────────────────────────────────────────────────────────────────

import { randomUUID as cryptoRandomUUID } from 'node:crypto';
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'folio_split';
const SUB_PREFIX = 'F9E_SPLIT';
const GAP_MS = 1200;

const SPLIT_PATH = '/api/pms-core/folio/split';
const SPLIT_BY_AMOUNT_PATH = '/api/pms-core/folio/split-by-amount';

test.describe.configure({ mode: 'serial' });

test.describe('F9E § 99B — Folio Split (Fatura Ayrıştırma) Surface', () => {
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let pilotBaseline = null;

    let stressFolioId = null;      // bölünecek kaynak folio (stress tenant, open)
    let seededChargeId = null;     // A için seed edilmiş charge
    let pilotFolioId = null;       // D IDOR (read-only harvest)

    function idemKey(op, i = 0) {
        return `${SUB_PREFIX}_${op}_${Date.now()}_${i}_${cryptoRandomUUID()}`;
    }
    function taggedReason(label) {
        return `${prefix}_${SUB_PREFIX}_${label}`;
    }
    async function gap(ms = GAP_MS) {
        await new Promise((r) => setTimeout(r, ms));
    }
    function extractNewFolioId(body) {
        if (!body || typeof body !== 'object') return null;
        if (body.new_folio?.id) return body.new_folio.id;
        if (Array.isArray(body.new_folios) && body.new_folios[0]?.id) return body.new_folios[0].id;
        if (body.id) return body.id;
        return null;
    }

    // ──────────────────────────────────────────────────────────────
    test('Setup: open folio harvest + seed charge + pilot baseline + pilot folio harvest', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        expect(prefix, 'stressState.data_prefix yok').toBeTruthy();

        if (stressTokens.pilot_token) {
            const snap = await pilotBookingsCount(request, stressTokens.pilot_token);
            pilotBaseline = (snap?.count != null && !snap.unreachable) ? snap.count : null;
        }
        rec(testInfo, { module: MOD, step: 'setup_pilot_baseline', status: 'PASS', note: `pilot_baseline=${pilotBaseline}` });

        // Module probe — GET /api/folio/list?status=open. Non-2xx → A/B/C SKIP.
        const probe = await callTimed(
            request, 'get', '/api/folio/list?status=open&limit=50', null,
            stressTokens.stress_token, { timeout: 15_000 },
        );
        if (probe.status !== 200) {
            moduleBlocked = true;
            blockedReason = `folio_list_probe http=${probe.status}`;
            recFinding(testInfo, 'P2', MOD,
                `Folio split module blocked (http=${probe.status})`,
                `stress_token finance reach yok — A/B/C SKIP, D/E/F bağımsız.`);
            rec(testInfo, { module: MOD, step: 'setup_module_probe', status: 'REVIEW', http: probe.status, note: blockedReason });
        } else {
            rec(testInfo, { module: MOD, step: 'setup_module_probe', status: 'PASS', http: 200 });
        }

        // Open folio harvest (status=open filtre garanti açık folio döndürür).
        if (!moduleBlocked) {
            const items = probe.body?.folios || probe.body?.items || (Array.isArray(probe.body) ? probe.body : []);
            const openFolio = items.find((f) => (f.status || 'open') === 'open' && f.id) || null;
            if (openFolio?.id) {
                stressFolioId = openFolio.id;
                rec(testInfo, { module: MOD, step: 'setup_harvest_stress_folio', status: 'PASS', note: `folio_id=${stressFolioId}` });
            } else {
                rec(testInfo, { module: MOD, step: 'setup_harvest_stress_folio', status: 'REVIEW', note: 'no open folio — A/B/C will SKIP' });
            }
        }

        // Seed a charge on the source folio so A) has a concrete charge_id to move.
        // /api/folio/{id}/charge (ChargeCreate: charge_category enum, amount>0).
        if (stressFolioId) {
            const seedR = await callTimed(
                request, 'post', `/api/folio/${stressFolioId}/charge`,
                { charge_category: 'other', description: taggedReason('seed_charge'), amount: 50.0, quantity: 1, vat_rate: 0 },
                stressTokens.stress_token,
                { timeout: 15_000, headers: { 'X-Idempotency-Key': idemKey('seed_charge') } },
            );
            if (seedR.status === 200 || seedR.status === 201) {
                seededChargeId = seedR.body?.id || seedR.body?.charge_id || null;
                rec(testInfo, { module: MOD, step: 'setup_seed_charge', status: 'PASS', http: seedR.status, note: `charge_id=${seededChargeId}` });
            } else {
                rec(testInfo, { module: MOD, step: 'setup_seed_charge', status: 'REVIEW', http: seedR.status, note: 'seed charge başarısız — A by charge_ids SKIP olabilir' });
            }
        }

        // Pilot folio harvest (D IDOR, read-only).
        if (stressTokens.pilot_token) {
            const pr = await callTimed(
                request, 'get', '/api/folio/list?limit=50', null,
                stressTokens.pilot_token, { timeout: 15_000 },
            );
            if (pr.status === 200) {
                const pItems = pr.body?.folios || pr.body?.items || (Array.isArray(pr.body) ? pr.body : []);
                const pf = pItems.find((f) => f.id) || null;
                if (pf?.id) {
                    pilotFolioId = pf.id;
                    rec(testInfo, { module: MOD, step: 'setup_harvest_pilot_folio', status: 'PASS', note: `pilot_folio_id=${String(pilotFolioId).slice(0, 8)}…` });
                } else {
                    rec(testInfo, { module: MOD, step: 'setup_harvest_pilot_folio', status: 'REVIEW', note: 'pilot folio empty — D uses bogus uuid' });
                }
            } else {
                rec(testInfo, { module: MOD, step: 'setup_harvest_pilot_folio', status: 'REVIEW', http: pr.status, note: 'pilot folio non-200 — D uses bogus uuid' });
            }
        }
    });

    // ──────────────────────────────────────────────────────────────
    // A) Split by charge_ids — seed charge'ı yeni folio'ya taşı.
    test('A) POST /folio/split (by charge_ids)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked || !stressFolioId || !seededChargeId) {
            const reason = moduleBlocked ? blockedReason : (!stressFolioId ? 'no_stress_folio' : 'no_seeded_charge');
            rec(testInfo, { module: MOD, step: 'A_split_by_charges', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const payload = {
            source_folio_id: stressFolioId,
            charge_ids: [seededChargeId],
            target_folio_type: 'company',
            reason: taggedReason('A_by_charges'),
        };
        const r = await callTimed(
            request, 'post', SPLIT_PATH, payload, stressTokens.stress_token,
            { timeout: 20_000, headers: { 'X-Idempotency-Key': idemKey('A_split') } },
        );
        recPerf(testInfo, MOD, 'A_split_by_charges', [r.ms], r.status === 200 || r.status === 201);
        expect(r.status, `A_split 5xx=${r.status}`).toBeLessThan(500);
        const okStatuses = [200, 201, 400, 403, 404, 409, 422];
        expect(okStatuses, `A_split unexpected=${r.status}`).toContain(r.status);

        if (r.status === 200 || r.status === 201) {
            const newFolioId = extractNewFolioId(r.body);
            // Başarı ise yeni folio gerçekten okunabilir olmalı (hayalet değil).
            if (newFolioId) {
                const detail = await callTimed(
                    request, 'get', `/api/folio/${newFolioId}`, null,
                    stressTokens.stress_token, { timeout: 15_000 },
                );
                rec(testInfo, {
                    module: MOD, step: 'A_split_by_charges', status: detail.status === 200 ? 'PASS' : 'REVIEW',
                    http: r.status, note: `new_folio_id=${newFolioId} readback_http=${detail.status} transferred=${r.body?.transferred_charges}`,
                });
            } else {
                rec(testInfo, { module: MOD, step: 'A_split_by_charges', status: 'REVIEW', http: r.status, note: 'split 2xx ama new_folio id yok' });
            }
        } else {
            // 4xx: RBAC (split_folio) / charge eligibility / folio durum — by-design olabilir.
            recFinding(testInfo, 'P2', MOD,
                `folio/split non-2xx status=${r.status}`,
                `source=${stressFolioId} body=${JSON.stringify(r.body || {}).slice(0, 200)} — RBAC/eligibility; C idempotency yine de çalışır.`);
            rec(testInfo, { module: MOD, step: 'A_split_by_charges', status: 'REVIEW', http: r.status });
        }
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // B) Split-by-amount — tutar bazlı bölme.
    test('B) POST /folio/split-by-amount', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked || !stressFolioId) {
            const reason = moduleBlocked ? blockedReason : 'no_stress_folio';
            rec(testInfo, { module: MOD, step: 'B_split_by_amount', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        // Küçük tutar — kaynak bakiyesinden az olmalı (servis: en az bir miktar
        // kalmalı, aksi 400). 1.0 TL güvenli alt sınır.
        const payload = {
            source_folio_id: stressFolioId,
            splits: [{ amount: 1.0, target_folio_type: 'guest' }],
            reason: taggedReason('B_by_amount'),
        };
        const r = await callTimed(
            request, 'post', SPLIT_BY_AMOUNT_PATH, payload, stressTokens.stress_token,
            { timeout: 20_000, headers: { 'X-Idempotency-Key': idemKey('B_split_amount') } },
        );
        recPerf(testInfo, MOD, 'B_split_by_amount', [r.ms], r.status === 200 || r.status === 201);
        expect(r.status, `B_split_amount 5xx=${r.status}`).toBeLessThan(500);
        const okStatuses = [200, 201, 400, 403, 404, 409, 422];
        expect(okStatuses, `B_split_amount unexpected=${r.status}`).toContain(r.status);

        if (r.status === 200 || r.status === 201) {
            const newFolioId = extractNewFolioId(r.body);
            rec(testInfo, {
                module: MOD, step: 'B_split_by_amount', status: 'PASS', http: r.status,
                note: `new_folio_id=${newFolioId} (amount-based)`,
            });
        } else {
            // 400 (bakiye yetersiz / tutar büyük) by-design — REVIEW.
            recFinding(testInfo, 'P2', MOD,
                `folio/split-by-amount non-2xx status=${r.status}`,
                `source=${stressFolioId} body=${JSON.stringify(r.body || {}).slice(0, 200)} — bakiye/RBAC/eligibility.`);
            rec(testInfo, { module: MOD, step: 'B_split_by_amount', status: 'REVIEW', http: r.status });
        }
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // C) Idempotency replay — aynı key cift-tap, hayalet folio YOK.
    test('C) Idempotency replay (folio/split-by-amount) — no ghost folio', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked || !stressFolioId) {
            const reason = moduleBlocked ? blockedReason : 'no_stress_folio';
            rec(testInfo, { module: MOD, step: 'C_idem_replay', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        // Generic assertIdempotentReplay helper'ı NESTED new_folio.id /
        // new_folios[0].id çıkaramaz (yalnız top-level / data.* bakar) — folio
        // split cevabı nested olduğu için manuel replay yapıyoruz: aynı küçük
        // tutar + AYNI X-Idempotency-Key ile iki kez gönder → ikinci çağrı YENİ
        // folio üretmemeli (hayalet folio = P1 finansal çift-yazım).
        const payload = {
            source_folio_id: stressFolioId,
            splits: [{ amount: 1.0, target_folio_type: 'guest' }],
            reason: taggedReason('C_replay'),
        };
        const xKey = idemKey('C_replay_xidem');
        const callOpts = { timeout: 20_000, headers: { 'X-Idempotency-Key': xKey } };
        const first = await callTimed(request, 'post', SPLIT_BY_AMOUNT_PATH, payload, stressTokens.stress_token, callOpts);
        const second = await callTimed(request, 'post', SPLIT_BY_AMOUNT_PATH, payload, stressTokens.stress_token, callOpts);

        // HARD gate: idempotency path'inde her iki çağrı da 5xx döndürmemeli
        // (replay çağrısında backend kırılımı suite'i yeşil bırakmaz; 5xx=0 doktrini).
        expect(first.status, `C_idem first 5xx=${first.status}`).toBeLessThan(500);
        expect(second.status, `C_idem replay 5xx=${second.status}`).toBeLessThan(500);

        const firstOk = first.status >= 200 && first.status < 300;
        const secondOk = second.status >= 200 && second.status < 300;
        const firstFid = extractNewFolioId(first.body);
        const secondFid = extractNewFolioId(second.body);
        const replayFlag = !!(second.body && (second.body.idempotent_replay || second.body.replayed || second.body.is_replay || second.body.duplicate));
        const conflictStyle = !secondOk && (second.status === 409 || second.status === 422);

        let status;
        let note;
        if (!firstOk) {
            // Precondition: ilk bölme başarısız (bakiye/RBAC) → sözleşme doğrulanamaz.
            status = 'REVIEW';
            note = `first_call_not_2xx=${first.status} — idempotency unverifiable (precondition)`;
        } else if (firstFid != null && secondFid != null && firstFid !== secondFid) {
            // İKİ FARKLI yeni folio = hayalet folio = idempotency ihlali.
            status = 'FAIL';
            note = `distinct_new_folio first=${firstFid} second=${secondFid} — duplicate folio (ghost)`;
            recFinding(testInfo, 'P1', MOD,
                'Folio split idempotency ihlali — aynı X-Idempotency-Key iki farklı folio üretti',
                `xkey=${xKey} first_folio=${firstFid} second_folio=${secondFid}. Finansal çift-yazım/hayalet folio.`);
        } else if (secondOk && firstFid != null && secondFid != null && firstFid === secondFid) {
            status = 'PASS';
            note = `replay same new_folio=${secondFid}`;
        } else if (replayFlag) {
            status = 'PASS';
            note = `replay flag=true second=${second.status}`;
        } else if (conflictStyle) {
            status = 'PASS';
            note = `conflict-style idempotency second=${second.status} (yeni folio reddedildi)`;
        } else {
            // Kimlik çıkarılamadı / belirsiz → PASS DEĞİL → REVIEW (skip-as-pass YOK).
            status = 'REVIEW';
            note = `unverifiable first=${first.status}/${firstFid} second=${second.status}/${secondFid} — replay kanıtlanamadı`;
        }
        rec(testInfo, { module: MOD, step: 'C_idem_replay', status, note });
        // HARD gate: yalnız KANITLANMIŞ duplicate (distinct folio) fail eder.
        const duplicateGhost = firstOk && firstFid != null && secondFid != null && firstFid !== secondFid;
        expect(duplicateGhost, 'folio split idempotency replay duplicate (ghost) folio üretti').toBe(false);
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // D) IDOR cross-tenant — stress_token PILOT folio split → 4xx.
    test('D) Cross-tenant: stress_token split pilot folio → 4xx', async ({ request, stressTokens }, testInfo) => {
        // Bogus UUID ek bir sanity probe — ASLA tek başına IDOR kanıtı değil.
        // Gerçek cross-tenant denemesi yalnız harvest edilmiş PILOT folio ile yapılır.
        const bogusId = '00000000-0000-4000-8000-000000000001';
        const bogusR = await callTimed(
            request, 'post', SPLIT_BY_AMOUNT_PATH,
            { source_folio_id: bogusId, splits: [{ amount: 1.0, target_folio_type: 'guest' }], reason: taggedReason('D_bogus') },
            stressTokens.stress_token, { timeout: 20_000, headers: { 'X-Idempotency-Key': idemKey('D_bogus') } },
        );
        expect(bogusR.status, `D_bogus 5xx=${bogusR.status}`).toBeLessThan(500);
        const bogusBreach = bogusR.status >= 200 && bogusR.status < 300;
        if (bogusBreach) {
            recFinding(testInfo, 'P1', MOD,
                'Folio split var olmayan folio için 2xx döndü',
                `bogus=${bogusId} status=${bogusR.status} — var olmayan kaynak üzerinde bölme başarılı görünüyor.`);
        }
        rec(testInfo, { module: MOD, step: 'D_bogus_probe', status: bogusBreach ? 'FAIL' : 'PASS', http: bogusR.status, note: 'bogus uuid sanity probe' });
        expect(bogusBreach, `bogus folio split unexpected 2xx=${bogusR.status}`).toBe(false);

        // Gerçek IDOR: pilot folio harvest edilemediyse PASS VERME → SKIP+P2 REVIEW.
        if (!pilotFolioId) {
            recFinding(testInfo, 'P2', MOD,
                'Cross-tenant folio split gerçek kanıtı yapılamadı (pilot folio harvest edilemedi)',
                'Pilot folio erişilemediği için gerçek cross-tenant denemesi atlandı; sadece bogus probe çalıştı.');
            rec(testInfo, { module: MOD, step: 'D_cross_tenant_split', status: 'SKIP', note: 'no_pilot_folio — real IDOR unverifiable' });
            test.skip(true, 'pilot folio not harvested — real cross-tenant attempt unverifiable');
        }

        const payload = {
            source_folio_id: pilotFolioId,
            splits: [{ amount: 1.0, target_folio_type: 'guest' }],
            reason: taggedReason('D_idor'),
        };
        const r = await callTimed(
            request, 'post', SPLIT_BY_AMOUNT_PATH, payload, stressTokens.stress_token,
            { timeout: 20_000, headers: { 'X-Idempotency-Key': idemKey('D_idor') } },
        );
        expect(r.status, `D_idor 5xx=${r.status}`).toBeLessThan(500);
        // Servis source folio'yu {id, tenant_id} ile arar → pilot folio stress
        // tenant'ta yok → "Source folio not found" → 4xx. 2xx = breach.
        const breach = r.status >= 200 && r.status < 300;
        if (breach) {
            recFinding(testInfo, 'P0', MOD,
                'Cross-tenant folio split — stress_token pilot folio\'yu böldü',
                `target=${pilotFolioId} status=${r.status} body=${JSON.stringify(r.body || {}).slice(0, 200)}. Finansal tenant izolasyon ihlali.`);
        }
        rec(testInfo, {
            module: MOD, step: 'D_cross_tenant_split',
            status: breach ? 'FAIL' : 'PASS', http: r.status,
            note: 'target=pilot_folio expected≥400',
        });
        expect(breach, `cross-tenant folio split breach status=${r.status}`).toBe(false);
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // E) Anonymous split — 401/403.
    test('E) Anonymous (no token) split → 401/403', async ({ request }, testInfo) => {
        const r = await request.post(SPLIT_BY_AMOUNT_PATH, {
            headers: { 'Content-Type': 'application/json' },
            data: { source_folio_id: '00000000-0000-4000-8000-000000000002', splits: [{ amount: 1.0, target_folio_type: 'guest' }], reason: 'anon' },
            failOnStatusCode: false, timeout: 15_000,
        }).catch(() => null);
        const status = r?.status?.() ?? 0;
        expect(status, `E_anon 5xx=${status}`).toBeLessThan(500);
        const blocked = status === 401 || status === 403 || status === 429;
        if (!blocked) {
            recFinding(testInfo, 'P1', MOD,
                `Anonymous folio split bloklanmadı status=${status}`,
                `Public finansal mutasyon yüzeyi — 401/403 bekleniyordu.`);
        }
        rec(testInfo, {
            module: MOD, step: 'E_anonymous_split',
            status: blocked ? 'PASS' : 'FAIL', http: status, note: 'expected 401/403',
        });
        expect(blocked, `anonymous folio split not blocked status=${status}`).toBe(true);
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // F) Bogus folio id split → 4xx (no 5xx, no leak).
    test('F) Bogus folio id split → 4xx (no 5xx)', async ({ request, stressTokens }, testInfo) => {
        const bogusId = `${SUB_PREFIX}-bogus-${cryptoRandomUUID()}`;
        const r = await callTimed(
            request, 'post', SPLIT_BY_AMOUNT_PATH,
            { source_folio_id: bogusId, splits: [{ amount: 1.0, target_folio_type: 'guest' }], reason: taggedReason('F_bogus') },
            stressTokens.stress_token, { timeout: 15_000, headers: { 'X-Idempotency-Key': idemKey('F_bogus') } },
        );
        expect(r.status, `F_bogus 5xx=${r.status}`).toBeLessThan(500);
        const ok4xx = r.status >= 400 && r.status < 500;
        if (!ok4xx) {
            recFinding(testInfo, 'P1', MOD,
                'Bogus folio id split 4xx döndürmedi',
                `bogus=${bogusId} status=${r.status} — var olmayan kaynak üzerinde mutasyon reddedilmedi.`);
        }
        rec(testInfo, {
            module: MOD, step: 'F_bogus_folio',
            status: ok4xx ? 'PASS' : 'FAIL', http: r.status, note: 'expected 4xx no 5xx',
        });
        // HARD gate: var olmayan folio bölme denemesi 4xx ile reddedilmeli.
        expect(ok4xx, `bogus folio split expected 4xx got ${r.status}`).toBe(true);
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // G) Final invariants — pilot drift = 0 + external_calls = [].
    test('G) Final invariants (pilot_drift=0 + external_calls=[])', async ({ request, stressTokens, stressState }, testInfo) => {
        const driftOk = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBaseline);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'final', stressState, request, stressTokens.pilot_token);
        rec(testInfo, {
            module: MOD, step: 'final_invariants',
            status: driftOk && extOk ? 'PASS' : 'FAIL',
            note: `pilot_drift_zero=${driftOk} external_calls_empty=${extOk}`,
        });
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
    });
});
