// Step recorder — testlerden çağrılır, custom reporter okur (annotation üzerinden).
// API: rec(testInfo, { module, scope, step, status, endpoint, http, note }) — status: PASS|FAIL|REVIEW|SKIP

export function rec(testInfo, entry) {
    const payload = {
        ts: new Date().toISOString(),
        module: entry.module || 'unknown',
        scope: entry.scope || null,
        step: entry.step || '',
        status: entry.status || 'REVIEW',
        endpoint: entry.endpoint || null,
        http: entry.http ?? null,
        note: entry.note || '',
    };
    testInfo.annotations.push({ type: 'rec', description: JSON.stringify(payload) });
}

export const PASS = 'PASS';
export const FAIL = 'FAIL';
export const REVIEW = 'REVIEW';
export const SKIP = 'SKIP';
