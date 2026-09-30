import { describe, expect, it } from 'vitest';

import { normalizeKitchenOrders } from '@/pages/KitchenDisplay';

describe('KitchenDisplay order contract', () => {
  it('normalizes v2 single-line kitchen tickets into visible items', () => {
    expect(normalizeKitchenOrders([{
      id: 'ticket-1',
      item_name: 'Izgara',
      quantity: 2,
      special_instructions: 'Az pişmiş',
      station: 'hot_kitchen',
    }])[0].items).toEqual([{
      id: 'ticket-1',
      name: 'Izgara',
      quantity: 2,
      notes: 'Az pişmiş',
      station: 'hot_kitchen',
    }]);
  });

  it('preserves grouped tickets while normalizing item labels', () => {
    expect(normalizeKitchenOrders([{ id: 'ticket-2', items: [{ item_name: 'Çorba', quantity: 1 }] }])[0].items[0].name).toBe('Çorba');
  });
});
