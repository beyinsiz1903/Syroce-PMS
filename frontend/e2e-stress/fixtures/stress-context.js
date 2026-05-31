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
    // Task #160 — rol-spesifik authenticated principal token'ları tek noktada.
    // globalSetup tarafından TOKEN_FILE.role_tokens'a yazılır; eksik dosya/anahtar
    // güvenli default (null) ile karşılanır. Değerler null OLABİLİR (fail-soft
    // provisioning): downstream spec null token'ı honest SKIP eder, ASLA
    // fake-green üretmez. Anahtarlar:
    //   super_admin  — pilot super_admin (cross-tenant/admin baseline)
    //   stress_admin — stress tenant admin (mutasyonların çoğu)
    //   staff_lowtrust — düşük-güven non-admin front_desk (RBAC-deny spec)
    //   agency_admin — acente-portal agency_admin (B2B IDOR / cross-tenant)
    stressRoles: async ({}, use) => {
        let roles = {};
        try {
            roles = loadJson(TOKEN_FILE)?.role_tokens || {};
        } catch { roles = {}; }
        await use({
            super_admin: roles.super_admin ?? null,
            stress_admin: roles.stress_admin ?? null,
            staff_lowtrust: roles.staff_lowtrust ?? null,
            agency_admin: roles.agency_admin ?? null,
        });
    },
});

export { expect };

// Task #160 — canonical path haritası + ortak stress helper'ları stress-context
// üzerinden de re-export edilir, böylece spec'ler tek import noktasından
// (fixtures/stress-context) hem fixture hem path/helper alır.
export { STRESS_PATHS, harvestWindow, resetHarvestCursors, assertIdempotentReplay } from './stress-helpers.js';

// Lightweight rec helper — appended to test annotations and consumed by md-reporter
export function rec(testInfo, payload) {
    testInfo.annotations.push({ type: 'rec', description: JSON.stringify(payload) });
}
