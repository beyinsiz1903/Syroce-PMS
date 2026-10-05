import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { axiosGet } = vi.hoisted(() => ({ axiosGet: vi.fn() }));

vi.mock('axios', () => ({
  default: {
    get: axiosGet,
    post: vi.fn(),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import NoShowToday, { arrivalSourceLabel, normalizeArrival } from '@/pages/NoShowToday';

describe('NoShowToday', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosGet.mockImplementation((url) => {
      if (url === '/night-audit/business-date') {
        return Promise.resolve({ data: { business_date: '2026-08-30' } });
      }
      if (url.startsWith('/pms/arrivals?')) {
        return Promise.resolve({
          data: {
            bookings: [{
              id: 'booking-1',
              confirmation_number: 'HR-1001',
              guest_name: 'Özgür Aslan',
              room_number: '208',
              status: 'confirmed',
              source: {
                provider: 'hotelrunner',
                external_reservation_id: 'R487730646',
                connector_id: 'connector-1',
                import_record: { id: 'import-1' },
              },
              total_amount: 14000,
              check_in: '2026-08-30',
              check_out: '2026-08-31',
            }],
          },
        });
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });
  });

  afterEach(() => cleanup());

  it('normalizes HotelRunner lineage objects into render-safe source labels', () => {
    const source = { provider: 'hotelrunner', external_reservation_id: 'R1' };
    expect(arrivalSourceLabel({ source })).toBe('hotelrunner');
    expect(normalizeArrival({ source, guest_name: { name: 'Misafir' } })).toMatchObject({
      source: 'hotelrunner',
      guest_name: 'Misafir',
    });
  });

  it('renders an arrival whose source is an object without React error 31', async () => {
    render(
      <MemoryRouter>
        <NoShowToday />
      </MemoryRouter>,
    );

    expect(await screen.findByText('HR-1001')).toBeInTheDocument();
    expect(screen.getByText('hotelrunner')).toBeInTheDocument();
    expect(screen.getByText(/Özgür Aslan/)).toBeInTheDocument();
    await waitFor(() => expect(axiosGet).toHaveBeenCalledWith(
      '/pms/arrivals?start_date=2026-08-30&end_date=2026-08-30&limit=500',
    ));
  });
});
