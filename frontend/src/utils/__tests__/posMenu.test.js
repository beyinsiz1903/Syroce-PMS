import { describe, expect, it } from 'vitest';

import { normalizePOSMenuItem, normalizePOSMenuItems } from '@/utils/posMenu';

describe('POS menu normalization', () => {
  it('accepts the canonical backend item_name and unit_price fields', () => {
    expect(normalizePOSMenuItem({ item_id: 'coffee', item_name: 'Türk kahvesi', unit_price: '95.50' })).toMatchObject({
      id: 'coffee',
      name: 'Türk kahvesi',
      price: 95.5,
    });
  });

  it('keeps legacy fields and removes unusable rows', () => {
    expect(normalizePOSMenuItems([{ id: 'tea', name: 'Çay', price: 40 }, { name: 'Eksik' }])).toEqual([
      expect.objectContaining({ id: 'tea', name: 'Çay', price: 40 }),
    ]);
  });
});
