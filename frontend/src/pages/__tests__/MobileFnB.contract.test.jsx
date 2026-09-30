import { describe, expect, it } from 'vitest';

import { normalizeMobilePOSOutlets } from '@/pages/MobileFnB';

describe('MobileFnB outlet contract', () => {
  it('maps canonical outlet fields to the mobile cards', () => {
    expect(normalizeMobilePOSOutlets([{
      id: 'outlet-1',
      outlet_name: 'Teras Restoran',
      outlet_type: 'restaurant',
      opening_hours: '07:00–23:00',
      status: 'active',
    }])).toEqual([expect.objectContaining({
      id: 'outlet-1',
      name: 'Teras Restoran',
      type: 'restaurant',
      operating_hours: '07:00–23:00',
    })]);
  });

  it('keeps active legacy records and removes inactive outlets', () => {
    expect(normalizeMobilePOSOutlets([
      { id: 'legacy', name: 'Lobi Bar', type: 'bar', operating_hours: '24 saat' },
      { id: 'inactive', outlet_name: 'Kapalı Kafe', status: 'inactive' },
    ])).toEqual([
      expect.objectContaining({ id: 'legacy', name: 'Lobi Bar', type: 'bar', operating_hours: '24 saat' }),
    ]);
  });
});
