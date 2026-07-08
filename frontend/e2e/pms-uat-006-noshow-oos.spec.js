import { test, expect } from '@playwright/test';
import { makeApi } from './fixtures/api.js';
import { createTestBooking, noShowBooking, todayDates, pickAvailableRoom } from './fixtures/pms-flow.js';
import { factory } from './fixtures/data-factory.js';

test.describe('PMS-UAT-006: No Show', () => {
    test('Mark booking as no-show', async ({ baseURL }) => {
        const api = await makeApi(baseURL);
        const dates = todayDates(1);
        const pick = await pickAvailableRoom(api, dates);
        test.skip(!pick.ok, 'No available room');
        
        const created = await createTestBooking(api, { roomId: pick.room.id, guestName: factory.guestName(), ...dates });
        expect(created.ok).toBe(true);
        
        const ns = await noShowBooking(api, created.bookingId);
        expect(ns.ok).toBe(true);
        
        await api.dispose();
    });
});
