import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiGet = vi.fn();

vi.mock('@/api/axios', () => ({
  default: {
    get: (...args) => apiGet(...args),
    post: vi.fn(),
  },
}));

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

import BlockManagementPage from '@/pages/BlockManagementPage';

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}

describe('BlockManagementPage professional workspace', () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiGet.mockImplementation((url) => {
      if (url === '/block-mgmt/summary') {
        return Promise.resolve({
          data: {
            blocks: [{
              id: 'block-1',
              group_name: 'Bahar Tur Grubu',
              check_in: '2026-09-10',
              cutoff_date: '2026-09-03',
              total_rooms: 12,
              rooms_picked_up: 7,
              washed_count: 2,
              pickup_pct: 58.3,
            }],
          },
        });
      }
      if (url === '/block-mgmt/cutoff-alerts') {
        return Promise.resolve({ data: { alerts: [] } });
      }
      return Promise.reject(new Error(`Unexpected GET: ${url}`));
    });
  });

  it('explains the inventory workflow using hotel-operation language', async () => {
    render(
      <MemoryRouter initialEntries={['/block-management']}>
        <BlockManagementPage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Bu ekran ne işe yarar?')).toBeInTheDocument();
    expect(screen.getByText('Kontenjanı ayırın')).toBeInTheDocument();
    expect(screen.getByText('Kullanımı izleyin')).toBeInTheDocument();
    expect(screen.getByText('Kalanı satışa açın')).toBeInTheDocument();
    expect(screen.queryByText(/group_blocks/)).not.toBeInTheDocument();
    expect(screen.queryByText(/cutoff\/pickup\/wash/i)).not.toBeInTheDocument();

    await waitFor(() => expect(screen.getByText('Bahar Tur Grubu')).toBeInTheDocument());
    const summary = within(screen.getByTestId('block-summary'));
    expect(summary.getByText('Ayrılan oda')).toBeInTheDocument();
    expect(summary.getByText('Kullanılan oda')).toBeInTheDocument();
    expect(summary.getByText('Kalan oda')).toBeInTheDocument();
    expect(summary.getByText('Satışa dönen')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Son bırakma' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Kullanım Detayı/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Oda Bırak/ })).toBeInTheDocument();
  });

  it('routes inventory users to the existing group-reservations workspace', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/block-management']}>
        <BlockManagementPage />
        <LocationProbe />
      </MemoryRouter>,
    );

    await user.click(screen.getByTestId('button-group-reservations'));
    expect(screen.getByTestId('location')).toHaveTextContent('/group-bookings-manage');
  });
});
