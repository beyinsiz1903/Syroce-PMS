// ─────────────────────────────────────────────────────────────────────────
// F9C § 98 — Marketplace Deep Lifecycle Stress.
// ─────────────────────────────────────────────────────────────────────────
//
// Scope (rapor §3.1 — Marketplace router 192 endpoint, deep yüzey ZERO idi):
//   Backend:
//     - backend/routers/marketplace_b2b.py        (prefix=/api/marketplace/v1)
//     - backend/routers/marketplace.py            (prefix=/api/module-store)
//     - backend/domains/pms/marketplace_router.py (prefix=/api,  /marketplace/*)
//
//   Yüzey (task #46 doctrine'inden mapping):
//     A) POST   /api/marketplace/v1/listings/me           (publish / opt-in)
//     B) GET    /api/marketplace/v1/listings/me           (read)
//     C) PUT    /api/marketplace/v1/listings/me           (update)
//     D) DELETE /api/marketplace/v1/listings/me           (unpublish / opt-out)
//     E) POST   /api/marketplace/v1/listings/me           (re-publish, idempotent)
//     F) GET    /api/marketplace/inventory                (inventory check)
//     G) GET    /api/marketplace/suppliers                (vendor profile)
//     H) POST   /api/marketplace/purchase-orders          (order place, tagged)
//     I) POST   /api/marketplace/purchase-orders/{id}/reject (order cancel)
//     J) IDOR   GET /api/marketplace/v1/hotels/{pilot_tid} with stress JWT
//               PATCH/DELETE pilot listing/order via cross-tenant id probes
//     K) Anon   headerless GET /api/marketplace/v1/listings/me  → 401/403
//     M) Invariant: external_calls=[]
//     N) Invariant: pilot drift (booking baseline + pilot listing/PO prefix scan)
//
// Mutlak kurallar (F9 doctrine):
//   - external_calls = []   (assertNoExternalCallsPostBatch)
//   - pilot mutation = 0    (assertPilotDriftZero — best effort)
//   - P0 = P1 = 0; 5xx = 0; PII leak = 0
//   - Tüm mutasyonlar stress-tenant scope; tüm POST'lara Idempotency-Key.
//   - Mutation tag'i: description/notes alanı `${prefix}_${SUB_PREFIX}_*`.
//   - Module-blocked doctrine: listing POST/GET non-2xx (404/403/501) →
//     A-I SKIP + REVIEW; J/K (security probes) BAĞIMSIZ çalışır.
//   - afterAll soft-cleanup: listing DELETE + PO reject (idempotent).
//
// Reporter satırı: `marketplace`.
// ─────────────────────────────────────────────────────────────────────────

import { randomUUID as cryptoRandomUUID } from 'node:crypto';
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'marketplace';
const SUB_PREFIX = 'F9C_MKT';
const GAP_MS = 1500;

test.describe.configure({ mode: 'serial' });

test.describe('F9C § 98 — Marketplace Deep Lifecycle', () => {
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let pilotBookingBaseline = null;
    let pilotKnownTenantId = null;     // best-effort pilot tenant id for J GET vendor
    let pilotKnownListingId = null;    // best-effort pilot listing id for J probe
    let pilotKnownPoId = null;         // best-effort pilot PO id for J probe
    const createdPoIds = [];
    let listingPublished = false;
    // PMS marketplace_router PO write surface (`/api/marketplace/*`) is gated by
    // the `hidden_marketplace` feature, independent of the b2b `/v1/listings/*`
    // surface that drives `moduleBlocked`. F/H/I depend on THIS gate.
    let marketplaceCoreEntitled = false;
    let coreBlockedReason = null;

    function idemKey(op, i = 0) {
        return `${SUB_PREFIX}_${op}_${Date.now()}_${i}_${cryptoRandomUUID()}`;
    }
    async function gap(ms = GAP_MS) {
        await new Promise((r) => setTimeout(r, ms));
    }
    function taggedString(label) {
        return `${prefix}_${SUB_PREFIX}_${label}`;
    }

    // ──────────────────────────────────────────────────────────────
    test('Setup: stress token + module probe + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        expect(prefix, 'stressState.data_prefix yok').toBeTruthy();

        if (stressTokens.pilot_token) {
            const snap = await pilotBookingsCount(request, stressTokens.pilot_token);
            pilotBookingBaseline = (snap?.count != null && !snap.unreachable) ? snap.count : null;

            // Best-effort: pilot tenant_id from pilot token's own listing/me.
            try {
                const pilotListing = await callTimed(
                    request, 'get', '/api/marketplace/v1/listings/me', null,
                    stressTokens.pilot_token, { timeout: 10_000 },
                );
                if (pilotListing.status === 200 && pilotListing.body?.listing?.tenant_id) {
                    pilotKnownTenantId = pilotListing.body.listing.tenant_id;
                    pilotKnownListingId = pilotListing.body.listing.id || null;
                }
            } catch { /* ignore — J falls back to bogus id */ }

            // Best-effort: pilot purchase-order sample for J cross-tenant probe.
            try {
                const pilotPos = await callTimed(
                    request, 'get', '/api/marketplace/purchase-orders', null,
                    stressTokens.pilot_token, { timeout: 10_000 },
                );
                if (pilotPos.status === 200 && Array.isArray(pilotPos.body?.orders) && pilotPos.body.orders.length > 0) {
                    pilotKnownPoId = pilotPos.body.orders[0].id || null;
                }
            } catch { /* ignore */ }
        }

        // Marketplace CORE entitlement probe — the PMS marketplace_router PO
        // surface (`/api/marketplace/*`) is gated by the `hidden_marketplace`
        // feature, granted to the stress tenant by the seed endpoint. This is
        // INDEPENDENT of the b2b `/v1/listings/*` surface below, so it runs
        // before any module-blocked early-return. MUST use the STRESS token —
        // super_admin bypasses require_feature, which would be a false positive.
        const coreProbe = await callTimed(
            request, 'get', '/api/marketplace/purchase-orders/entitlement-check', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        if (coreProbe.status >= 500) {
            recFinding(testInfo, 'P1', MOD,
                'Marketplace core entitlement-check 5xx',
                `status=${coreProbe.status} body=${JSON.stringify(coreProbe.body || {}).slice(0, 200)}`);
            expect(coreProbe.status, 'Marketplace core entitlement 5xx').toBeLessThan(500);
        }
        if (coreProbe.status >= 200 && coreProbe.status < 300 && coreProbe.body?.entitled === true) {
            marketplaceCoreEntitled = true;
        } else {
            marketplaceCoreEntitled = false;
            coreBlockedReason = `core_not_entitled_${coreProbe.status}`;
            recFinding(testInfo, 'P2', MOD,
                `Marketplace PO surface not entitled (hidden_marketplace) status=${coreProbe.status}`,
                'Remediation: cd backend && python -m scripts.enable_marketplace_for_stress (seed endpoint also sets it).');
        }
        rec(testInfo, {
            module: MOD, step: 'core_entitlement_probe',
            status: marketplaceCoreEntitled ? 'PASS' : 'REVIEW',
            http: coreProbe.status,
            note: `hidden_marketplace entitled=${marketplaceCoreEntitled}`,
        });

        // Module probe: GET listing — stress tenant hotel admin scope.
        const probe = await callTimed(
            request, 'get', '/api/marketplace/v1/listings/me', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        if (probe.status >= 500) {
            recFinding(testInfo, 'P1', MOD,
                'Marketplace module 5xx on setup probe',
                `GET /api/marketplace/v1/listings/me → ${probe.status}; body=${JSON.stringify(probe.body || {}).slice(0, 200)}`);
            expect(probe.status, 'Marketplace setup 5xx').toBeLessThan(500);
        }
        if (probe.status === 401 || probe.status === 403 || probe.status === 404 || probe.status === 501) {
            moduleBlocked = true;
            blockedReason = `setup_probe_${probe.status}`;
            rec(testInfo, {
                module: MOD, step: 'module_probe', status: 'REVIEW',
                http: probe.status, note: 'Module blocked / not deployed — A-I SKIP, J/K independent.',
            });
            recFinding(testInfo, 'P2', MOD,
                `Marketplace listings/me blocked at setup (${probe.status})`,
                'A-I lifecycle SKIP; security probes (J/K) bağımsız çalışır.');
            return;
        }
        rec(testInfo, {
            module: MOD, step: 'module_probe', status: 'PASS',
            http: probe.status,
            note: `listings/me 2xx — is_listed=${probe.body?.is_listed} pilot_tid=${pilotKnownTenantId ? 'captured' : 'none'} pilot_po=${pilotKnownListingId ? 'captured' : 'none'}`,
        });
    });

    // ──────────────────────────────────────────────────────────────
    // A) PUBLISH — POST /listings/me  (opt-in)
    test('A) Publish listing — stress-tenant opt-in', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'A_publish', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        // Pre-clean: if a prior round left an opt-in active, DELETE it idempotently
        // so POST returns 200 (otherwise 409 "zaten listelenmiş").
        await callTimed(
            request, 'delete', '/api/marketplace/v1/listings/me', null,
            stressTokens.stress_token, { timeout: 10_000 },
        ).catch(() => null);
        await gap(300);

        const payload = {
            hotel_name: taggedString('hotel'),
            city: 'Istanbul',
            country: 'TR',
            address: taggedString('addr'),
            description: taggedString('A_publish'),
            photos: [],
            amenities: ['wifi'],
            star_rating: 4,
            commission_pct: 10,
            allowed_room_types: [],
            blocked_dates: [],
        };
        const r = await callTimed(
            request, 'post', '/api/marketplace/v1/listings/me', payload,
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'Idempotency-Key': idemKey('A_publish') } },
        );
        recPerf(testInfo, MOD, 'A_publish', [r.ms], r.status >= 200 && r.status < 300);

        if ([403, 404, 422, 501].includes(r.status)) {
            rec(testInfo, { module: MOD, step: 'A_publish', status: 'REVIEW', http: r.status, note: 'opt-in endpoint not deployed / payload mismatch' });
            recFinding(testInfo, 'P2', MOD, `POST listings/me non-2xx status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            return;
        }
        expect(r.status, `A_publish unexpected status=${r.status}`).toBeLessThan(500);
        expect(r.status, `A_publish non-2xx status=${r.status}`).toBeGreaterThanOrEqual(200);
        expect(r.status).toBeLessThan(300);

        const listing = r.body?.listing || {};
        expect(listing.tenant_id, 'A_publish listing tenant_id yok').toBeTruthy();
        expect(listing.is_listed, 'A_publish is_listed flag yok').toBe(true);
        listingPublished = true;

        rec(testInfo, { module: MOD, step: 'A_publish', status: 'PASS', http: r.status, note: `listing_id=${listing.id}` });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // B) READ — GET /listings/me
    test('B) Read listing — verify tenant scope', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'B_read', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/marketplace/v1/listings/me', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `B_read 5xx`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `B_read non-200 status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'B_read', status: 'REVIEW', http: r.status });
            return;
        }
        const listing = r.body?.listing;
        if (listingPublished) {
            expect(listing, 'B_read listing null sonrası publish').toBeTruthy();
            // Tenant scope invariant: returned listing must NOT match pilot tenant id.
            if (pilotKnownTenantId && listing?.tenant_id) {
                expect(listing.tenant_id, 'B_read CROSS-TENANT LEAK: stress sees pilot listing!').not.toBe(pilotKnownTenantId);
            }
        }
        rec(testInfo, { module: MOD, step: 'B_read', status: 'PASS', http: r.status, note: `is_listed=${r.body?.is_listed}` });
        await gap(500);
    });

    // ──────────────────────────────────────────────────────────────
    // C) UPDATE — PUT /listings/me
    test('C) Update listing — PUT changes apply', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (!listingPublished ? 'no_listing_published' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'C_update', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const r = await callTimed(
            request, 'put', '/api/marketplace/v1/listings/me',
            { description: taggedString('C_update'), star_rating: 5 },
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'Idempotency-Key': idemKey('C_update') } },
        );
        expect(r.status, `C_update 5xx`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `C_update non-200 status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'C_update', status: 'REVIEW', http: r.status });
            return;
        }
        expect(r.body?.ok, 'C_update ok flag yok').toBe(true);
        rec(testInfo, { module: MOD, step: 'C_update', status: 'PASS', http: r.status });
        await gap(500);
    });

    // ──────────────────────────────────────────────────────────────
    // D) UNPUBLISH — DELETE /listings/me  (opt-out)
    test('D) Unpublish listing — DELETE sets is_listed=false', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (!listingPublished ? 'no_listing_published' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'D_unpublish', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const r = await callTimed(
            request, 'delete', '/api/marketplace/v1/listings/me', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `D_unpublish 5xx`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `D_unpublish non-200 status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'D_unpublish', status: 'REVIEW', http: r.status });
            return;
        }
        // Verify via GET — is_listed must be false
        const verify = await callTimed(
            request, 'get', '/api/marketplace/v1/listings/me', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        if (verify.status === 200) {
            expect(verify.body?.is_listed, 'D_unpublish is_listed hala true').toBe(false);
        }
        rec(testInfo, { module: MOD, step: 'D_unpublish', status: 'PASS', http: r.status });
        await gap(500);
    });

    // ──────────────────────────────────────────────────────────────
    // E) RE-PUBLISH — POST /listings/me sonrası DELETE → 2xx idempotent loop
    test('E) Re-publish after unpublish — lifecycle idempotency', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (!listingPublished ? 'no_listing_published' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'E_republish', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const payload = {
            hotel_name: taggedString('hotel2'),
            city: 'Ankara',
            country: 'TR',
            address: taggedString('addr2'),
            description: taggedString('E_republish'),
            star_rating: 3,
            commission_pct: 8,
        };
        const r = await callTimed(
            request, 'post', '/api/marketplace/v1/listings/me', payload,
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'Idempotency-Key': idemKey('E_republish') } },
        );
        expect(r.status, `E_republish 5xx`).toBeLessThan(500);
        if (r.status !== 200) {
            // 409 = zaten listelenmiş → state regression doctrine
            recFinding(testInfo, 'P2', MOD, `E_republish non-200 status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'E_republish', status: 'REVIEW', http: r.status });
            return;
        }
        expect(r.body?.listing?.is_listed, 'E_republish is_listed yeniden true değil').toBe(true);
        rec(testInfo, { module: MOD, step: 'E_republish', status: 'PASS', http: r.status });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // F) INVENTORY CHECK — GET /api/marketplace/inventory (PMS marketplace)
    test('F) Inventory check — GET marketplace/inventory', async ({ request, stressTokens }, testInfo) => {
        if (!marketplaceCoreEntitled) {
            rec(testInfo, { module: MOD, step: 'F_inventory', status: 'REVIEW', note: coreBlockedReason || 'core_not_entitled' });
            test.skip(true, coreBlockedReason || 'core_not_entitled');
        }
        const r = await callTimed(
            request, 'get', '/api/marketplace/inventory', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `F_inventory 5xx`).toBeLessThan(500);
        // Entitled tenant MUST be able to read inventory — hard-assert 2xx + array.
        expect(r.status, `F_inventory not 2xx (status=${r.status})`).toBeGreaterThanOrEqual(200);
        expect(r.status, `F_inventory not 2xx (status=${r.status})`).toBeLessThan(300);
        const items = r.body?.inventory || [];
        expect(Array.isArray(items), 'F_inventory items array değil').toBe(true);
        // Tenant scope invariant — backend filters by tenant_id; double-check.
        for (const it of items.slice(0, 20)) {
            if (it.tenant_id && pilotKnownTenantId) {
                expect(it.tenant_id, 'F_inventory CROSS-TENANT LEAK').not.toBe(pilotKnownTenantId);
            }
        }
        rec(testInfo, { module: MOD, step: 'F_inventory', status: 'PASS', http: r.status, note: `items=${items.length}` });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // G) VENDOR PROFILE — GET /api/marketplace/suppliers
    test('G) Vendor profile — GET marketplace/suppliers', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'G_vendors', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/marketplace/suppliers', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `G_vendors 5xx`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `suppliers non-200 status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'G_vendors', status: 'REVIEW', http: r.status });
            return;
        }
        const list = r.body?.suppliers || r.body?.items || [];
        expect(Array.isArray(list), 'G_vendors response array değil').toBe(true);
        rec(testInfo, { module: MOD, step: 'G_vendors', status: 'PASS', http: r.status, note: `count=${list.length}` });
    });

    // ──────────────────────────────────────────────────────────────
    // H) ORDER PLACE — POST /api/marketplace/purchase-orders (tagged, idempotent)
    test('H) Order place — POST purchase-orders', async ({ request, stressTokens }, testInfo) => {
        if (!marketplaceCoreEntitled) {
            rec(testInfo, { module: MOD, step: 'H_order', status: 'REVIEW', note: coreBlockedReason || 'core_not_entitled' });
            test.skip(true, coreBlockedReason || 'core_not_entitled');
        }
        const payload = {
            supplier: taggedString('H_supplier'),
            items: [{ product_name: taggedString('H_item'), quantity: 2, unit_price: 3.5 }],
            delivery_location: taggedString('H_loc'),
            expected_delivery_date: new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10),
        };
        const r = await callTimed(
            request, 'post', '/api/marketplace/purchase-orders', payload,
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'Idempotency-Key': idemKey('H_order') } },
        );
        recPerf(testInfo, MOD, 'H_order', [r.ms], r.status >= 200 && r.status < 300);
        expect(r.status, `H_order 5xx`).toBeLessThan(500);
        // Entitled tenant MUST be able to create a PO — hard-assert the real
        // create contract (2xx + id + tenant scope + pending status).
        expect(r.status, `H_order not 2xx (status=${r.status}) body=${JSON.stringify(r.body || {}).slice(0, 200)}`).toBeGreaterThanOrEqual(200);
        expect(r.status, `H_order not 2xx (status=${r.status})`).toBeLessThan(300);
        expect(r.body?.id, 'H_order PO id yok').toBeTruthy();
        expect(r.body?.tenant_id, 'H_order PO tenant_id yok').toBeTruthy();
        expect(r.body?.status, 'H_order PO status pending değil').toBe('pending');
        // Tenant scope invariant — created PO must NOT belong to the pilot.
        if (pilotKnownTenantId) {
            expect(r.body.tenant_id, 'H_order PO CROSS-TENANT').not.toBe(pilotKnownTenantId);
        }
        createdPoIds.push(r.body.id);
        rec(testInfo, { module: MOD, step: 'H_order', status: 'PASS', http: r.status, note: `po_id=${r.body.id}` });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // I) ORDER CANCEL — POST /api/marketplace/purchase-orders/{id}/cancel
    test('I) Order cancel — POST purchase-orders/{id}/cancel', async ({ request, stressTokens }, testInfo) => {
        const reason = !marketplaceCoreEntitled
            ? (coreBlockedReason || 'core_not_entitled')
            : (createdPoIds.length === 0 ? 'no_po_created' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'I_cancel', status: 'REVIEW', note: reason });
            test.skip(true, reason);
        }
        const poId = createdPoIds[0];
        const r = await callTimed(
            request, 'post',
            `/api/marketplace/purchase-orders/${poId}/cancel`,
            { reason: taggedString('I_cancel') },
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'Idempotency-Key': idemKey('I_cancel') } },
        );
        expect(r.status, `I_cancel 5xx`).toBeLessThan(500);
        // Created PO MUST cancel — hard-assert 2xx + terminal cancelled status.
        expect(r.status, `I_cancel not 2xx (status=${r.status}) body=${JSON.stringify(r.body || {}).slice(0, 200)}`).toBeGreaterThanOrEqual(200);
        expect(r.status, `I_cancel not 2xx (status=${r.status})`).toBeLessThan(300);
        expect(r.body?.status, 'I_cancel status cancelled değil').toBe('cancelled');
        expect(r.body?.id, 'I_cancel PO id yok').toBe(poId);

        // Idempotency — re-cancel returns 2xx + still cancelled (no error).
        const r2 = await callTimed(
            request, 'post',
            `/api/marketplace/purchase-orders/${poId}/cancel`,
            { reason: taggedString('I_cancel_again') },
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'Idempotency-Key': idemKey('I_cancel2') } },
        );
        expect(r2.status, `I_cancel idempotent 5xx`).toBeLessThan(500);
        expect(r2.status >= 200 && r2.status < 300, `I_cancel re-cancel not 2xx (status=${r2.status})`).toBe(true);
        expect(r2.body?.status, 'I_cancel re-cancel status cancelled değil').toBe('cancelled');

        rec(testInfo, { module: MOD, step: 'I_cancel', status: 'PASS', http: r.status, note: `po_id=${poId} cancelled` });
        await gap(500);
    });

    // ──────────────────────────────────────────────────────────────
    // J) SECURITY: cross-tenant IDOR — real pilot id first, bogus fallback
    test('J) IDOR: cross-tenant probes → no mutation / no leak', async ({ request, stressTokens }, testInfo) => {
        // J1: GET pilot vendor profile via stress JWT (agency endpoint, JWT should be rejected)
        const targetTid = pilotKnownTenantId || `cross-tenant-${cryptoRandomUUID()}`;
        const probeKind1 = pilotKnownTenantId ? 'real_pilot_tenant_id' : 'bogus_tid_fallback';
        const r1 = await callTimed(
            request, 'get', `/api/marketplace/v1/hotels/${targetTid}`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r1.status, `J1 5xx`).toBeLessThan(500);
        // Agency endpoint expects X-API-Key, not JWT. 2xx returning pilot listing = leak.
        if (r1.status >= 200 && r1.status < 300) {
            const body = r1.body || {};
            const leaks = body?.tenant_id === pilotKnownTenantId
                || JSON.stringify(body).includes(pilotKnownTenantId || '__never__');
            if (leaks) {
                recFinding(testInfo, 'P0', MOD,
                    `IDOR breach: stress JWT read pilot vendor profile (${probeKind1})`,
                    `target_tid=${targetTid} body=${JSON.stringify(body).slice(0, 200)}`);
            }
            expect(leaks, `J1: stress JWT exposed pilot vendor data via ${probeKind1}`).toBe(false);
        }
        // 401/403/404 = correct rejection. Any other status = REVIEW.
        const r1Ok = [200, 401, 403, 404].includes(r1.status);
        if (!r1Ok) {
            recFinding(testInfo, 'P2', MOD, `J1 unexpected status=${r1.status}`, `probe=${probeKind1}`);
        }

        // J2: DELETE pilot purchase-order via stress token → must 404/403 (NEVER 2xx success)
        const targetPoId = pilotKnownPoId || `cross-tenant-${cryptoRandomUUID()}`;
        const probeKind2 = pilotKnownPoId ? 'real_pilot_po_id' : 'bogus_po_fallback';
        const r2 = await callTimed(
            request, 'post',
            `/api/marketplace/purchase-orders/${targetPoId}/reject`,
            { reason: 'J2_cross_tenant_probe' },
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r2.status, `J2 5xx`).toBeLessThan(500);
        if (r2.status >= 200 && r2.status < 300) {
            recFinding(testInfo, 'P0', MOD,
                `IDOR breach: stress token rejected pilot PO (${probeKind2})`,
                `po_id=${targetPoId} status=${r2.status} body=${JSON.stringify(r2.body || {}).slice(0, 200)}`);
        }
        expect(r2.status >= 400, `J2: cross-tenant PO reject succeeded (${probeKind2})`).toBe(true);

        // J3: CANCEL pilot purchase-order via stress token → must 403/404 (NEVER
        // 2xx). The new /cancel endpoint is tenant-scoped; cross-tenant access
        // must fall through to the 404 not-found guard, never mutate a pilot PO.
        const r3 = await callTimed(
            request, 'post',
            `/api/marketplace/purchase-orders/${targetPoId}/cancel`,
            { reason: 'J3_cross_tenant_cancel_probe' },
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r3.status, `J3 5xx`).toBeLessThan(500);
        if (r3.status >= 200 && r3.status < 300) {
            recFinding(testInfo, 'P0', MOD,
                `IDOR breach: stress token cancelled pilot PO (${probeKind2})`,
                `po_id=${targetPoId} status=${r3.status} body=${JSON.stringify(r3.body || {}).slice(0, 200)}`);
        }
        expect(r3.status >= 400, `J3: cross-tenant PO cancel succeeded (${probeKind2})`).toBe(true);
        expect([403, 404].includes(r3.status), `J3: cross-tenant cancel unexpected status=${r3.status} (expected 403/404)`).toBe(true);

        rec(testInfo, {
            module: MOD, step: 'J_idor', status: 'PASS',
            http: r1.status,
            note: `J1=${probeKind1}/${r1.status} J2=${probeKind2}/${r2.status} J3=cancel/${r3.status}`,
        });
    });

    // ──────────────────────────────────────────────────────────────
    // K) SECURITY: Anonymous (headerless) GET → 401/403
    test('K) Anonymous (headerless) GET listings/me → 401/403', async ({ request }, testInfo) => {
        let status = 0;
        let bodySnippet = '';
        try {
            const r = await request.get('/api/marketplace/v1/listings/me', {
                failOnStatusCode: false,
                timeout: 10_000,
                // Intentionally headerless — no Authorization header at all.
            });
            status = r.status();
            try { bodySnippet = (await r.text()).slice(0, 200); } catch { /* ignore */ }
        } catch (e) {
            recFinding(testInfo, 'P2', MOD, 'K_anon network error', String(e?.message || e).slice(0, 200));
        }
        expect(status, `K_anon 5xx status=${status}`).toBeLessThan(500);

        const blocked = status === 401 || status === 403 || status === 429;
        if (!blocked) {
            recFinding(testInfo, 'P1', MOD,
                `Anonymous GET marketplace listings/me not blocked (status=${status})`,
                `PUBLIC SURFACE LEAK — listing/PII reachable without auth. body=${bodySnippet}`);
        }
        expect(blocked, `K_anon: headerless returned ${status} (expected 401/403)`).toBe(true);
        rec(testInfo, { module: MOD, step: 'K_anon', status: 'PASS', http: status, note: 'headerless probe' });
    });

    // ──────────────────────────────────────────────────────────────
    // INVARIANTS
    test('M) Invariant: external_calls=[] for this module batch', async ({ request, stressTokens, stressState }, testInfo) => {
        const ok = await assertNoExternalCallsPostBatch(
            testInfo, MOD, 'F9C_MKT_full',
            stressState, request, stressTokens.pilot_token,
        );
        expect(ok, 'external_calls invariant failed').toBe(true);
    });

    test('N) Invariant: pilot drift — booking baseline + pilot marketplace prefix scan', async ({ request, stressTokens }, testInfo) => {
        const primaryOk = await assertPilotDriftZero(
            testInfo, MOD, request, stressTokens.pilot_token,
            pilotBookingBaseline,
        );
        expect(primaryOk, 'pilot drift primary failed (booking baseline)').toBe(true);

        // Supplemental: pilot marketplace prefix scan — pilot listing + pilot PO listesi
        // bizim SUB_PREFIX tag'imizden hiçbir kayıt içermemeli (pilot read-only mutlak).
        if (stressTokens.pilot_token) {
            try {
                const pilotListing = await callTimed(
                    request, 'get', '/api/marketplace/v1/listings/me', null,
                    stressTokens.pilot_token, { timeout: 10_000 },
                );
                if (pilotListing.status === 200) {
                    const desc = pilotListing.body?.listing?.description || '';
                    const name = pilotListing.body?.listing?.hotel_name || '';
                    if (desc.includes(SUB_PREFIX) || name.includes(SUB_PREFIX)) {
                        recFinding(testInfo, 'P0', MOD,
                            'Pilot listing leak: stress prefix found in pilot tenant listing',
                            `desc=${desc.slice(0, 100)} name=${name.slice(0, 100)}`);
                        expect(false, 'pilot listing contains stress prefix').toBe(true);
                    }
                }
                const pilotPos = await callTimed(
                    request, 'get', '/api/marketplace/purchase-orders', null,
                    stressTokens.pilot_token, { timeout: 10_000 },
                );
                if (pilotPos.status === 200 && Array.isArray(pilotPos.body?.orders)) {
                    const tainted = pilotPos.body.orders.filter((p) =>
                        (p.supplier || '').includes(SUB_PREFIX)
                        || (p.delivery_location || '').includes(SUB_PREFIX));
                    if (tainted.length > 0) {
                        recFinding(testInfo, 'P0', MOD,
                            'Pilot PO leak: stress prefix found in pilot purchase orders',
                            `count=${tainted.length} sample=${JSON.stringify(tainted[0]).slice(0, 200)}`);
                        expect(tainted.length, 'pilot POs contain stress prefix').toBe(0);
                    }
                }
                rec(testInfo, { module: MOD, step: 'pilot_prefix_scan', status: 'PASS', note: 'no stress prefix in pilot marketplace data' });
            } catch (e) {
                rec(testInfo, { module: MOD, step: 'pilot_prefix_scan', status: 'REVIEW', note: `scan_error=${String(e?.message || e).slice(0, 80)}` });
            }
        } else {
            rec(testInfo, { module: MOD, step: 'pilot_prefix_scan', status: 'SKIP', note: 'no pilot_token' });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // CLEANUP — soft, idempotent: unpublish listing + reject any leftover POs.
    // Round-2 (architect): afterAll cannot inject test-level fixtures
    // (stressTokens/request). Same pattern as 98-maintenance: load token
    // cache from disk + create a fresh global request context.
    test.afterAll(async ({}, testInfo) => {
        const cleanupRec = {
            module: MOD,
            step: 'cleanup',
            listing_published: listingPublished,
            po_attempted: createdPoIds.length,
            note: 'soft opt-out + PO reject; idempotent best-effort',
        };
        try {
            const { request: globalRequest } = await import('@playwright/test');
            const path = (await import('node:path')).default;
            const fs = await import('node:fs');
            const TOKEN_FILE = path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-token.json');
            if (!fs.existsSync(TOKEN_FILE)) {
                cleanupRec.status = 'SKIP';
                cleanupRec.note += ' | token cache yok';
                testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
                return;
            }
            const tok = JSON.parse(fs.readFileSync(TOKEN_FILE, 'utf-8')).stress_token;
            const ctx = await globalRequest.newContext({
                extraHTTPHeaders: { Authorization: `Bearer ${tok}`, 'Content-Type': 'application/json' },
            });
            // Listing opt-out (idempotent — 404 if already opt-out, swallow).
            let listingOptedOut = false;
            try {
                const r = await ctx.delete('/api/marketplace/v1/listings/me',
                    { timeout: 10_000, failOnStatusCode: false });
                if (r.status() < 500) listingOptedOut = true;
            } catch { /* idempotent best-effort */ }
            // PO reject (idempotent — already-rejected returns 4xx, swallow).
            let posRejected = 0;
            for (const poId of createdPoIds) {
                try {
                    const r = await ctx.post(
                        `/api/marketplace/purchase-orders/${poId}/reject`,
                        { data: { reason: 'F9C_MKT_cleanup' },
                          timeout: 10_000, failOnStatusCode: false },
                    );
                    if (r.status() < 500) posRejected += 1;
                } catch { /* idempotent best-effort */ }
            }
            await ctx.dispose();
            cleanupRec.listing_opted_out = listingOptedOut;
            cleanupRec.pos_rejected = posRejected;
            cleanupRec.status = 'PASS';
            testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
        } catch (e) {
            cleanupRec.status = 'REVIEW';
            cleanupRec.error = String(e?.message || e).slice(0, 200);
            testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
        }
    });
});
