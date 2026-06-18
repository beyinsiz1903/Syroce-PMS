/**
 * k6 Load Test - POS / F&B PRIMARY load target
 * ============================================================================
 * Otel POS F&B'yi BIRINCIL yuk hedefi olarak surer: gercek ogle/aksam servisi
 * profili = okuma karisimi + siparis yasam dongusu (create -> close/odeme) +
 * acik adisyon (open-tab) cekismesi. Yeni eklenen POS index'lerini yuk altinda
 * dogrular:
 *   pos_orders        (tenant_id,status,created_at)  -> active-orders panosu
 *                     (tenant_id,created_at)         -> dashboard/rapor range
 *                     (tenant_id,id)                 -> close_order lookup kaynak
 *   pos_transactions  (tenant_id,id)                 -> islem lookup
 *                     (tenant_id,order_id)           -> close_order txn lookup
 *                     (tenant_id,outlet_id,table_number) PARTIAL {status:open}
 *                                                    -> open_tab dup guard
 *
 * DOKTRIN (mutlak):
 *   - SADECE stress tenant'ina yazar (E2E_STRESS_ADMIN + E2E_STRESS_TENANT_ID).
 *     demo@hotel.com / pilot tenant'a ASLA yazma yapilmaz (pilot_drift=0).
 *   - Tum yazmalar POS_LOAD_PREFIX'i guest_name + table_number + idempotency_key
 *     alanlarina basar; kosu sonrasi backend prefix-scoped cleanup endpoint'i
 *     (POST /api/admin/stress/pos-load-cleanup) bu tek kosunun kalintisini siler.
 *   - post_to_folio=false: folyo/Xchange yan-etkisi ve dis cagri tetiklenmez.
 *   - Sentetik PII (gercek misafir verisi yok).
 *   - Bu testi AGENT calistirmaz; operator deploy'a karsi dispatch eder.
 *     Dispatch + cleanup komutlari icin: load_tests/README.md
 *
 * Dispatch (ozet):
 *   k6 run \
 *     -e BASE_URL=https://<deploy> \
 *     -e E2E_STRESS_ADMIN_EMAIL=<secret> \
 *     -e E2E_STRESS_ADMIN_PASSWORD=<secret> \
 *     -e E2E_STRESS_TENANT_ID=<stress_tid> \
 *     -e POS_LOAD_PREFIX=POSLOAD_$(date +%Y%m%d%H%M%S)_ \
 *     load_tests/pos_fnb_burst.js
 */
import http from 'k6/http';
import { check, fail } from 'k6';
import { Trend, Counter, Rate } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL;

// ── Custom metrikler ────────────────────────────────────────────────────────
// Latency'ler cagri tipine gore AYRI izlenir; esikler tipe ozeldir.
const readLatency = new Trend('pos_read_latency_ms');
const createLatency = new Trend('pos_create_latency_ms');
const closeLatency = new Trend('pos_close_latency_ms');
const tabLatency = new Trend('pos_tab_latency_ms');
// pos_unexpected_errors = ASIL kalite kapisi: 5xx VEYA beklenmeyen 4xx.
// Beklenen contention (409) ve throttle (429) bu orana KARISTIRILMAZ; ayri
// sayaclarda gozlemlenir, yoksa gercek hata sinyali maskelenir.
const posUnexpected = new Rate('pos_unexpected_errors');
const tabConflict = new Counter('pos_tab_conflict_409');
const throttle429 = new Counter('pos_throttle_429');

export const options = {
    scenarios: {
        // Birincil OKUMA yuku: index'li okuma yollarini surer.
        read_mix: {
            executor: 'ramping-arrival-rate',
            exec: 'readMix',
            startRate: 5,
            timeUnit: '1s',
            preAllocatedVUs: 60,
            maxVUs: 200,
            stages: [
                { duration: '1m', target: 25 },   // isinma
                { duration: '5m', target: 25 },   // surekli ogle yogunlugu
                { duration: '2m', target: 60 },   // peak ramp
                { duration: '30s', target: 100 }, // spike
                { duration: '1m', target: 0 },    // soguma
            ],
            tags: { pos_scenario: 'read_mix' },
        },
        // YAZMA yasam dongusu: create_order -> close_order/odeme.
        order_lifecycle: {
            executor: 'ramping-arrival-rate',
            exec: 'orderLifecycle',
            startRate: 2,
            timeUnit: '1s',
            preAllocatedVUs: 40,
            maxVUs: 120,
            startTime: '0s',
            stages: [
                { duration: '1m', target: 8 },
                { duration: '5m', target: 8 },
                { duration: '2m', target: 18 },
                { duration: '30s', target: 25 },
                { duration: '1m', target: 0 },
            ],
            tags: { pos_scenario: 'order_lifecycle' },
        },
        // Acik adisyon CEKISMESI: kucuk masa kumesine es-zamanli open-tab ->
        // (tenant,outlet,table) PARTIAL {status:open} dup guard'i zorlar.
        // 409 BEKLENEN sonuctur (TAB_ALREADY_OPEN), hata degildir.
        open_tab_contention: {
            executor: 'constant-arrival-rate',
            exec: 'openTabContention',
            rate: 8,
            timeUnit: '1s',
            duration: '9m30s',
            preAllocatedVUs: 30,
            maxVUs: 80,
            startTime: '0s',
            tags: { pos_scenario: 'open_tab_contention' },
        },
    },
    thresholds: {
        'pos_read_latency_ms': ['p(95)<1500'],
        'pos_create_latency_ms': ['p(95)<2500'],
        'pos_close_latency_ms': ['p(95)<3000'],
        'pos_tab_latency_ms': ['p(95)<3000'],
        // ASIL kapi: beklenmeyen hata (5xx / beklenmeyen 4xx) < %2.
        'pos_unexpected_errors': ['rate<0.02'],
        // Genel backstop: tam coku yine kirmizi yapsin. 409/429 burada sayilir,
        // bu yuzden esik gevsektir; gercek kalite kapisi pos_unexpected_errors.
        'http_req_failed': ['rate<0.25'],
    },
};

// ── Yardimcilar ─────────────────────────────────────────────────────────────
function randInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}

function uniq() {
    return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

function syntheticItems() {
    // Sentetik menu satirlari; v2 create_order menu lookup YAPMAZ (name+price
    // dogrudan kullanilir), bu yuzden gercek pos_menu_items'a ihtiyac yok.
    return [
        { name: 'Load Burger', quantity: randInt(1, 3), price: 120.0, station: 'kitchen' },
        { name: 'Load Cola', quantity: randInt(1, 2), price: 40.0, station: 'bar' },
    ];
}

function classify(res, okStatuses, expectedStatuses) {
    // okStatuses: basari; expectedStatuses: beklenen (ornek 409 contention,
    // 429 throttle) -> pos_unexpected'a KARISTIRILMAZ. Geri kalan her sey
    // (5xx dahil) beklenmeyen hatadir.
    const s = res.status;
    if (s === 429) {
        throttle429.add(1);
        return 'throttle';
    }
    if (okStatuses.includes(s)) {
        posUnexpected.add(false);
        return 'ok';
    }
    if (expectedStatuses.includes(s)) {
        posUnexpected.add(false);
        return 'expected';
    }
    posUnexpected.add(true);
    return 'unexpected';
}

const READ_ENDPOINTS = [
    '/api/fnb/dashboard',
    '/api/pos/mobile/active-orders',
    '/api/fnb/kitchen-display',
    '/api/pos/mobile/stock-levels',
    '/api/pos/mobile/low-stock-alerts',
];

// ── Setup: fail-closed env dogrulama + stress-admin login ───────────────────
export function setup() {
    const required = [
        'BASE_URL',
        'E2E_STRESS_ADMIN_EMAIL',
        'E2E_STRESS_ADMIN_PASSWORD',
        'E2E_STRESS_TENANT_ID',
        'POS_LOAD_PREFIX',
    ];
    for (const k of required) {
        if (!__ENV[k] || !String(__ENV[k]).trim()) {
            fail(`[pos_fnb_burst] zorunlu env eksik: ${k}. Bu test yalniz stress `
                + `tenant'ina, prefix'li ve cleanup'lanabilir sekilde calisir.`);
        }
    }

    const email = String(__ENV.E2E_STRESS_ADMIN_EMAIL).trim();
    const prefix = String(__ENV.POS_LOAD_PREFIX).trim();

    // Guvenlik kilidi: pilot/demo hesabiyla yazma yuku KESINLIKLE yasak.
    if (email.toLowerCase() === 'demo@hotel.com') {
        fail('[pos_fnb_burst] demo@hotel.com pilot/demo otele baglidir; yazma '
            + 'yuku pilot_drift\'i bozar. Adanmis E2E_STRESS_ADMIN hesabini kullan.');
    }
    // Prefix cok kisa ise cleanup regex'i tehlikeli olcude genis olur.
    if (prefix.length < 4) {
        fail(`[pos_fnb_burst] POS_LOAD_PREFIX cok kisa (${prefix.length}); en az `
            + `4 karakter olmali (ornek: POSLOAD_<ts>_).`);
    }

    const loginRes = http.post(`${BASE_URL}/api/auth/login`, JSON.stringify({
        email,
        password: String(__ENV.E2E_STRESS_ADMIN_PASSWORD),
    }), { headers: { 'Content-Type': 'application/json' } });

    if (loginRes.status !== 200) {
        fail(`[pos_fnb_burst] stress-admin login basarisiz: HTTP ${loginRes.status}`);
    }
    let token;
    try {
        token = JSON.parse(loginRes.body).access_token;
    } catch (e) {
        token = null;
    }
    if (!token) {
        fail('[pos_fnb_burst] login yanitinda access_token yok.');
    }

    // KRITIK guvenlik kapisi: token'in GERCEKTEN stress tenant'a ait oldugunu
    // dogrula. Env var'in var olmasi yetmez; yanlis-ama-gecerli bir admin/staff
    // hesabi verilirse o hesabin tenant'ina yazma yapilir -> pilot_drift riski.
    // /api/auth/me User dondurur (tenant_id alani yetkili kaynaktan gelir).
    const me = http.get(`${BASE_URL}/api/auth/me`, {
        headers: { 'Authorization': `Bearer ${token}` },
    });
    if (me.status !== 200) {
        fail(`[pos_fnb_burst] /auth/me dogrulamasi basarisiz: HTTP ${me.status}`);
    }
    let meTenant = null;
    try {
        meTenant = JSON.parse(me.body).tenant_id;
    } catch (e) {
        meTenant = null;
    }
    const stressTid = String(__ENV.E2E_STRESS_TENANT_ID).trim();
    if (!meTenant || String(meTenant) !== stressTid) {
        fail(`[pos_fnb_burst] token tenant'i (${meTenant}) E2E_STRESS_TENANT_ID `
            + `ile eslesmiyor. Yazma yuku yalniz stress tenant'a izinli `
            + `(pilot_drift=0). Calistirma durduruldu.`);
    }

    return {
        token,
        prefix,
        outletId: (__ENV.POS_OUTLET_ID && String(__ENV.POS_OUTLET_ID).trim())
            || `${prefix}OUTLET`,
    };
}

function authHeaders(data) {
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${data.token}`,
    };
}

// ── Senaryo 1: okuma karisimi ───────────────────────────────────────────────
export function readMix(data) {
    const headers = authHeaders(data);
    const path = READ_ENDPOINTS[randInt(0, READ_ENDPOINTS.length - 1)];
    const res = http.get(`${BASE_URL}${path}`, { headers, tags: { pos_kind: 'read' } });
    classify(res, [200], []);
    readLatency.add(res.timings.duration);
    check(res, { 'read 2xx': (r) => r.status === 200 });
}

// ── Senaryo 2: siparis yasam dongusu (create -> close) ──────────────────────
export function orderLifecycle(data) {
    const headers = authHeaders(data);
    const tag = `${data.prefix}${__VU}-${__ITER}-${uniq()}`;

    const createBody = JSON.stringify({
        outlet_id: data.outletId,
        table_number: `${data.prefix}L${__VU}x${__ITER}`,
        items: syntheticItems(),
        guest_name: `${data.prefix}G${__VU}`,
        order_type: 'dine_in',
        idempotency_key: `${tag}-c`,
    });
    const createRes = http.post(`${BASE_URL}/api/pos/v2/orders`, createBody, {
        headers, tags: { pos_kind: 'create' },
    });
    createLatency.add(createRes.timings.duration);
    const createState = classify(createRes, [200], []);
    check(createRes, { 'create 2xx': (r) => r.status === 200 });
    if (createState !== 'ok') {
        return;
    }

    let orderId = null;
    try {
        orderId = JSON.parse(createRes.body).order_id;
    } catch (e) {
        orderId = null;
    }
    if (!orderId) {
        // Govde sozlesmesi beklenmedik -> gercek sinyal, maskeleme yok.
        posUnexpected.add(true);
        return;
    }

    const closeBody = JSON.stringify({
        order_id: orderId,
        payment_method: 'cash',
        post_to_folio: false,
        tip_amount: 0.0,
        idempotency_key: `${tag}-x`,
    });
    const closeRes = http.post(`${BASE_URL}/api/pos/v2/orders/close`, closeBody, {
        headers, tags: { pos_kind: 'close' },
    });
    closeLatency.add(closeRes.timings.duration);
    classify(closeRes, [200], []);
    check(closeRes, { 'close 2xx': (r) => r.status === 200 });
}

// ── Senaryo 3: acik adisyon cekismesi (open-tab dup guard) ──────────────────
export function openTabContention(data) {
    const headers = authHeaders(data);
    const tag = `${data.prefix}${__VU}-${__ITER}-${uniq()}`;
    // Kucuk sicak masa kumesi -> ayni (outlet,table) icin yuksek collision.
    const table = `${data.prefix}T${randInt(1, 6)}`;

    const openBody = JSON.stringify({
        outlet_id: data.outletId,
        table_number: table,
        items: syntheticItems(),
        guest_name: `${data.prefix}G${__VU}`,
        guests: randInt(1, 4),
        idempotency_key: `${tag}-t`,
    });
    const openRes = http.post(`${BASE_URL}/api/pos/v2/tabs/open`, openBody, {
        headers, tags: { pos_kind: 'tab' },
    });
    tabLatency.add(openRes.timings.duration);
    // 409 = TAB_ALREADY_OPEN: BEKLENEN cekisme sonucu, hata degil.
    const state = classify(openRes, [200], [409]);
    if (openRes.status === 409) {
        tabConflict.add(1);
    }
    check(openRes, { 'tab open 2xx|409': (r) => r.status === 200 || r.status === 409 });
    if (state !== 'ok') {
        return;
    }

    // Basarili acilan adisyonu kapat -> masa serbest kalir, sonraki open
    // yarisabilir (200 + 409 karisimi surer). close_tab transaction_id ister.
    let txnId = null;
    try {
        txnId = JSON.parse(openRes.body).transaction_id;
    } catch (e) {
        txnId = null;
    }
    if (!txnId) {
        return;
    }
    const closeTabRes = http.post(`${BASE_URL}/api/pos/v2/tabs/close`, JSON.stringify({
        transaction_id: txnId,
        payment_method: 'cash',
    }), { headers, tags: { pos_kind: 'tab_close' } });
    classify(closeTabRes, [200], []);
}
