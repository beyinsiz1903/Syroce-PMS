import { test, expect } from '@playwright/test';
import { makeApi } from './fixtures/api.js';
import { createTestBooking, checkInBooking, recordPayment, todayDates, pickAvailableRoom } from './fixtures/pms-flow.js';
import { factory } from './fixtures/data-factory.js';

test.describe('PMS-UAT-007: Payment / Refund', () => {
    test('Record Virtual POS payment on Folio', async ({ baseURL }) => {
        const api = await makeApi(baseURL);
        const dates = todayDates(1);
        const pick = await pickAvailableRoom(api, dates);
        test.skip(!pick.ok, 'No available room');
        
        const created = await createTestBooking(api, { roomId: pick.room.id, guestName: factory.guestName(), ...dates });
        expect(created.ok).toBe(true);
        
        const ci = await checkInBooking(api, created.bookingId);
        expect(ci.ok).toBe(true);
        
        const pay = await recordPayment(api, created.bookingId, { amount: 100, method: 'card', payment_type: 'interim' });
        expect(pay.ok).toBe(true);
        
        await api.dispose();
    });
});
