// F7 stress fixtures — read globalSetup state, expose stress + pilot bearer + helpers.
import { test as base, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const AUTH_DIR = path.join(process.cwd(), 'e2e-stress', '.auth');
const STATE_FILE = path.join(AUTH_DIR, 'stress-state.json');
const TOKEN_FILE = path.join(AUTH_DIR, 'stress-token.json');

function loadJson(p) {
    if (!fs.existsSync(p)) throw new Error(`[stress-context] missing file: ${p}`);
    return JSON.parse(fs.readFileSync(p, 'utf-8'));
}

export const test = base.extend({
    stressState: async ({}, use) => { await use(loadJson(STATE_FILE)); },
    stressTokens: async ({}, use) => { await use(loadJson(TOKEN_FILE)); },
});

export { expect };

// Lightweight rec helper — appended to test annotations and consumed by md-reporter
export function rec(testInfo, payload) {
    testInfo.annotations.push({ type: 'rec', description: JSON.stringify(payload) });
}
