import { test, expect } from '@playwright/test';
import { makeApi } from './fixtures/api.js';
import { createTestBooking, checkInBooking, roomMove, pickNAvailableRooms, todayDates } from './fixtures/pms-flow.js';
import { factory } from './fixtures/data-factory.js';

test.describe('PMS-UAT-003: Room Move / Upgrade', () => {
    test('Room Move flow', async ({ baseURL }) => {
        const api = await makeApi(baseURL);
        const dates = todayDates(1);
        const pick = await pickNAvailableRooms(api, dates, 2);
        test.skip(!pick.ok, 'Needs 2 available rooms');
        
        const [roomA, roomB] = pick.rooms;
        const created = await createTestBooking(api, { roomId: roomA.id, guestName: factory.guestName(), ...dates });
        expect(created.ok).toBe(true);
        
        const ci = await checkInBooking(api, created.bookingId);
        expect(ci.ok).toBe(true);
        
        const mv = await roomMove(api, created.bookingId, roomB.id);
        expect(mv.ok).toBe(true);
        
        await api.dispose();
    });
});
