import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const source = readFileSync(resolve(process.cwd(), 'src/pages/ReservationCalendar.jsx'), 'utf8');

describe('ReservationCalendar reference data scheduling', () => {
  it('defers non-operational reference lists until the browser is idle', () => {
    expect(source).toContain("import { runIdle } from '@/lib/idle'");
    expect(source).toContain('runIdle(() => {');
    expect(source).toContain("axios.get('/pms/guests')");
    expect(source).toContain("axios.get('/companies')");
  });

  it('keeps sellable calendar data on the immediate critical path', () => {
    expect(source).toContain("axios.get('/pms/rooms')");
    expect(source).toContain("axios.get('/pms/room-blocks?status=active')");
    expect(source).toContain("axios.get(`/pms/bookings?start_date=${startDate.toISOString().split('T')[0]}&end_date=${endDate.toISOString().split('T')[0]}&limit=500`)");
  });

  it('hydrates calendar rates without blocking the first room grid paint', () => {
    const ratesStart = source.indexOf('const calendarRatesPromise = axios.get(');
    const criticalStart = source.indexOf('const [roomsRes, bookingsRes, blocksRes] = await Promise.all([', ratesStart);
    const dataReady = source.indexOf('calendarDataLoadedRef.current = true;', criticalStart);
    const ratesHydration = source.indexOf('void calendarRatesPromise.then(', dataReady);

    expect(ratesStart).toBeGreaterThan(-1);
    expect(criticalStart).toBeGreaterThan(ratesStart);
    expect(dataReady).toBeGreaterThan(criticalStart);
    expect(ratesHydration).toBeGreaterThan(dataReady);
  });
});
