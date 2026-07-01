import { chromium } from 'playwright';
import { writeFileSync, readFileSync, mkdirSync } from 'node:fs';

const BASE = process.env.APP_URL || 'http://localhost:5000';
const API = process.env.API_URL || 'http://localhost:8000';
const EMAIL = 'info@syroce.com';
const PASS = 'Syroce2026';
const CONCURRENCY = parseInt(process.env.CONC || '3', 10);
const ROUTE_TIMEOUT = 25000;
const BUTTON_TIMEOUT = 1500;
const MAX_BUTTONS = 8; // per page
const OUT = '/tmp/audit_full';
mkdirSync(OUT, { recursive: true });

const ALL_ROUTES = JSON.parse(readFileSync('/tmp/routes.json', 'utf8'));
const START = parseInt(process.env.BATCH_START || '0', 10);
const END = parseInt(process.env.BATCH_END || String(ALL_ROUTES.length), 10);
const ROUTES = ALL_ROUTES.slice(START, END);
const BATCH_TAG = `${START}-${END}`;

// Skip very-similar duplicates: /foo and /app/foo both go to same component → keep both as routes
// but reduce noise: skip the /app/* duplicate if /<name> already there with same suffix
// Actually keep all — they may have different layout wrappers.

// Buttons whose text matches these regexes are SKIPPED (destructive / navigational-away)
const SKIP_BUTTON_RE = /(sil|kaldır|sıfırla|gönder|çıkış|logout|delete|remove|reset|send|submit|onayla|approve|reddet|reject|iptal et|cancel reservation|kapat hesab|deactivate|disable|terminate|sign\s*out|fatura kes|nakit al|tahsil|ödeme al|charge|refund|iade|atılan|destroy|wipe|export|indir|download|yazdır|print|email|e-posta gönder|bildir|notify|publish|yayınla|kilitle|unlock|kilit aç|dosya yükle|upload|stop|durdur|kill|abort|shutdown|night audit|gece kapat|run audit|trigger|tetikle|activate|aktive|switch tenant|impersonate|log\s*in as|delete account|hesabı sil|change password|şifre değiştir|hard refresh|reload|yeniden başlat|reboot|restart)/i;

const KEEP_TYPES = new Set(['button', 'submit', null, undefined, '']);

// Login + session bootstrap
const loginRes = await fetch(`${API}/api/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: EMAIL, password: PASS }),
});
if (!loginRes.ok) { console.error('Login failed'); process.exit(1); }
const { access_token, refresh_token, user, tenant } = await loginRes.json();
let modules = null;
try {
  const sRes = await fetch(`${API}/api/subscription/current`, { headers: { Authorization: `Bearer ${access_token}` } });
  if (sRes.ok) modules = (await sRes.json())?.modules || null;
} catch {}
console.log(`Logged in as ${user.email} • crawling ${ROUTES.length} routes (concurrency=${CONCURRENCY})`);

const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });

async function newAuthedPage() {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.evaluate(({ tok, refresh, u, t, mods }) => {
    localStorage.setItem('token', tok);
    localStorage.setItem('token_ts', String(Date.now()));
    if (refresh) localStorage.setItem('refresh_token', refresh);
    localStorage.setItem('user', JSON.stringify(u));
    localStorage.setItem('tenant', t ? JSON.stringify(t) : 'null');
    if (mods) localStorage.setItem('modules', JSON.stringify(mods));
    localStorage.setItem('language', 'tr');
  }, { tok: access_token, refresh: refresh_token, u: user, t: tenant, mods: modules });
  return { ctx, page };
}

async function auditRoute(page, route) {
  const consoleErrors = [];
  const failedRequests = [];
  const buttonResults = [];

  const onConsole = (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text().slice(0, 250)); };
  const onPageError = (err) => consoleErrors.push(`PAGE_ERROR: ${err.message}`.slice(0, 250));
  const onResponse = (resp) => {
    const s = resp.status();
    if (s >= 400) failedRequests.push(`${s} ${resp.request().method()} ${resp.url().replace(BASE,'').slice(0,180)}`);
  };
  page.on('console', onConsole);
  page.on('pageerror', onPageError);
  page.on('response', onResponse);

  let navOk = true, navErr = null;
  try {
    await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded', timeout: ROUTE_TIMEOUT });
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => {});
  } catch (e) {
    navOk = false; navErr = String(e.message).slice(0, 150);
  }
  await page.waitForTimeout(500);

  const finalUrl = page.url().replace(BASE, '');
  let bodyText = '';
  try { bodyText = (await page.evaluate(() => (document.body.innerText || '').slice(0, 500))); } catch {}
  const hasErrorBoundary = /something went wrong|hata oluştu|bir hata/i.test(bodyText) && /retry|tekrar|yenile/i.test(bodyText);

  // Click safe buttons
  if (navOk && !hasErrorBoundary && finalUrl !== '/auth' && finalUrl !== '/login') {
    let buttons = [];
    try {
      buttons = await page.$$eval('button:not([disabled])', (els) => els.slice(0, 40).map((b, i) => ({
        i,
        text: (b.innerText || b.getAttribute('aria-label') || '').trim().slice(0, 60),
        type: b.getAttribute('type') || '',
      })));
    } catch {}

    let clicked = 0;
    for (const b of buttons) {
      if (clicked >= MAX_BUTTONS) break;
      const txt = b.text;
      if (!txt || txt.length < 1) continue;
      if (SKIP_BUTTON_RE.test(txt)) continue;
      if (!KEEP_TYPES.has(b.type) && b.type !== 'button') continue;
      const errBefore = consoleErrors.length;
      const reqBefore = failedRequests.length;
      try {
        const handles = await page.$$('button:not([disabled])');
        const target = handles[b.i];
        if (!target) continue;
        await target.click({ timeout: BUTTON_TIMEOUT, force: false }).catch(() => {});
        await page.waitForTimeout(300);
        // Close any opened dialog/modal/sheet
        await page.keyboard.press('Escape').catch(() => {});
        await page.waitForTimeout(150);
      } catch (e) {
        consoleErrors.push(`CLICK_ERR[${txt}]: ${String(e.message).slice(0, 100)}`);
      }
      const newErrs = consoleErrors.length - errBefore;
      const new4xx = failedRequests.length - reqBefore;
      buttonResults.push({ text: txt, newErrors: newErrs, new4xx });
      clicked++;
    }
    var clickedCount = clicked;
    var totalButtons = buttons.length;
  }

  page.off('console', onConsole);
  page.off('pageerror', onPageError);
  page.off('response', onResponse);

  return {
    route, finalUrl, navOk, navErr,
    bodyPreview: bodyText.slice(0, 100),
    visibleChars: bodyText.replace(/\s+/g, '').length,
    hasErrorBoundary,
    consoleErrors: [...new Set(consoleErrors)].slice(0, 10),
    failedRequests: [...new Set(failedRequests)].slice(0, 10),
    buttons: { tried: clickedCount || 0, total: totalButtons || 0, results: buttonResults.filter(r => r.newErrors > 0 || r.new4xx > 0) },
  };
}

// Worker pool
const queue = [...ROUTES];
const results = [];
let processed = 0;
async function worker(id) {
  const { ctx, page } = await newAuthedPage();
  while (queue.length) {
    const route = queue.shift();
    if (!route) break;
    let r;
    try { r = await auditRoute(page, route); }
    catch (e) { r = { route, navOk: false, navErr: String(e.message).slice(0,150), consoleErrors: [], failedRequests: [], buttons: { tried: 0, total: 0, results: [] } }; }
    results.push(r);
    processed++;
    const tag = r.hasErrorBoundary ? 'BOOM' : (r.consoleErrors.length || r.failedRequests.length ? 'WARN' : 'ok');
    if (tag !== 'ok' || processed % 25 === 0) {
      console.log(`[w${id}] ${processed}/${ROUTES.length} ${tag.padEnd(4)} ${route} → ${r.finalUrl} btn=${r.buttons.tried}/${r.buttons.total} err=${r.consoleErrors.length} 4xx=${r.failedRequests.length}`);
    }
  }
  await ctx.close();
}

await Promise.all(Array.from({ length: CONCURRENCY }, (_, i) => worker(i + 1)));
writeFileSync(`${OUT}/report_${BATCH_TAG}.json`, JSON.stringify(results, null, 2));
await browser.close();

// Summary
const broken = results.filter(r => r.hasErrorBoundary || r.consoleErrors.length || r.failedRequests.length || !r.navOk);
console.log(`\n=== DONE ${results.length}/${ROUTES.length} routes ===`);
console.log(`Clean: ${results.length - broken.length}`);
console.log(`With issues: ${broken.length}`);
console.log(`Report: ${OUT}/report.json`);
