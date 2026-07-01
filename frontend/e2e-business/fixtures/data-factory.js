import fs from 'node:fs';
import path from 'node:path';
import { E2E_PREFIX } from './env.js';

// Playwright spec dosyaları bu helper'ı CJS-transform ile yüklüyor → import.meta.url YOK.
// process.cwd() Playwright'ta config dizinidir (frontend/).
const REGISTRY_FILE = path.join(process.cwd(), 'e2e-business', '.auth', 'data-registry.json');

function loadRegistry() {
    try { return JSON.parse(fs.readFileSync(REGISTRY_FILE, 'utf-8')); } catch { return { entities: [] }; }
}
function saveRegistry(r) {
    fs.mkdirSync(path.dirname(REGISTRY_FILE), { recursive: true });
    fs.writeFileSync(REGISTRY_FILE, JSON.stringify(r, null, 2));
}

export function trackEntity({ kind, id, label, cleanup = 'pending', endpoint = null }) {
    const r = loadRegistry();
    r.entities.push({ kind, id, label, cleanup, endpoint, createdAt: new Date().toISOString() });
    saveRegistry(r);
}
export function listEntities() { return loadRegistry().entities; }

export const factory = {
    guestName: () => E2E_PREFIX('GUEST'),
    reservationLabel: () => E2E_PREFIX('RES'),
    folioLabel: () => E2E_PREFIX('FOLIO'),
    miceLabel: () => E2E_PREFIX('MICE'),
    userEmail: () => `${E2E_PREFIX('USER').toLowerCase()}@e2e.local`,
    companyName: () => E2E_PREFIX('CO'),
    invoiceVkn: () => `${Math.floor(1000000000 + Math.random() * 8999999999)}`,
};
