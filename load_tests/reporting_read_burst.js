/**
 * k6 Load Test - Reporting / Dashboard + Night-Audit OKUMA yuku (saf-read)
 * ============================================================================
 * Sistemin EN AGIR OKUMA katmanini birincil hedef alir: GM snapshot, rol-bazli
 * dashboard, executive KPI ve ozellikle Night-Audit finansal ozetleri (6 paralel
 * aggregate; folio_charges + payments uzerinde $match/$group). Bu kati hem DB
 * index'lerini hem de cache stratejisini (redis_cache / advanced_cache L1-L3 /
 * in-process _cache) gercek yuk altinda sinar.
 *
 * IKI MOD (Murat'in iki sorusuna birebir karsilik):
 *   1) cached_read_mix  -> default parametreler. Ilk cagri sonrasi cevap cache'ten
 *      doner; cache-hit servis verimini ve sicak-latency'yi olcer ("Redis'i ne
 *      kadar akilli kullaniyoruz").
 *   2) cold_aggregation -> nocache=true + degisken tarih/periyot. Her cagri sicak
 *      yolu (heavy aggregate) yeniden kosar; ham DB + index performansini olcer
 *      ("Database Indexing yeterli mi").
 *
 * DOKTRIN (mutlak):
 *   - PMS IS VERISI SALT-OKUMA. Hicbir rezervasyon/folyo/oda/finans mutasyonu
 *     yapilmaz -> is-verisi cleanup'i GEREKMEZ. pilot_drift=0 insaen (token
 *     tenant'i ile DB sorgulari otomatik scoped).
 *   - TAM SIFIR DEGIL, bilincli istisna: (a) login POST'u basariliysa STRESS
 *     tenant'a bir audit_logs satiri yazar; (b) okunan endpoint'ler cevabi
 *     cache'e populate eder. Ikisi de STRESS tenant'ta kalir, pilot'a DOKUNMAZ.
 *     Tam sifir-yan-etki istenirse: E2E_STRESS_ADMIN_TOKEN ile login atlanir
 *     (asagiya bak); okuma cache-populate yine olur (dogasi geregi).
 *   - Yalniz stress tenant'ina baglanir (E2E_STRESS_ADMIN + E2E_STRESS_TENANT_ID).
 *     demo@hotel.com / pilot tenant ASLA hedef alinmaz.
 *   - Bu testi AGENT calistirmaz; operator deploy'a karsi dispatch eder.
 *
 * SETUP-PROBE (fail-closed + no fake-green):
 *   Aday endpoint'ler stress-admin token'i ile bir kez yoklanir. Yalniz 200 donen
 *   surfler yuke alinir; perm-gate (view_finance_reports / view_executive_reports
 *   / view_reports) nedeniyle 403 donenler SESSIZCE haric tutulur ve setup loguna
 *   yazilir. Boylece RBAC kodda zayiflatilmaz, gate bir "beklenmeyen hata" gibi
 *   sahte-kirmizi uretmez. Eger en agir finans/executive endpoint'leri haric
 *   kaliyorsa: adanmis stress hesabina view_finance_reports + view_executive_reports
 *   + view_reports yetkilerini ver (test hesabi senin kontrolunde, en-az-yetkili).
 *   ASIL DB/index yukunu yalniz night-audit finans aggregate'leri gercekten cold
 *   surer; hicbiri erisilemiyorsa kosu fail-closed durur (bilincli istisna:
 *   ALLOW_CACHED_ONLY=true). Boylece cache-only bir kosu sahte-yesil sayilmaz.
 *
 * Dispatch (ozet):
 *   k6 run \
 *     -e BASE_URL=https://<deploy> \
 *     -e E2E_STRESS_ADMIN_EMAIL=<secret> \
 *     -e E2E_STRESS_ADMIN_PASSWORD=<secret> \
 *     -e E2E_STRESS_TENANT_ID=<stress_tid> \
 *     load_tests/reporting_read_burst.js
 *   Opsiyonel env:
 *     E2E_STRESS_ADMIN_TOKEN  -> login POST'unu (ve audit_logs yan-etkisini) atlar.
 *     ALLOW_CACHED_ONLY=true  -> cold (night-audit finans) endpoint erisilemezse
 *                                kosuyu fail etmek yerine bilincli cache-only surer.
 *   Ayrintilar + perm notu: load_tests/README.md
 */
import http from 'k6/http';
import { check, fail } from 'k6';
import { Trend, Counter, Rate } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL;

// -- Custom metrikler -------------------------------------------------------
// Latency cagri tipine gore AYRI izlenir; cache-hit ile cold-aggregate ayni
// esige sokulmaz (cold dogal olarak yavastir).
const readCachedLatency = new Trend('read_cached_latency_ms');
const readColdLatency = new Trend('read_cold_latency_ms');
// ASIL kalite kapisi: 5xx VEYA beklenmeyen 4xx. 429 (throttle) ayri sayilir,
// yoksa gercek hata sinyali maskelenir.
const readUnexpected = new Rate('read_unexpected_errors');
const throttle429 = new Counter('read_throttle_429');

export const options = {
    scenarios: {
        // Birincil OKUMA yuku: cache-friendly default parametreler.
        cached_read_mix: {
            executor: 'ramping-arrival-rate',
            exec: 'cachedRead',
            startRate: 10,
            timeUnit: '1s',
            preAllocatedVUs: 80,
            maxVUs: 250,
            stages: [
                { duration: '1m', target: 40 },   // isinma
                { duration: '5m', target: 40 },   // surekli okuma yogunlugu
                { duration: '2m', target: 100 },  // peak ramp
                { duration: '30s', target: 160 }, // spike
                { duration: '1m', target: 0 },    // soguma
            ],
            tags: { read_scenario: 'cached_read_mix' },
        },
        // COLD agregasyon: nocache + degisken parametre -> sicak yolu zorlar.
        // Dusuk rate, cunku her cagri gercek aggregate kosar.
        cold_aggregation: {
            executor: 'ramping-arrival-rate',
            exec: 'coldRead',
            startRate: 2,
            timeUnit: '1s',
            preAllocatedVUs: 40,
            maxVUs: 120,
            startTime: '0s',
            stages: [
                { duration: '1m', target: 6 },
                { duration: '5m', target: 6 },
                { duration: '2m', target: 14 },
                { duration: '30s', target: 20 },
                { duration: '1m', target: 0 },
            ],
            tags: { read_scenario: 'cold_aggregation' },
        },
    },
    thresholds: {
        // Cache-hit hizli olmali.
        'read_cached_latency_ms': ['p(95)<800'],
        // Cold aggregate (6 paralel $group) dogal olarak yavas; gevsek esik.
        'read_cold_latency_ms': ['p(95)<3500'],
        // ASIL kapi: beklenmeyen hata (5xx / beklenmeyen 4xx) < %2.
        'read_unexpected_errors': ['rate<0.02'],
        // Genel backstop: tam coku yine kirmizi yapsin (429 burada sayilir).
        'http_req_failed': ['rate<0.20'],
    },
};

// -- Aday endpoint'ler ------------------------------------------------------
// CACHED: default parametre -> ilk cagri sonrasi cache servisi.
const CANDIDATE_CACHED = [
    '/api/gm/snapshot-enhanced',
    '/api/dashboard/role-based',
    '/api/dashboard/trend-kpis',
    '/api/executive/kpi-snapshot',
    '/api/executive/daily-summary',
    '/api/night-audit/status',
    '/api/night-audit/business-date',
    '/api/night-audit/history?limit=20',
    '/api/night-audit/financial-summary',
];

// COLD: param tipine gore degisken sorgu -> her cagri heavy aggregate.
// path = perm-probe icin cikis yolu (bare path gate'i temsil eder).
const CANDIDATE_COLD = [
    { path: '/api/night-audit/financial-summary', param: 'date_nocache' },
    { path: '/api/night-audit/payment-reconciliation', param: 'date_nocache' },
    { path: '/api/night-audit/integrity-check', param: 'date_nocache' },
    { path: '/api/night-audit/financial-report', param: 'date_range' },
    { path: '/api/dashboard/trend-kpis', param: 'period' },
    { path: '/api/dashboard/employee-performance', param: 'date_range' },
    { path: '/api/dashboard/guest-satisfaction-trends', param: 'days' },
    { path: '/api/dashboard/gm-forecast', param: 'none' },
];

// -- Yardimcilar ------------------------------------------------------------
function randInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}

function isoDaysAgo(days) {
    return new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);
}

function todayIso() {
    return new Date().toISOString().slice(0, 10);
}

function buildColdQuery(param) {
    switch (param) {
        case 'date_nocache':
            // nocache -> in-process _cache bypass; degisken tarih -> aggregate yeniden.
            return `?nocache=true&date=${isoDaysAgo(randInt(0, 90))}`;
        case 'date_range':
            // end=bugun, start=gecmis -> start <= end garanti.
            return `?start_date=${isoDaysAgo(randInt(7, 90))}&end_date=${todayIso()}`;
        case 'period':
            return `?period=${['7days', '30days', '90days'][randInt(0, 2)]}`;
        case 'days':
            return `?days=${[7, 30, 90][randInt(0, 2)]}`;
        case 'none':
        default:
            return '';
    }
}

function classify(res) {
    // 429 (throttle) ASIL hata oranina KARISTIRILMAZ; ayri sayilir. 200 disindaki
    // her sey (5xx dahil) beklenmeyen hatadir -> gercek sinyal maskelenmez.
    if (res.status === 429) {
        throttle429.add(1);
        return 'throttle';
    }
    if (res.status === 200) {
        readUnexpected.add(false);
        return 'ok';
    }
    readUnexpected.add(true);
    return 'unexpected';
}

// -- Setup: fail-closed env + stress-admin login + tenant kilidi + probe ----
export function setup() {
    // Pre-minted token verilirse login POST'u (ve audit_logs yan-etkisi) atlanir.
    const preToken = (__ENV.E2E_STRESS_ADMIN_TOKEN
        && String(__ENV.E2E_STRESS_ADMIN_TOKEN).trim()) || '';

    // BASE_URL + tenant her zaman zorunlu. Login icin email+password yalniz
    // pre-token YOKSA zorunlu.
    const required = preToken
        ? ['BASE_URL', 'E2E_STRESS_TENANT_ID']
        : ['BASE_URL', 'E2E_STRESS_ADMIN_EMAIL', 'E2E_STRESS_ADMIN_PASSWORD',
            'E2E_STRESS_TENANT_ID'];
    for (const k of required) {
        if (!__ENV[k] || !String(__ENV[k]).trim()) {
            fail(`[reporting_read_burst] zorunlu env eksik: ${k}. Bu test yalniz `
                + `stress tenant'a karsi, salt-okuma calisir.`);
        }
    }

    let token = preToken;
    if (!token) {
        const email = String(__ENV.E2E_STRESS_ADMIN_EMAIL).trim();
        // Guvenlik kilidi: pilot/demo hesabi hedef alinmaz.
        if (email.toLowerCase() === 'demo@hotel.com') {
            fail('[reporting_read_burst] demo@hotel.com pilot/demo otele baglidir; '
                + 'adanmis E2E_STRESS_ADMIN hesabini kullan (pilot_drift=0).');
        }
        const loginRes = http.post(`${BASE_URL}/api/auth/login`, JSON.stringify({
            email,
            password: String(__ENV.E2E_STRESS_ADMIN_PASSWORD),
        }), { headers: { 'Content-Type': 'application/json' } });
        if (loginRes.status !== 200) {
            fail(`[reporting_read_burst] stress-admin login basarisiz: HTTP ${loginRes.status}`);
        }
        try {
            token = JSON.parse(loginRes.body).access_token;
        } catch (e) {
            token = null;
        }
        if (!token) {
            fail('[reporting_read_burst] login yanitinda access_token yok.');
        }
    }

    // KRITIK kapi: token'in GERCEKTEN stress tenant'a ait oldugunu dogrula. Env
    // var'in var olmasi yetmez; yanlis-ama-gecerli bir hesap baska tenant'i
    // okumaya yol acabilir.
    const me = http.get(`${BASE_URL}/api/auth/me`, {
        headers: { 'Authorization': `Bearer ${token}` },
    });
    if (me.status !== 200) {
        fail(`[reporting_read_burst] /auth/me dogrulamasi basarisiz: HTTP ${me.status}`);
    }
    let meTenant = null;
    try {
        meTenant = JSON.parse(me.body).tenant_id;
    } catch (e) {
        meTenant = null;
    }
    const stressTid = String(__ENV.E2E_STRESS_TENANT_ID).trim();
    if (!meTenant || String(meTenant) !== stressTid) {
        fail(`[reporting_read_burst] token tenant'i (${meTenant}) E2E_STRESS_TENANT_ID `
            + `ile eslesmiyor. Okuma yuku yalniz stress tenant'a izinli. Durduruldu.`);
    }

    // Probe: erisilebilir (200) endpoint'leri sec. Perm-gate (403) sessizce
    // haric birakilir + loglanir -> sahte-kirmizi yok, RBAC zayiflatma yok.
    const probeHeaders = { 'Authorization': `Bearer ${token}` };
    function probe(url) {
        const r = http.get(`${BASE_URL}${url}`, { headers: probeHeaders });
        return r.status;
    }

    const cached = [];
    const cachedExcluded = [];
    for (const url of CANDIDATE_CACHED) {
        if (probe(url) === 200) {
            cached.push(url);
        } else {
            cachedExcluded.push(url);
        }
    }

    const cold = [];
    const coldExcluded = [];
    for (const item of CANDIDATE_COLD) {
        // bare path ile probe -> perm gate param'dan bagimsiz calisir.
        if (probe(item.path) === 200) {
            cold.push(item);
        } else {
            coldExcluded.push(item.path);
        }
    }

    // ASIL DB/index yukunu yalniz night-audit finans aggregate'leri (nocache=true
    // + degisken tarih) gercekten cold surer; dashboard cold'lari @cached altinda
    // (key param'i icerir, ama sonlu param uzayinda birkac varyanttan sonra isinir).
    const coldFinance = cold.filter((it) => it.path.indexOf('/api/night-audit/') === 0);
    const allowCachedOnly = String(__ENV.ALLOW_CACHED_ONLY || '').toLowerCase() === 'true';

    console.log(`[reporting_read_burst] cached aktif=${cached.length} `
        + `haric=${cachedExcluded.length} (${cachedExcluded.join(', ') || '-'})`);
    console.log(`[reporting_read_burst] cold aktif=${cold.length} `
        + `haric=${coldExcluded.length} (${coldExcluded.join(', ') || '-'})`);
    console.log(`[reporting_read_burst] cold night-audit finans=${coldFinance.length} `
        + `(${coldFinance.map((it) => it.path).join(', ') || '-'})`);

    if (cached.length === 0 && cold.length === 0) {
        fail('[reporting_read_burst] hicbir okuma endpoint\'i erisilebilir degil '
            + '(hepsi 403/4xx). Stress hesabina view_reports + view_finance_reports '
            + '+ view_executive_reports yetkilerini ver.');
    }
    // Fail-closed (no fake-green): cold heavy-aggregate (night-audit finans) yoksa
    // bu kosu cache-only/reporting-smoke kalitesindedir; DB/index yuku OLCULMEZ.
    // Bilincli cache-only kosu icin ALLOW_CACHED_ONLY=true gec.
    if (coldFinance.length === 0) {
        if (allowCachedOnly) {
            console.warn('[reporting_read_burst] UYARI: night-audit finans cold '
                + 'endpoint YOK -> kosu CACHE-ONLY / reporting-smoke; DB/index yuku '
                + 'OLCULMEZ. (ALLOW_CACHED_ONLY=true ile bilincli devam; '
                + 'read_cold_latency_ms ornek uretmeyebilir.)');
        } else {
            fail('[reporting_read_burst] cold heavy-aggregate (night-audit finans) '
                + 'endpoint erisilemez -> DB/index yuku olculemez (cache-only kosu '
                + 'sahte-yesil sayilmaz). Stress hesabina view_finance_reports ver; '
                + 'ya da bilincli cache-only kosu icin ALLOW_CACHED_ONLY=true gec.');
        }
    }

    return { token, cached, cold };
}

function authHeaders(data) {
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${data.token}`,
    };
}

// -- Senaryo 1: cache-friendly okuma karisimi -------------------------------
export function cachedRead(data) {
    if (!data.cached || data.cached.length === 0) {
        return;
    }
    const path = data.cached[randInt(0, data.cached.length - 1)];
    const res = http.get(`${BASE_URL}${path}`, {
        headers: authHeaders(data), tags: { read_kind: 'cached' },
    });
    classify(res);
    readCachedLatency.add(res.timings.duration);
    check(res, { 'cached read 2xx': (r) => r.status === 200 });
}

// -- Senaryo 2: cold heavy-aggregate okuma ----------------------------------
export function coldRead(data) {
    if (!data.cold || data.cold.length === 0) {
        return;
    }
    const item = data.cold[randInt(0, data.cold.length - 1)];
    const url = `${item.path}${buildColdQuery(item.param)}`;
    const res = http.get(`${BASE_URL}${url}`, {
        headers: authHeaders(data), tags: { read_kind: 'cold' },
    });
    classify(res);
    readColdLatency.add(res.timings.duration);
    check(res, { 'cold read 2xx': (r) => r.status === 200 });
}
