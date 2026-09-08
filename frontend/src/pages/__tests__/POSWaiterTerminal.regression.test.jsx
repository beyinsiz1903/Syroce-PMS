import { describe, expect, it } from 'vitest';

import { normalizeWaiterMenuItems } from '@/pages/POSWaiterTerminal';

describe('POS waiter menu regressions', () => {
  it('keeps unavailable products visible while excluding inactive products', () => {
    const items = normalizeWaiterMenuItems([
      { id: 'sold-out', name: 'QA Burger', price: '120', available: false, status: 'active' },
      { id: 'inactive', name: 'Eski ürün', price: 10, available: true, status: 'inactive' },
    ]);

    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      id: 'sold-out',
      item_name: 'QA Burger',
      unit_price: 120,
      available: false,
    });
  });
});
