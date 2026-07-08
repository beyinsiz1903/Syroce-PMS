import { test, expect } from '@playwright/test';
import { makeApi } from './fixtures/api.js';
import { createTestBooking, checkInBooking, checkoutBooking, todayDates, pickAvailableRoom } from './fixtures/pms-flow.js';
import { factory } from './fixtures/data-factory.js';

test.describe('PMS-UAT-002: Check-in / Check-out', () => {
    test('Full Check-in to Check-out flow', async ({ baseURL }) => {
        const api = await makeApi(baseURL);
        const dates = todayDates(1);
        const pick = await pickAvailableRoom(api, dates);
        test.skip(!pick.ok, 'No available room');
        
        const created = await createTestBooking(api, { roomId: pick.room.id, guestName: factory.guestName(), ...dates });
        expect(created.ok).toBe(true);
        
        const ci = await checkInBooking(api, created.bookingId);
        expect(ci.ok).toBe(true);
        
        const co = await checkoutBooking(api, created.bookingId, true);
        expect(co.ok).toBe(true);
        
        await api.dispose();
    });
});
