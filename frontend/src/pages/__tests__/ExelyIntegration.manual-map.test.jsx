import { describe, expect, it } from 'vitest';

import { buildExelyManualMapPayload } from '@/pages/ExelyIntegration';

describe('Exely manual mapping payload', () => {
  it('accepts explicit provider codes and keeps per-field sync controls', () => {
    expect(buildExelyManualMapPayload({
      pms_room_type: ' Junior Suite ',
      exely_room_code: ' 5003301 ',
      exely_rate_plan_code: ' 10009740 ',
      exely_room_name: ' Suite ',
      sync_availability: false,
      sync_price: true,
      sync_restrictions: true
    }, [])).toEqual({
      pms_room_type: 'Junior Suite',
      exely_room_code: '5003301',
      exely_rate_plan_code: '10009740',
      pms_api_room_code: '',
      pms_api_rate_plan_code: '',
      exely_room_name: 'Suite',
      sync_availability: false,
      sync_price: true,
      sync_restrictions: true
    });
  });

  it('uses the discovered room name when the code is known', () => {
    const result = buildExelyManualMapPayload({
      pms_room_type: 'Standard',
      exely_room_code: '5003299',
      exely_rate_plan_code: '10009740',
      sync_availability: true,
      sync_price: true,
      sync_restrictions: false
    }, [{ code: '5003299', name: 'Standart' }]);

    expect(result.exely_room_name).toBe('Standart');
  });

  it('keeps ARI identifiers separate from inbound PMS API aliases', () => {
    const result = buildExelyManualMapPayload({
      pms_room_type: 'Standard',
      exely_room_code: '5003299',
      exely_rate_plan_code: '10009740',
      pms_api_room_code: ' 5001574 ',
      pms_api_rate_plan_code: ' 10003870 ',
      sync_availability: true,
      sync_price: true,
      sync_restrictions: true
    });
    expect(result.pms_api_room_code).toBe('5001574');
    expect(result.pms_api_rate_plan_code).toBe('10003870');
  });
});
