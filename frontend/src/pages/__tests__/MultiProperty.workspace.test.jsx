import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { axiosMock } = vi.hoisted(() => ({
  axiosMock: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock('axios', () => ({ default: axiosMock }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/adminTenantContext', () => ({ persistEnteredTenantContext: vi.fn() }));

import MultiProperty from '../MultiProperty';

const dashboard = {
  current_property_id: 'hotel-denizli',
  summary: {
    total_properties: 2,
    total_rooms: 240,
    avg_occupancy: 0,
    total_revenue: 0,
    total_revenue_by_currency: {},
  },
  properties: [
    { property_id: 'hotel-denizli', property_name: 'Denizli Oteli', total_rooms: 120, occupancy_pct: 0 },
    { property_id: 'hotel-fethiye', property_name: 'Fethiye Oteli', total_rooms: 120, occupancy_pct: 0 },
  ],
};

describe('MultiProperty workspace switching', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axiosMock.get.mockImplementation((url) => {
      if (url === '/multi-property/dashboard') return Promise.resolve({ data: dashboard });
      return Promise.resolve({ data: { properties: [], users: [] } });
    });
  });

  it('opens the current hotel and exposes sibling hotel switching', async () => {
    axiosMock.post.mockRejectedValue({ response: { data: { detail: 'Geçiş reddedildi' } } });
    render(<MemoryRouter><MultiProperty /></MemoryRouter>);

    const current = await screen.findByRole('button', { name: 'Denizli Oteli çalışma alanına geç' });
    const sibling = screen.getByRole('button', { name: 'Fethiye Oteli çalışma alanına geç' });

    expect(current).toBeEnabled();
    expect(sibling).toBeEnabled();

    fireEvent.click(current);
    expect(axiosMock.post).not.toHaveBeenCalled();

    fireEvent.click(sibling);
    await waitFor(() => expect(axiosMock.post).toHaveBeenCalledWith('/admin/tenants/hotel-fethiye/context'));
    await waitFor(() => expect(sibling).toBeEnabled());
  });
});
