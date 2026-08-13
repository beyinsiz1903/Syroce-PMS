import { describe, expect, it, vi } from 'vitest';

vi.mock('../lazyPages', () => ({
  ReservationCalendar: 'ReservationCalendar',
  ReservationLineage: 'ReservationLineage',
  GroupBookingsPage: 'GroupBookingsPage',
  DepositTrackingPage: 'DepositTrackingPage',
  GroupFolioPage: 'GroupFolioPage',
  NoShowAnalytics: 'NoShowAnalytics',
  ArrivalList: 'ArrivalList',
  DepartureList: 'DepartureList',
  NoShowToday: 'NoShowToday',
}));

import { reservationRoutes } from '../reservations';

describe('reservationRoutes', () => {
  it('uses the canonical group booking screen for both supported URLs', () => {
    const routes = reservationRoutes({ p: (component) => ({ component }) });
    const primary = routes.find((route) => route.path === '/group-bookings-manage');
    const alias = routes.find((route) => route.path === '/group-reservations');

    expect(alias.component).toBe(primary.component);
    expect(alias.wrapLayout).toBe(true);
    expect(alias.layoutModule).toBe('group-bookings');
  });
});
