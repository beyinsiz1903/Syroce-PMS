import { test, expect } from '@playwright/test';
import { makeApi } from './fixtures/api.js';
import { createTestBooking, cancelBooking, todayDates, pickAvailableRoom } from './fixtures/pms-flow.js';
import { factory } from './fixtures/data-factory.js';

test.describe('PMS-UAT-001: Reservation Create, Modify, Cancel', () => {
    test('Create and Cancel Reservation', async ({ baseURL }) => {
        const api = await makeApi(baseURL);
        const dates = todayDates(2);
        const pick = await pickAvailableRoom(api, dates);
        test.skip(!pick.ok, 'No available room found');
        
        const guestName = factory.guestName();
        const created = await createTestBooking(api, {
            roomId: pick.room.id,
            guestName,
            check_in: dates.check_in,
            check_out: dates.check_out,
        });
        expect(created.ok).toBe(true);
        expect(created.bookingId).toBeTruthy();

        const canceled = await cancelBooking(api, created.bookingId, 'UAT 001 cancellation');
        expect(canceled.ok).toBe(true);
        
        await api.dispose();
    });
});
