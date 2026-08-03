// İzin verilen "noisy ama zararsız" hata desenleri
export const CONSOLE_ERROR_ALLOWLIST = [
    /i18next.*missingKey/i,
    /Sentry.*beacon/i,
    /ResizeObserver loop/i,
    /Failed to load resource.*favicon/i,
    /websocket.*reconnect/i,
];
export const NETWORK_ERROR_ALLOWLIST = [
    /\/api\/health\/.*$/,         // health probe 503/404 OK
    /\/sentry\/.*$/,
    /\/socket\.io\/.*$/,
    /\.map(\?|$)/,
];

export function attachObservers(page) {
    const consoleErrors = [];
    const networkErrors = [];
    page.on('console', (msg) => {
        if (msg.type() !== 'error') return;
        const text = msg.text();
        if (CONSOLE_ERROR_ALLOWLIST.some((re) => re.test(text))) return;
        consoleErrors.push({ text, location: msg.location?.() });
    });
    page.on('response', (resp) => {
        const status = resp.status();
        if (status < 400) return;
        const url = resp.url();
        if (NETWORK_ERROR_ALLOWLIST.some((re) => re.test(url))) return;
        networkErrors.push({ url, status, method: resp.request().method() });
    });
    page.on('pageerror', (err) => {
        consoleErrors.push({ text: `[pageerror] ${err.message}`, location: null });
    });
    return { consoleErrors, networkErrors };
}

export async function inspectPageContent(page) {
    return page.evaluate(() => {
        const bodyText = (document.body?.innerText || '').trim();
        const lengthChars = bodyText.length;
        const domChildren = document.body?.children?.length ?? 0;
        const outerLen = document.body?.outerHTML?.length ?? 0;
        const head = bodyText.slice(0, 600);
        // 404/500 tek başına yaygın (KPI değerleri); error-state spesifik kombinasyonlar gereklidir.
        const has404 = /(404\s+(not\s+found|sayfa\s+bulun)|sayfa\s+bulunamad[ıi]|error\s+404)/i.test(head);
        const has500 = /(500\s+(internal\s+server|server\s+error|hata)|internal\s+server\s+error|sunucu\s+hatas[ıi]|error\s+500)/i.test(head);
        const hasErrorBoundary = /(something\s+went\s+wrong|bir\s+şeyler\s+ters\s+gitti|hata\s+olu[şs]tu|application\s+error)/i.test(head);
        const isLoading = lengthChars < 30 && /(loading|yükleniyor|\.\.\.$)/i.test(bodyText);
        // empty = innerText kısa VE DOM gerçekten boş VE outerHTML küçük (CSR hidrate olmamış değil; gerçekten boş sayfa)
        const empty = lengthChars < 10 && domChildren < 2 && outerLen < 500;
        return { lengthChars, domChildren, outerLen, has404, has500, hasErrorBoundary, isLoading, empty };
    });
}
