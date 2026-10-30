import { describe, expect, it } from 'vitest';
import { scheduleCells, scheduleOutsideGrid } from '../scheduledServiceGrid';
const day = '2026-10-30';
const hours = [8, 9, 10, 11];
const row = overrides => ({ id: 's', resource_id: 'r', status: 'booked', starts_at: `${day}T09:30:00+03:00`, ends_at: `${day}T10:15:00+03:00`, ...overrides });
describe('hotel-local half-open schedule grid', () => {
  it('covers fractional-hour overlaps once and includes the first visible label', () => {
    const cells = scheduleCells([row()], day, hours, 'resource_id');
    expect([...cells.keys()]).toEqual(['r@9', 'r@10']);
    expect(cells.get('r@9')[0].isStart).toBe(true);
  });
  it('includes an overnight carry-in and clips to the chosen hotel day', () => {
    const item = row({ starts_at: '2026-10-29T23:00:00+03:00', ends_at: `${day}T09:00:00+03:00` });
    expect([...scheduleCells([item], day, hours, 'resource_id').keys()]).toEqual(['r@8']);
    expect(scheduleOutsideGrid([item], day, hours)).toEqual([item]);
  });
  it('does not occupy the end boundary or cancelled services', () => {
    expect([...scheduleCells([row({ starts_at: `${day}T08:00:00+03:00`, ends_at: `${day}T09:00:00+03:00` })], day, hours, 'resource_id').keys()]).toEqual(['r@8']);
    expect(scheduleCells([row({ status: 'cancelled' })], day, hours, 'resource_id').size).toBe(0);
  });
});
