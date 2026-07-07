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
    stressTokens: async ({}, use) => {
        const tokens = loadJson(TOKEN_FILE);
        const tag = process.env.STRESS_REPORT_TAG || '';
        let shardKey = null;
        if (tag.includes('shard_b')) shardKey = 'stress_admin_b';
        else if (tag.includes('shard_c')) shardKey = 'stress_admin_c';
        else if (tag.includes('shard_d')) shardKey = 'stress_admin_d';
        else if (tag.includes('shard_e')) shardKey = 'stress_admin_e';

        if (shardKey && tokens.role_tokens?.[shardKey]) {
            tokens.stress_token = tokens.role_tokens[shardKey];
        }
        await use(tokens);
    },
    // Task #160 — rol-spesifik authenticated principal token'ları tek noktada.
    // globalSetup tarafından TOKEN_FILE.role_tokens'a yazılır; eksik dosya/anahtar
    // güvenli default (null) ile karşılanır. Değerler null OLABİLİR (fail-soft
    // provisioning): downstream spec null token'ı honest SKIP eder, ASLA
    // fake-green üretmez. Anahtarlar:
    //   super_admin  — pilot super_admin (cross-tenant/admin baseline)
    //   stress_admin — stress tenant admin (mutasyonların çoğu)
    //   staff_lowtrust — düşük-güven non-admin front_desk (RBAC-deny spec)
    //   staff_housekeeping — non-admin housekeeping; view_guest_list YOK
    //     (Task #213 — PII-mask edilen recipient path'ini hard-assert için)
    //   agency_admin — acente-portal agency_admin (B2B IDOR / cross-tenant)
    stressRoles: async ({}, use) => {
        let roles = {};
        try {
            roles = loadJson(TOKEN_FILE)?.role_tokens || {};
        } catch { roles = {}; }
        const tag = process.env.STRESS_REPORT_TAG || '';
        let activeAdminToken = roles.stress_admin ?? null;
        if (tag.includes('shard_b') && roles.stress_admin_b) activeAdminToken = roles.stress_admin_b;
        else if (tag.includes('shard_c') && roles.stress_admin_c) activeAdminToken = roles.stress_admin_c;
        else if (tag.includes('shard_d') && roles.stress_admin_d) activeAdminToken = roles.stress_admin_d;
        else if (tag.includes('shard_e') && roles.stress_admin_e) activeAdminToken = roles.stress_admin_e;
        await use({
            super_admin: roles.super_admin ?? null,
            stress_admin: activeAdminToken,
            staff_lowtrust: roles.staff_lowtrust ?? null,
            staff_housekeeping: roles.staff_housekeeping ?? null,
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
