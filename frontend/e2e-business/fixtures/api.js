import fs from 'node:fs';
import path from 'node:path';
import { request } from '@playwright/test';

// process.cwd() Playwright'ta config dizinidir (frontend/).
const TOKEN_FILE = path.join(process.cwd(), 'e2e-business', '.auth', 'token.json');

let cached = null;
export function loadToken() {
    if (cached) return cached;
    try {
        const raw = fs.readFileSync(TOKEN_FILE, 'utf-8');
        const obj = JSON.parse(raw);
        cached = obj.token || null;
    } catch {
        cached = null;
    }
    return cached;
}

export async function makeApi(baseURL) {
    const token = loadToken();
    const ctx = await request.newContext({
        baseURL,
        ignoreHTTPSErrors: true,
        extraHTTPHeaders: token ? { Authorization: `Bearer ${token}` } : {},
    });
    return ctx;
}

export async function safeGet(ctx, url, opts = {}) {
    try {
        const r = await ctx.get(url, { failOnStatusCode: false, ...opts });
        return { status: r.status(), ok: r.ok(), body: await r.text().catch(() => '') };
    } catch (e) {
        return { status: 0, ok: false, body: '', error: e.message };
    }
}
