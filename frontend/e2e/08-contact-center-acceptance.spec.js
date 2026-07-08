import { test, expect } from '@playwright/test';
import { loginAsDemo, STORAGE_STATE, PASSWORD } from './fixtures/auth.js';
import { randomUUID } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

test.use({ storageState: STORAGE_STATE });

test.describe('Contact Center Faz 1 - Production Acceptance Test', () => {
    let mockJwtToken;
    let sessionToken;
    let testTenant;

    test.beforeAll(async ({ playwright }) => {
        // Build a fake JWT that expires 1 hour from now so the UI considers it fresh
        const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString('base64');
        
        // Read the actual active user session token from state.json first as backup
        const statePath = path.resolve(STORAGE_STATE);
        if (fs.existsSync(statePath)) {
            const state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
            const cookie = state.cookies.find(c => c.name === 'access_token');
            if (cookie) {
                sessionToken = cookie.value;
                const parts = sessionToken.split('.');
                if (parts.length === 3) {
                    const payloadJson = JSON.parse(Buffer.from(parts[1].replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString());
                    testTenant = payloadJson.tenant_id;
                }
            }
        }

        if (!testTenant) {
            testTenant = 'bb306859-9748-430f-b24a-5a0d0ea29309';
        }

        const payload = Buffer.from(JSON.stringify({
            iat: Math.floor(Date.now() / 1000),
            exp: Math.floor(Date.now() / 1000) + 3600,
            tenant_id: testTenant
        })).toString('base64');
        mockJwtToken = `${header}.${payload}.signature`;
    });

    test.beforeEach(async ({ page }) => {
        // 1. Intercept the voice token endpoint and return our fake fresh JWT token
        await page.route('**/contact-center/voice/token', async (route) => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ token: mockJwtToken })
            });
        });

        // 2. Inject window.Twilio mock before the page loads
        await page.addInitScript(() => {
            window.__getUserMediaCallCount = 0;
            
            // Mock getUserMedia to track call counts
            if (!navigator.mediaDevices) {
                Object.defineProperty(navigator, 'mediaDevices', {
                    value: {},
                    writable: true
                });
            }
            navigator.mediaDevices.getUserMedia = async (constraints) => {
                window.__getUserMediaCallCount++;
                return {
                    getTracks: () => [{ stop: () => {} }]
                };
            };

            // Mock window.AudioContext
            const mockAudioContext = {
                state: "suspended",
                resume: async () => {}
            };
            window.AudioContext = function() { return mockAudioContext; };
            window.webkitAudioContext = function() { return mockAudioContext; };

            // Mock Twilio.Device
            let registeredCallback = null;
            let unregisteredCallback = null;
            const mockDeviceInstance = {
                on: (event, cb) => {
                    if (event === "registered") registeredCallback = cb;
                    if (event === "unregistered") unregisteredCallback = cb;
                },
                register: async () => {
                    if (registeredCallback) registeredCallback();
                },
                unregister: async () => {
                    if (unregisteredCallback) unregisteredCallback();
                },
                connect: async () => {
                    return {
                        on: () => {},
                        disconnect: () => {}
                    };
                },
                destroy: () => {}
            };

            window.Twilio = {
                Device: function() {
                    return mockDeviceInstance;
                }
            };
        });
    });

    test('1. Müsait -> Mola -> Müsait geçişinde mikrofon tekrar sorulmuyor', async ({ page }) => {
        // Force complete clean slate (cookies, localStorage, and sessionStorage)
        await page.goto('/auth');
        await page.evaluate(() => {
            localStorage.clear();
            sessionStorage.clear();
        });
        await page.context().clearCookies();
        await page.reload();
        await loginAsDemo(page);
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // Click Softphone trigger button to open it
        const softphoneTrigger = page.locator('button[aria-label="Softphone"], button[title="Softphone"]').first();
        await expect(softphoneTrigger).toBeVisible();
        await softphoneTrigger.click();

        // Check that the activate button "Müsait (Çevrimiçi Ol)" is visible
        const activateBtn = page.getByRole('button', { name: /Müsait \(Çevrimiçi Ol\)/i });
        await expect(activateBtn).toBeVisible({ timeout: 15000 });

        // Clear sessionStorage to make sure getUserMedia runs the first time
        await page.evaluate(() => sessionStorage.removeItem("microphone_permission_granted"));

        // First transition: Click "Müsait (Çevrimiçi Ol)"
        await activateBtn.click();

        // The status select should be visible and value should be "ready"
        const statusSelect = page.locator('select').first();
        await expect(statusSelect).toBeVisible();
        await expect(statusSelect).toHaveValue('ready');

        // Get getUserMedia call count (should be 1 because we cleared permission)
        let count = await page.evaluate(() => window.__getUserMediaCallCount);
        expect(count).toBe(1);

        // Second transition: Go to break (select break_short)
        await statusSelect.selectOption('break_short');
        await expect(statusSelect).toHaveValue('break_short');

        // Third transition: Go back online (select ready)
        await statusSelect.selectOption('ready');
        await expect(statusSelect).toHaveValue('ready');

        // Verify getUserMedia call count is STILL 1 (cached via sessionStorage)
        count = await page.evaluate(() => window.__getUserMediaCallCount);
        expect(count).toBe(1);

        const lsKeys = await page.evaluate(() => JSON.stringify(localStorage));
        const cookiesList = await page.context().cookies();
        console.log('E2E_DEBUG: localStorage content:', lsKeys);
        console.log('E2E_DEBUG: cookies content:', JSON.stringify(cookiesList.map(c => ({ name: c.name, secure: c.secure }))));

        // Extract the fresh sessionToken from localStorage (or cookies as backup) to use for subsequent API tests
        const tokenVal = await page.evaluate(() => localStorage.getItem('token') || localStorage.getItem('access_token'));
        if (tokenVal) {
            sessionToken = tokenVal;
        } else {
            const cookies = await page.context().cookies();
            const accessCookie = cookies.find(c => c.name === 'access_token');
            if (accessCookie) {
                sessionToken = accessCookie.value;
            }
        }

        if (sessionToken) {
            const parts = sessionToken.split('.');
            if (parts.length === 3) {
                const payloadJson = JSON.parse(Buffer.from(parts[1].replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString());
                testTenant = payloadJson.tenant_id;
            }
        }
    });

    test('2. Idempotency ve Webhook Akışı: Tek Dial Child, WhatsApp queued/sent/delivered ve Çağrı Geçmişi', async ({ playwright }) => {
        expect(sessionToken).toBeTruthy();
        expect(testTenant).toBeTruthy();

        const request = await playwright.request.newContext({
            baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
            extraHTTPHeaders: {
                'Origin': 'http://localhost:3000',
                'Authorization': `Bearer ${sessionToken}`
            }
        });

        const headers = {
            'Origin': 'http://localhost:3000',
            'Authorization': `Bearer ${sessionToken}`
        };

        const agentName = 'agent1';
        const clientIdentity = `client:${testTenant}:${agentName}`;
        const toNumber = '+908503334455';

        // 1. Create a voice number mapping for the tenant's agent to allow outbound dialing
        const numRes = await request.post('/api/contact-center/voice/numbers', {
            data: {
                to_number: toNumber,
                agent_identity: `${testTenant}:${agentName}`,
                label: 'Test Acceptance Number',
                tenant_id: testTenant
            },
            headers: headers
        });
        
        // If it already exists (409), we ignore the error
        if (numRes.status() !== 201 && numRes.status() !== 409) {
            console.error('Failed to create voice number mapping:', await numRes.text());
        }
        expect([201, 409]).toContain(numRes.status());

        let numberId = null;
        if (numRes.status() === 201) {
            const numBody = await numRes.json();
            numberId = numBody.id;
        } else {
            // Find existing number mapping ID to clean up later
            const listRes = await request.get('/api/contact-center/voice/numbers', { headers: headers });
            expect(listRes.status()).toBe(200);
            const listBody = await listRes.json();
            const existing = listBody.numbers?.find(n => n.to_number === toNumber);
            if (existing) {
                numberId = existing.id;
            }
        }

        const callSid = 'CA_accept_test_' + randomUUID().substring(0, 8);
        const attemptId = randomUUID();

        // A. Verify Outgoing Dial Child creation is idempotent (Only 1 child, subsequent receives <Hangup/>)
        // 1. First outbound request
        const res1 = await request.post('/api/voice/outbound', {
            form: {
                CallSid: callSid,
                From: clientIdentity,
                To: '+905551112233',
                call_attempt_id: attemptId
            },
            headers: { 'Origin': 'http://localhost:3000' }
        });
        expect(res1.status()).toBe(200);
        const text1 = await res1.text();
        expect(text1).toContain('<Dial'); // Should initiate dial

        // 2. Second outbound request with the same parent CallSid (retry scenario)
        const res2 = await request.post('/api/voice/outbound', {
            form: {
                CallSid: callSid,
                From: clientIdentity,
                To: '+905551112233',
                call_attempt_id: attemptId
            },
            headers: { 'Origin': 'http://localhost:3000' }
        });
        expect(res2.status()).toBe(200);
        const text2 = await res2.text();
        expect(text2).toContain('<Hangup/>'); // Should drop the retry to prevent duplicate child legs

        // 3. Third outbound request with same attempt_id but different CallSid
        const res3 = await request.post('/api/voice/outbound', {
            form: {
                CallSid: callSid + '_dup',
                From: clientIdentity,
                To: '+905551112233',
                call_attempt_id: attemptId
            },
            headers: { 'Origin': 'http://localhost:3000' }
        });
        expect(res3.status()).toBe(200);
        const text3 = await res3.text();
        expect(text3).toContain('<Hangup/>'); // Should drop attempt-level duplicates

        // B. Transition call to completed status (using tenant_id query parameter so webhook resolves it)
        const statusRes = await request.post(`/api/voice/status?tenant_id=${testTenant}`, {
            form: {
                CallSid: callSid,
                CallStatus: 'completed',
                CallDuration: '45'
            },
            headers: { 'Origin': 'http://localhost:3000' }
        });
        expect([200, 204]).toContain(statusRes.status());

        // C. WhatsApp status transition (queued -> sent -> delivered)
        // 1. Send WhatsApp message during the call
        const waSendRes = await request.post(`/api/contact-center/voice/live/${callSid}/whatsapp`, {
            data: {
                template_name: 'hello_world',
                language_code: 'tr'
            },
            headers: headers
        });
        expect(waSendRes.status()).toBe(200);
        const waSendBody = await waSendRes.json();
        expect(waSendBody.status).toBe('ok');
        const msgSid = waSendBody.provider_message_id;
        expect(msgSid).toBeTruthy();

        // 2. Transition WhatsApp status callback (queued -> sent -> delivered)
        const transitionStatuses = ['queued', 'sent', 'delivered'];
        for (const status of transitionStatuses) {
            const callbackRes = await request.post('/api/voice/whatsapp/status', {
                form: {
                    MessageSid: msgSid,
                    MessageStatus: status
                },
                headers: { 'Origin': 'http://localhost:3000' }
            });
            expect(callbackRes.status()).toBe(204);
        }

        // 3. Verify call history via API
        const historyRes = await request.get('/api/contact-center/calls?reveal_phone=true', { headers: headers });
        expect(historyRes.status()).toBe(200);
        const historyBody = await historyRes.json();
        
        // Find our call by matching decrypted caller_phone
        const callRecord = historyBody.items?.find(c => c.caller_phone === '+905551112233');
        expect(callRecord).toBeTruthy();
        expect(callRecord.duration_seconds).toBe(45);
        expect(callRecord.direction).toBe('outbound');
        expect(callRecord.agent_id).toBeTruthy();

        // D. Cleanup: Delete the registered number mapping
        if (numberId) {
            const delRes = await request.delete(`/api/contact-center/voice/numbers/${numberId}`, { headers: headers });
            expect(delRes.status()).toBe(204);
        }
    });
});
