import { expect, it } from 'vitest';
import { buildManagerDailyMetrics } from '../ManagerDailyReport';
import { operations } from './managerOperationsFixture';

it('requires authoritative actual-night metrics and never substitutes planned client bookings', () => {
  expect(buildManagerDailyMetrics({ day: '2026-10-26', operations: operations() }).occupiedRooms).toBe(25);
  expect(buildManagerDailyMetrics({ day: '2026-10-27', operations: operations() })).toBeNull();
  expect(buildManagerDailyMetrics({ day: '2026-10-26', bookings: [{ status: 'confirmed' }] })).toBeNull();
  expect(buildManagerDailyMetrics({ day: '2026-10-26', operations: { ...operations(), occupiedRooms: NaN } })).toBeNull();
  expect(buildManagerDailyMetrics({ day: '2026-10-26', operations: { ...operations(), basis: 'planned' } })).toBeNull();
});
