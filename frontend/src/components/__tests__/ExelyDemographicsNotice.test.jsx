import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ExelyDemographicsNotice from '../ExelyDemographicsNotice';
import { exelyDemographicsUnverified } from '@/utils/exelyDemographics';

describe('Exely demographic provenance', () => {
  it.each(['channel', 'source_channel', 'booking_source', 'source_provider', 'ota_channel'])('treats legacy %s records as unverified', field => {
    const booking = { [field]: 'EXELY', adults: 3, children: 0 };
    expect(exelyDemographicsUnverified(booking)).toBe(true);
    render(<ExelyDemographicsNotice booking={booking} />);
    expect(screen.getByRole('status')).toHaveTextContent('yetişkin/çocuk ayrımı');
  });

  it('does not affect direct bookings or infer child ages from a note', () => {
    expect(exelyDemographicsUnverified({ channel: 'direct', special_requests: 'child age 6' })).toBe(false);
    const { container } = render(<ExelyDemographicsNotice booking={{ channel: 'direct' }} />);
    expect(container).toBeEmptyDOMElement();
  });

  const verified = {
    booking_source: 'exely', property_id: '501694', provider_group_reservation_id: 'synthetic', provider_version_key: 'version-a',
    adults: 2, children: 1, children_ages: [6], guests_count: 3,
    check_in: '2026-11-10', check_out: '2026-11-11', room_type: 'Deluxe', currency: 'USD', total_amount: 120,
    exely_demographics: { status: 'verified', source: 'exely_read_reservation_v1', property_id: '501694', reservation_id: 'synthetic', provider_version_key: 'version-a', adults: 2, children_ages: [6], check_in: '2026-11-10', check_out: '2026-11-11', room_type: 'Deluxe', currency: 'USD', total_amount: 120 },
  };

  it('accepts only a matching independently verified PMS readback', () => {
    expect(exelyDemographicsUnverified(verified)).toBe(false);
    const { container } = render(<ExelyDemographicsNotice booking={verified} />);
    expect(container).toBeEmptyDOMElement();
  });

  it.each([
    { provider_version_key: 'newer-version' }, { property_id: 'different-property' },
    { adults: 3 }, { children_ages: [7] }, { children: 0 }, { guests_count: 2 },
    { provider_group_reservation_id: 'different-booking' }, { exely_demographics: { status: 'verified' } },
    { check_in: '2026-12-10' }, { check_out: '2026-12-11' }, { currency: 'EUR' }, { total_amount: 121 }, { room_type: 'Suite' },
  ])('keeps stale, partial and manually altered provenance unverified: %j', drift => {
    expect(exelyDemographicsUnverified({ ...verified, ...drift })).toBe(true);
  });
});
