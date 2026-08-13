import { describe, expect, it } from 'vitest';

import { buildExelyAutoMapPayload, hasCompleteExelyRatePlanSelection } from '@/pages/ExelyIntegration';

describe('Exely auto-map rate-plan safety', () => {
  const suggestions = [{
    pms_room_type: 'Standard',
    provider_room_code: 'room-a',
    provider_room_name: 'Standard provider room',
  }];
  const ratePlans = [
    { code: 'plan-a', name: 'Plan A' },
    { code: 'plan-b', name: 'Plan B' },
  ];

  it('does not silently select the first provider rate plan', () => {
    const mappings = buildExelyAutoMapPayload(suggestions, {}, ratePlans);

    expect(mappings[0].provider_rate_plan_code).toBe('');
    expect(hasCompleteExelyRatePlanSelection(mappings)).toBe(false);
  });

  it('transfers the operator-selected rate plan', () => {
    const mappings = buildExelyAutoMapPayload(suggestions, { 'room-a': 'plan-b' }, ratePlans);

    expect(mappings[0]).toMatchObject({
      provider_rate_plan_code: 'plan-b',
      provider_rate_plan_name: 'Plan B',
    });
    expect(hasCompleteExelyRatePlanSelection(mappings)).toBe(true);
  });
});
