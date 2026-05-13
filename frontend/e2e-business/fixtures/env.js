export function requireEnv(key) {
    const v = process.env[key];
    if (!v) throw new Error(`[e2e-business] Eksik env: ${key}`);
    return v;
}
export const BASE_URL = () => requireEnv('E2E_BASE_URL');
export const TS = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
export const E2E_PREFIX = (kind) => `E2E_${TS()}_${kind}`;
