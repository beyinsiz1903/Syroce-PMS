// Güvenli buton tıklama: yalnız refresh/search whitelist; destructive blacklist katmanı
const SAFE_TEXT = /^(yenile|refresh|ara|search|filtrele|filter|göster|show|listele|list)\b/i;
const DESTRUCTIVE = /(sil|delete|iptal|cancel|refund|void|kapat|close shift|vardiya kapat|çıkış yap|logout|sign out)/i;

export async function clickSafeButtons(page, { max = 3 } = {}) {
    const summary = { clicked: 0, skipped: 0, errors: 0, details: [] };
    const buttons = page.locator('button:visible');
    const total = await buttons.count().catch(() => 0);
    for (let i = 0; i < Math.min(total, 30) && summary.clicked < max; i++) {
        const btn = buttons.nth(i);
        let text = '';
        try { text = (await btn.innerText({ timeout: 2_000 })).trim(); } catch { continue; }
        if (!text) continue;
        if (DESTRUCTIVE.test(text)) { summary.skipped++; summary.details.push({ text, action: 'skipped-destructive' }); continue; }
        if (!SAFE_TEXT.test(text)) { summary.skipped++; continue; }
        try {
            await btn.click({ timeout: 5_000, trial: false });
            await page.waitForLoadState('networkidle', { timeout: 8_000 }).catch(() => {});
            summary.clicked++;
            summary.details.push({ text, action: 'clicked' });
        } catch (e) {
            summary.errors++;
            summary.details.push({ text, action: 'error', error: e.message });
        }
    }
    return summary;
}

export async function softFill(page, locator, value) {
    try { await locator.fill(value, { timeout: 5_000 }); return true; } catch { return false; }
}
export async function softClick(locator, opts = {}) {
    try { await locator.click({ timeout: 5_000, ...opts }); return true; } catch { return false; }
}
export async function existsVisible(locator, timeout = 3_000) {
    try { await locator.first().waitFor({ state: 'visible', timeout }); return true; } catch { return false; }
}
