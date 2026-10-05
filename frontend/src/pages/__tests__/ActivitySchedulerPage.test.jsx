import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));

vi.mock('@/api/axios', () => ({
  default: {
    get: apiGet,
    post: vi.fn(),
  },
}));

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

import ActivitySchedulerPage from '@/pages/ActivitySchedulerPage';

describe('ActivitySchedulerPage', () => {
  beforeEach(() => {
    apiGet.mockReset();
  });

  afterEach(() => cleanup());

  it('explains the module and guides an unconfigured hotel through setup', async () => {
    apiGet.mockImplementation((url) => {
      if (url === '/night-audit/business-date') return Promise.resolve({ data: { business_date: '2026-08-29' } });
      if (url === '/activities' || url === '/activities/resources' || url === '/activities/bookings') {
        return Promise.resolve({ data: [] });
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });

    render(<ActivitySchedulerPage />);

    expect(await screen.findByText('Bu ekran oda rezervasyonu için değildir.')).toBeInTheDocument();
    expect(screen.getByTestId('activity-setup-empty-state')).toBeInTheDocument();
    expect(screen.getByTestId('button-new-activity-booking')).toBeDisabled();
    await waitFor(() => expect(screen.getByTestId('input-schedule-date')).toHaveValue('2026-08-29'));
  });

  it('shows the resolved PMS guest name instead of a technical guest id', async () => {
    apiGet.mockImplementation((url) => {
      if (url === '/night-audit/business-date') return Promise.resolve({ data: { business_date: '2026-08-29' } });
      if (url === '/activities') {
        return Promise.resolve({ data: [{ id: 'activity-1', name: 'Tenis Dersi', type: 'tennis' }] });
      }
      if (url === '/activities/resources') {
        return Promise.resolve({ data: [{ id: 'resource-1', name: 'Kort 1', kind: 'venue' }] });
      }
      if (url === '/activities/bookings') {
        return Promise.resolve({ data: [{
          id: 'booking-1',
          activity_id: 'activity-1',
          resource_id: 'resource-1',
          guest_id: 'guest-technical-id',
          guest_name: 'Özgür Aslan',
          starts_at: '2026-08-29T10:00:00+03:00',
          ends_at: '2026-08-29T11:00:00+03:00',
          status: 'booked',
        }] });
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });

    render(<ActivitySchedulerPage />);

    expect(await screen.findByTitle(/Özgür Aslan/)).toBeInTheDocument();
    expect(screen.queryByTitle(/guest-technical-id/)).not.toBeInTheDocument();
  });
});
