import { describe, expect, it } from 'vitest';

import { availableMaintenanceTransitions } from '@/pages/MaintenanceWorkOrders';

describe('MaintenanceWorkOrders transitions', () => {
  it('does not reopen completed or cancelled work orders from the UI', () => {
    expect(availableMaintenanceTransitions('open')).toEqual(['in_progress', 'completed']);
    expect(availableMaintenanceTransitions('in_progress')).toEqual(['completed']);
    expect(availableMaintenanceTransitions('completed')).toEqual([]);
    expect(availableMaintenanceTransitions('cancelled')).toEqual([]);
  });
});
