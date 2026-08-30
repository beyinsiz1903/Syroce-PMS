import { cleanup, render, screen, waitFor } from '@testing-library/react';
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

import DepartureList from '../DepartureList';

describe('DepartureList', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosGet.mockImplementation((url) => {
      if (url === '/night-audit/business-date') {
        return Promise.resolve({ data: { business_date: '2026-08-29' } });
      }
      if (url.startsWith('/frontdesk/departures?')) {
        return Promise.resolve({
          data: {
            departures: [{
              id: 'booking-1',
              guest_name: 'Özgür Aslan',
              guest_phone: 'SYR1:encrypted-contact-value-that-must-not-render',
              room_number: '208',
              total_amount: 14000,
              balance: 7000,
              check_out_time: '12:00',
            }],
          },
        });
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });
  });

  afterEach(() => cleanup());

  it('uses the PMS business date and hides encrypted contact values', async () => {
    render(<DepartureList />);

    expect(await screen.findByText(/Özgür Aslan/)).toBeInTheDocument();
    expect(screen.queryByText(/SYR1:/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Çıkış Yap/i })).toBeDisabled();
    await waitFor(() => expect(screen.getByDisplayValue('2026-08-29')).toBeInTheDocument());
  });
});
