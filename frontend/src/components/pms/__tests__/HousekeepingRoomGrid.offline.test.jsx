import { describe, expect, it } from 'vitest';

import { withOptimisticHousekeepingStatus } from '@/components/pms/HousekeepingRoomGrid';

describe('HousekeepingRoomGrid offline status updates', () => {
  it('updates the field the room grid renders for single and bulk selections', () => {
    const rooms = [
      { id: '101', housekeeping_status: 'dirty' },
      { id: '102', housekeeping_status: 'clean' },
    ];

    expect(withOptimisticHousekeepingStatus(rooms, '101', 'clean')).toEqual([
      { id: '101', housekeeping_status: 'clean' },
      { id: '102', housekeeping_status: 'clean' },
    ]);
    expect(withOptimisticHousekeepingStatus(rooms, ['101', '102'], 'inspected')).toEqual([
      { id: '101', housekeeping_status: 'inspected' },
      { id: '102', housekeeping_status: 'inspected' },
    ]);
  });
});
