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
    pickup_7d: 4,
    arrivals_today: 2,
    departures_today: 1,
  },
  business_date: '2026-09-30',
  business_dates: ['2026-09-30'],
  business_dates_aligned: true,
  properties: [
    { property_id: 'hotel-denizli', property_name: 'Denizli Oteli', total_rooms: 120, occupied_rooms: 40, occupancy_pct: 33.3, pickup_7d: 3, arrivals_today: 2, departures_today: 1, currency: 'TRY', today_revenue_by_currency: { TRY: 1000 }, room_revenue_by_currency: { TRY: 900 }, adr_by_currency: { TRY: 22.5 }, integrations: {} },
    { property_id: 'hotel-fethiye', property_name: 'Fethiye Oteli', total_rooms: 120, occupied_rooms: 20, occupancy_pct: 16.7, pickup_7d: 1, arrivals_today: 0, departures_today: 0, currency: 'EUR', today_revenue_by_currency: { EUR: 100 }, room_revenue_by_currency: { EUR: 80 }, adr_by_currency: { EUR: 4 }, integrations: {} },
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

  it('keeps currencies separate and opens a real property quick view', async () => {
    render(<MemoryRouter><MultiProperty /></MemoryRouter>);

    expect(await screen.findByTestId('chain-command-center')).toBeInTheDocument();
    expect(screen.getAllByText(/₺1\.000/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/€100/).length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByRole('button', { name: /Hızlı görünüm/i })[0]);
    expect(await screen.findByRole('dialog')).toHaveTextContent('Denizli Oteli');
    expect(screen.getByRole('dialog')).toHaveTextContent('Bugünkü operasyon');
  });

  it('uses room revenue terminology and blocks mixed-day chain ADR/RevPAR', async () => {
    axiosMock.get.mockImplementation((url) => {
      if (url === '/multi-property/dashboard') {
        return Promise.resolve({
          data: {
            ...dashboard,
            business_date: null,
            business_dates: ['2026-09-29', '2026-09-30'],
            business_dates_aligned: false,
          },
        });
      }
      return Promise.resolve({ data: { properties: [], users: [] } });
    });

    render(<MemoryRouter><MultiProperty /></MemoryRouter>);

    expect(await screen.findByRole('alert')).toHaveTextContent('Tesislerin açık PMS iş günleri farklı');
    expect(screen.queryByText('Oda geliri / satılan oda')).not.toBeInTheDocument();
    expect(screen.getAllByText('İş günleri eşitlenmeli')).toHaveLength(2);
    expect(screen.queryByText('Tahsilat / dolu oda')).not.toBeInTheDocument();
    expect(screen.queryByText('Tahsilat / toplam oda')).not.toBeInTheDocument();
  });
});
