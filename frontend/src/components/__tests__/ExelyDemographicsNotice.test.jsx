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
});
