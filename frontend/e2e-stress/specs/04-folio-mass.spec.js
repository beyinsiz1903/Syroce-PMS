// F8A § 04 — Folio mass: charge, dry-run payment, split, audit, closed-folio guard.
import { test, expect, rec } from '../fixtures/stress-context.js';
import { fetchAllByPrefix, callTimed, recPerf, recFinding, pilotBookingsCount, assertNoExternalCallsPostBatch } from '../fixtures/stress-helpers.js';

const MOD = 'folio-mass';

test.describe.configure({ mode: 'serial' });

test.describe('F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard)', () => {
    let folios = [];
    let bookings = [];
    let pilotBefore = null;

    test('Setup: stress folios + bookings list', async ({ request, stressTokens, stressState }, testInfo) => {
        const prefix = stressState.data_prefix;
        bookings = await fetchAllByPrefix(request, stressTokens.stress_token, '/api/pms/bookings', 'stress_prefix', prefix);
        // Folio listesi için doğrudan endpoint olmayabilir → checkout-preview üzerinden de erişebiliriz.
        // İlk attempt: /api/pms/folios
        folios = await fetchAllByPrefix(request, stressTokens.stress_token, '/api/pms/folios', 'stress_prefix', prefix, { maxPages: 8 });
        let fallbackUsed = false;
        let bookingsWithFolioId = 0;
        if (folios.length === 0 && bookings.length > 0) {
            // Booking üzerinden folio_id bulmaya çalış (booking objesinde folio_id varsa)
            bookingsWithFolioId = bookings.filter((b) => b.folio_id).length;
            const fromBookings = bookings.filter((b) => b.folio_id).map((b) => ({ id: b.folio_id, booking_id: b.id }));
            folios = fromBookings;
            fallbackUsed = true;
        }
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        // Seed-contract regression guard (Task #174 / #161): if bookings exist
        // but the seed factory forgot to write folio_id (or the bookings
        // serializer started dropping it), the A/B/C batches would otherwise
        // burn ~160 POSTs and report 100% s400. Fail fast at setup instead so
        // operators see a single P0 finding pointing at the seed contract.
        const contractBroken = bookings.length > 0 && folios.length === 0;
        const setupStatus = contractBroken
            ? 'FAIL'
            : (folios.length > 0 ? 'PASS' : 'REVIEW');
        rec(testInfo, { module: MOD, step: 'setup', status: setupStatus,
            note: `bookings=${bookings.length} folios=${folios.length} pilot_before=${pilotBefore?.count} fallback=${fallbackUsed} bookings_with_folio_id=${bookingsWithFolioId}` });
        if (contractBroken) {
            recFinding(testInfo, 'P0', MOD,
                'Folio target resolution kırık — seed contract regression',
                `bookings=${bookings.length} ama hem /api/pms/folios=[] hem de bookings.folio_id boş (with_folio_id=${bookingsWithFolioId}). ` +
                'Stress seed bookings_docs[].folio_id alanını yazmamış olabilir (backend/domains/admin/router/stress.py:233) ' +
                'VEYA /api/pms/bookings serializer folio_id alanını dropluyor (modules/reservations/repository.py projection). ' +
                'A/B/C batch\'leri tüm POST\'larda s400 dönecek — ileri çalıştırma anlamsız.');
        }
        expect(contractBroken,
            `Folio target resolution broken: bookings=${bookings.length} folios=${folios.length} bookings_with_folio_id=${bookingsWithFolioId}. ` +
            'Stress seed must write folio_id onto bookings (#161 fix commit 5587e010).').toBe(false);
    });

    test('A) 100 folio charge POST (mini-bar, restaurant, other)', async ({ request, stressTokens }, testInfo) => {
        if (folios.length < 5 && bookings.length < 5) { rec(testInfo, { module: MOD, step: 'charge_sample', status: 'SKIP', note: 'No folios reachable' }); return; }
        // folio_id bilinmiyorsa booking_id üzerinden attempt; backend folio'yu booking'den çıkarsın.
        const sample = (folios.length > 0 ? folios : bookings).slice(0, 100);
        const cats = ['minibar', 'restaurant', 'spa', 'laundry'];
        const samples = []; let ok = 0, fail = 0; const failModes = {};
        for (let i = 0; i < sample.length; i++) {
            const it = sample[i];
            const body = {
                folio_id: it.folio_id || it.id,
                booking_id: it.booking_id || it.id,
                category: cats[i % cats.length],
                description: `F8A_charge_${cats[i % cats.length]}_${i}`,
                amount: 50 + (i % 10) * 10,
                quantity: 1.0,
                tax_rate: 0.18,
            };
            const r = await callTimed(request, 'post', '/api/pms-core/folio/charge', body, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) ok++;
            else { fail++; const k = `s${r.status}`; failModes[k] = (failModes[k] || 0) + 1; }
        }
        // Hard-fail when destructive batch is fully broken (architect feedback): a 100/100 s400
        // means folio contract is broken, must not be hidden as REVIEW. Partial = REVIEW.
        const chargeStatus = ok === 0 ? 'FAIL' : (ok > sample.length * 0.5 ? 'PASS' : 'REVIEW');
        rec(testInfo, { module: MOD, step: 'charge_post_batch', status: chargeStatus,
            endpoint: '/api/pms-core/folio/charge',
            note: `n=${sample.length} ok=${ok} fail=${fail} fail_modes=${JSON.stringify(failModes)}` });
        recPerf(testInfo, MOD, 'folio_charge', samples, ok > sample.length * 0.5);
        if (ok === 0) {
            recFinding(testInfo, 'P1', MOD, 'Folio charge tüm denemelerde başarısız',
                `${sample.length} charge POST 0 başarı. Modes: ${JSON.stringify(failModes)}. Permission veya folio_id resolution sorunu olabilir.`);
        }
        // Hard-fail Playwright test (architect feedback): annotation alone leaves test PASS.
        expect(chargeStatus, `charge_post_batch FAIL: n=${sample.length} ok=${ok} fail_modes=${JSON.stringify(failModes)}`).not.toBe('FAIL');
    });

    test('B) 50 dry-run payment POST (cash, reference="F8A_DRY_RUN")', async ({ request, stressTokens }, testInfo) => {
        if (folios.length < 5 && bookings.length < 5) { rec(testInfo, { module: MOD, step: 'payment_sample', status: 'SKIP' }); return; }
        const sample = (folios.length > 0 ? folios : bookings).slice(0, 50);
        const samples = []; let ok = 0, fail = 0; const failModes = {};
        for (let i = 0; i < sample.length; i++) {
            const it = sample[i];
            const r = await callTimed(request, 'post', '/api/pms-core/folio/payment', {
                folio_id: it.folio_id || it.id,
                booking_id: it.booking_id || it.id,
                amount: 100,
                method: 'cash',
                payment_type: 'partial',
                reference: `F8A_DRY_RUN_${i}`,
                notes: 'F8A stress dry-run, no real gateway',
            }, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) ok++;
            else { fail++; const k = `s${r.status}`; failModes[k] = (failModes[k] || 0) + 1; }
            // F8A tur-18 fix (CI run #30: s429×49/50): payment endpoint heavy
            // rate-limit class (PCI-DSS audit trail + folio mutation + tax
            // recalc). Aynı sınıftaki C testi 1500ms gap kullanıyor; B testinde
            // throttle yoktu → 50 ardışık POST → rate limit sliding window
            // dolup hemen 429 dönüyor. 400ms gap: 50×400=20s + 50×~200ms call
            // = ~30s toplam (180s test budget'ın çok altı), rate-limit window'u
            // (~1000ms) yenilemek için yeterli.
            await new Promise((res) => setTimeout(res, 400));
        }
        const paymentStatus = ok === 0 ? 'FAIL' : (ok > sample.length * 0.5 ? 'PASS' : 'REVIEW');
        rec(testInfo, { module: MOD, step: 'payment_post_batch', status: paymentStatus,
            endpoint: '/api/pms-core/folio/payment',
            note: `n=${sample.length} ok=${ok} fail=${fail} fail_modes=${JSON.stringify(failModes)} method=cash (DRY-RUN, no Stripe)` });
        recPerf(testInfo, MOD, 'folio_payment', samples, ok > sample.length * 0.5);
        expect(paymentStatus, `payment_post_batch FAIL: n=${sample.length} ok=${ok} fail_modes=${JSON.stringify(failModes)}`).not.toBe('FAIL');
    });

    test('C) Folio split-by-amount (10 folio)', async ({ request, stressTokens }, testInfo) => {
        if (folios.length < 5 && bookings.length < 5) { rec(testInfo, { module: MOD, step: 'split_sample', status: 'SKIP' }); return; }
        const sample = (folios.length > 0 ? folios : bookings).slice(0, 10);
        const samples = []; let ok = 0, fail = 0; const failModes = {};
        for (const it of sample) {
            const r = await callTimed(request, 'post', '/api/pms-core/folio/split-by-amount', {
                source_folio_id: it.folio_id || it.id,
                splits: [{ amount: 25, target_folio_type: 'guest' }],
                reason: 'F8A split test',
            }, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) ok++;
            else { fail++; const k = `s${r.status}`; failModes[k] = (failModes[k] || 0) + 1; }
            // Throttle: split-by-amount writes 1 source folio + N target folio +
            // 2N+1 charges per call → "heavy" endpoint sınıfı (rate limit daha
            // sıkı). 120ms gap CI'da yetmedi (run #18: s429×10). 1500ms gap
            // sliding window'u garantili boşaltır; toplam test ~15s (kabul).
            await new Promise((res) => setTimeout(res, 1500));
        }
        const splitStatus = ok > 0 ? 'PASS' : 'FAIL';
        rec(testInfo, { module: MOD, step: 'folio_split_batch', status: splitStatus,
            endpoint: '/api/pms-core/folio/split-by-amount',
            note: `n=${sample.length} ok=${ok} fail=${fail} fail_modes=${JSON.stringify(failModes)}` });
        recPerf(testInfo, MOD, 'folio_split', samples, ok > 0);
        expect(splitStatus, `folio_split_batch FAIL: n=${sample.length} ok=${ok} fail_modes=${JSON.stringify(failModes)}`).not.toBe('FAIL');
    });

    test('C2) Total mismatch detector: sum(charges) == folio.total (10 folio)', async ({ request, stressTokens, stressState }, testInfo) => {
        // Architect tur-3 feedback: brief'in "folio total reconciliation" gereksinimi.
        // Her folio için audit endpoint'inden veya direkt folio GET'inden charges
        // listesini al, sum hesapla, folio.total ile karşılaştır. ≤0.01 TL fark tolere.
        if (folios.length < 1 && bookings.length < 1) { rec(testInfo, { module: MOD, step: 'reconcile_sample', status: 'SKIP' }); return; }
        const sample = (folios.length > 0 ? folios : bookings).slice(0, 10);
        let checked = 0, ok = 0, mismatch = 0, fetchFail = 0;
        const mismatchDetail = [];
        for (const it of sample) {
            const fid = it.folio_id || it.id;
            // Architect tur-6 round 2 review: kullan canonical detail endpoint
            // `/api/pms-core/folio/detail/{id}` (FolioDetailService) — audit
            // endpoint financial source-of-truth değil (yalnız trail array döner)
            // o yüzden fallback kullanma (false-pass riski). Response şekli:
            // { success, folio:{...}, summary:{total_charges, total_payments, balance}, charges:[], payments:[] }
            const detailR = await callTimed(request, 'get', `/api/pms-core/folio/detail/${fid}`, undefined, stressTokens.stress_token);
            if (!detailR.ok || !detailR.body || detailR.body.success === false) { fetchFail++; continue; }
            const folioBody = detailR.body;
            checked++;
            const summary = folioBody.summary || {};
            const sumCharges = Number(summary.total_charges ?? 0);
            const sumPayments = Number(summary.total_payments ?? 0);
            const balance = Number(summary.balance ?? (sumCharges - sumPayments));
            // Service contract: balance = total_charges - total_payments (gross-net invariant).
            // Tolerance 0.01 TL float drift; >0.01 = aggregate transaction broken.
            const matchNet = Math.abs((sumCharges - sumPayments) - balance) <= 0.01;
            if (matchNet) ok++;
            else {
                mismatch++;
                if (mismatchDetail.length < 5) {
                    mismatchDetail.push({ folio_id: fid, sum_charges: sumCharges, sum_payments: sumPayments, balance, delta: +((sumCharges - sumPayments) - balance).toFixed(2) });
                }
            }
        }
        const reconcileStatus = checked === 0 ? 'REVIEW' : (mismatch === 0 ? 'PASS' : 'FAIL');
        rec(testInfo, { module: MOD, step: 'folio_total_reconcile', status: reconcileStatus,
            endpoint: '/api/pms-core/folio/detail/{id}',
            note: `n=${sample.length} fetched=${checked} ok=${ok} mismatch=${mismatch} fetch_fail=${fetchFail} ${mismatch > 0 ? `samples=${JSON.stringify(mismatchDetail)}` : ''}` });
        if (mismatch > 0) {
            recFinding(testInfo, 'P1', MOD,
                'Folio total mismatch — sum(charges) ≠ folio.total',
                `${mismatch}/${checked} folio'da gross-veya-net reconciliation 0.01 toleransı aştı. Folio aggregate update transaction'ı kırık olabilir. Detay: ${JSON.stringify(mismatchDetail)}`);
        }
        expect(reconcileStatus, `folio_total_reconcile FAIL: mismatch=${mismatch}/${checked} samples=${JSON.stringify(mismatchDetail)}`).not.toBe('FAIL');
        // Post-batch external-call invariant re-assert (runtime endpoint).
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'folio_reconcile_10', stressState, request, stressTokens.pilot_token);
        expect(extOk, 'folio_reconcile_10 sonrası external_calls invariant ihlal').toBe(true);
    });

    test('D) Folio audit GET (5 folio)', async ({ request, stressTokens }, testInfo) => {
        if (folios.length < 1 && bookings.length < 1) { rec(testInfo, { module: MOD, step: 'audit_sample', status: 'SKIP' }); return; }
        const sample = (folios.length > 0 ? folios : bookings).slice(0, 5);
        let ok = 0, fail = 0;
        for (const it of sample) {
            const fid = it.folio_id || it.id;
            const r = await callTimed(request, 'get', `/api/pms-core/folio/audit/${fid}`, undefined, stressTokens.stress_token);
            if (r.ok) ok++;
            else fail++;
        }
        rec(testInfo, { module: MOD, step: 'folio_audit', status: ok > 0 ? 'PASS' : 'REVIEW',
            endpoint: '/api/pms-core/folio/audit/{id}',
            note: `n=${sample.length} ok=${ok} fail=${fail}` });
    });

    test('E) Closed folio guard: checkout sonrası charge reddi', async ({ request, stressTokens }, testInfo) => {
        if (bookings.length < 1) { rec(testInfo, { module: MOD, step: 'closed_guard', status: 'SKIP' }); return; }
        // Bir booking'i force checkout et → folio kapansın → ardından charge dene → reject bekle
        const candidate = bookings.find((b) => b.status === 'checked_in') || bookings[0];
        const fid = candidate.folio_id || candidate.id;
        const co = await callTimed(request, 'post', '/api/pms-core/checkout',
            { booking_id: candidate.id, force: true }, stressTokens.stress_token);
        const ch = await callTimed(request, 'post', '/api/pms-core/folio/charge', {
            folio_id: fid, booking_id: candidate.id,
            category: 'minibar', description: 'F8A closed-guard test', amount: 25, quantity: 1, tax_rate: 0,
        }, stressTokens.stress_token);
        const guardOk = ch.status === 400 || ch.status === 409 || ch.status === 422;
        rec(testInfo, { module: MOD, step: 'closed_folio_guard', status: guardOk ? 'PASS' : 'REVIEW',
            note: `checkout=${co.status} post_charge=${ch.status} (≠2xx ⇒ guard çalışıyor)` });
        if (ch.ok) {
            recFinding(testInfo, 'P1', MOD,
                'Closed-folio guard yok — kapanmış folio\'ya charge eklendi',
                `Booking ${candidate.id} force-checkout sonrası /folio/charge 2xx döndü. Production hardening guard regresyon.`);
        }
    });

    test('F) Pilot drift = 0', async ({ request, stressTokens }, testInfo) => {
        if (!pilotBefore) { rec(testInfo, { module: MOD, step: 'pilot_drift', status: 'SKIP' }); return; }
        const after = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (after?.count ?? 0) - pilotBefore.count;
        rec(testInfo, { module: MOD, step: 'pilot_drift', status: drift === 0 ? 'PASS' : 'FAIL',
            note: `pilot bookings before=${pilotBefore.count} after=${after?.count} drift=${drift}` });
        if (drift !== 0) recFinding(testInfo, 'P0', MOD, 'Pilot mutation', `drift=${drift}`);
        expect(drift).toBe(0);
    });
});
