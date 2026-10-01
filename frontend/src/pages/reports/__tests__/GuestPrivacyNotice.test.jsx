import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import GuestPrivacyNotice from '../GuestPrivacyNotice';

describe('GuestPrivacyNotice', () => {
  it('shows the server-enforced visibility summary', () => {
    render(<GuestPrivacyNotice privacy={{
      server_side_enforced: true,
      full_fields: ['name'],
      masked_fields: ['phone', 'email'],
      hidden_fields: ['national_id'],
    }} />);

    expect(screen.getByText('Veri koruması bu rapora uygulandı')).toBeInTheDocument();
    expect(screen.getByText('Tam görünen: 1 · Maskeli: 2 · Gizli: 1')).toBeInTheDocument();
  });

  it('renders nothing when the backend did not enforce a profile', () => {
    const { container } = render(<GuestPrivacyNotice privacy={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
