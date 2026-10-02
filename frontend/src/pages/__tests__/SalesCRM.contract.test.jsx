import { describe, expect, it } from 'vitest';

import { buildActivityPayload } from '@/pages/SalesCRM';

describe('Sales CRM activity payload', () => {
  const draft = {
    activity_type: 'call',
    subject: 'Teklif görüşmesi',
    description: 'Kahvaltı ve transfer seçenekleri konuşuldu.',
  };

  it('keeps a planned follow-up in the activity saved to the backend', () => {
    expect(buildActivityPayload('lead-42', {
      ...draft,
      follow_up_at: '2026-10-04T10:30',
    })).toEqual({
      lead_id: 'lead-42',
      ...draft,
      follow_up_at: '2026-10-04T10:30',
    });
  });

  it('does not send an empty follow-up as a scheduled task', () => {
    expect(buildActivityPayload('lead-42', { ...draft, follow_up_at: '' })).toEqual({
      lead_id: 'lead-42',
      ...draft,
    });
  });
});
