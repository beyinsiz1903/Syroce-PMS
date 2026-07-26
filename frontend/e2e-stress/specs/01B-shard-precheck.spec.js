import { test, expect } from '../fixtures/stress-context.js';

const ROOM_COUNT = parseInt(process.env.E2E_ROOM_COUNT || '500', 10);
const PROFILE = process.env.STRESS_PRECHECK_PROFILE || 'unknown';

async function verifyEndpoint(request, token, path, expectedMinCount, description, extractor) {
    const r = await request.get(path, {
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false,
        timeout: 30_000,
    });
    expect(r.ok(), `Precheck failed: ${path} returned ${r.status()}`).toBeTruthy();
    
    const j = await r.json().catch(() => ({}));
    
    const count = extractor(j);
    if (count === undefined || count === null || isNaN(count)) {
        throw new Error(`[precheck] Could not determine count for ${path}. Extractor returned invalid value. Response keys: ${Object.keys(j)}`);
    }

    if (expectedMinCount > 0) {
        expect(count, `Precheck missing auxiliary data for ${description} at ${path}`).toBeGreaterThanOrEqual(expectedMinCount);
    }
}


test.describe(`F7B § Shard Precheck [${PROFILE}]`, () => {

    test('Core entities exact counts (via seed_response)', async ({ stressState }) => {
        // Assert exact counts based on seed_response artifact
        const c = stressState.seed_response.seeded_counts;
        expect(c.rooms, 'base rooms must equal ROOM_COUNT').toBe(ROOM_COUNT);
        expect(c.bookings, 'bookings must equal ROOM_COUNT').toBe(ROOM_COUNT);
        expect(c.folios, 'folios must equal ROOM_COUNT').toBe(ROOM_COUNT);
    });

    if (PROFILE === 'front_office') {
        test('Front Office auxiliary data', async ({ request, stressTokens }) => {
            const token = stressTokens.stress_token;
            // No strict > 0 requirements for auxiliary data in front office yet, but we check endpoints
            await verifyEndpoint(request, token, '/api/pms/rooms', 0, 'Rooms', (j) => j.rooms?.length ?? j.items?.length ?? (Array.isArray(j) ? j.length : -1));
        });
    }

    if (PROFILE === 'operations') {
        test('Operations auxiliary data (Fail-fast if missing)', async ({ request, stressTokens }) => {
            const token = stressTokens.stress_token;
            // QR / Room requests
            // QR seed (source=guest_qr)
            await verifyEndpoint(request, token, '/api/room-requests?source=guest_qr&limit=1', 1, 'QR Requests Seed', (j) => j.items?.length ?? j.list?.length ?? (Array.isArray(j) ? j.length : -1));
            // Staff service requests (source=staff)
            await verifyEndpoint(request, token, '/api/room-requests?source=staff&limit=1', 1, 'Staff Service Requests', (j) => j.items?.length ?? j.list?.length ?? (Array.isArray(j) ? j.length : -1));
            // Complaints
            await verifyEndpoint(request, token, '/api/complaints/list?limit=1', 1, 'Complaints', (j) => j.data?.length ?? j.items?.length ?? (Array.isArray(j) ? j.length : -1));
            // Maintenance and Messaging readiness (expect reachable, so count=0 is fine)
            await verifyEndpoint(request, token, '/api/maintenance/work-orders?limit=1', 0, 'Maintenance Readiness', (j) => j.items?.length ?? j.data?.length ?? j.list?.length ?? (Array.isArray(j) ? j.length : 0));
            await verifyEndpoint(request, token, '/api/messaging/templates?limit=1', 0, 'Messaging Templates', (j) => j.items?.length ?? j.data?.length ?? j.list?.length ?? (Array.isArray(j) ? j.length : 0));
        });
    }

    if (PROFILE === 'mice_hr_finance') {
        test('MICE, HR, Spa auxiliary data (Fail-fast if missing)', async ({ request, stressTokens }) => {
            const token = stressTokens.stress_token;
            const stdExtract = (j) => j.items?.length ?? j.data?.length ?? j.list?.length ?? (Array.isArray(j) ? j.length : -1);
            await verifyEndpoint(request, token, '/api/hr/staff', 1, 'HR Staff', stdExtract);
            await verifyEndpoint(request, token, '/api/hr/departments', 1, 'HR Departments', stdExtract);
            await verifyEndpoint(request, token, '/api/spa/services', 1, 'Spa Services', (j) => j.services?.length ?? stdExtract(j));
            await verifyEndpoint(request, token, '/api/spa/therapists', 1, 'Spa Therapists', (j) => j.therapists?.length ?? stdExtract(j));
            await verifyEndpoint(request, token, '/api/spa/rooms', 1, 'Spa Rooms', (j) => j.rooms?.length ?? stdExtract(j));
            await verifyEndpoint(request, token, '/api/mice/events', 1, 'MICE Events', (j) => j.events?.length ?? stdExtract(j));
            // New additions
            await verifyEndpoint(request, token, '/api/mice/accounts', 1, 'MICE Parent Entities (Accounts)', stdExtract);
            await verifyEndpoint(request, token, '/api/pos/outlets', 1, 'POS Outlets / F&B Catalog', stdExtract);
            await verifyEndpoint(request, token, '/api/inventory/items', 1, 'Inventory Catalog', stdExtract); // May be 0 if seed missing, but endpoint must be reachable
        });
    }

    if (PROFILE === 'security_integrations') {
        test('Security and Integrations precheck', async ({ stressTokens }) => {
            // Check auth endpoints or other security prerequisites
            expect(stressTokens.stress_token).toBeTruthy();
        });
    }
});
