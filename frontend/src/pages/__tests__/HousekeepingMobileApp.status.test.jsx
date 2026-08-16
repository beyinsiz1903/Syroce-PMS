import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const axiosGet = vi.fn();
const axiosPut = vi.fn();

vi.mock('axios', () => ({
  default: {
    get: (...args) => axiosGet(...args),
    put: (...args) => axiosPut(...args),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import HousekeepingMobileApp, { getRoomHousekeepingStatus } from '@/pages/HousekeepingMobileApp';

describe('HousekeepingMobileApp room status', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosPut.mockReset();
  });

  afterEach(cleanup);

  it('prefers the canonical housekeeping status over the legacy value', () => {
    expect(getRoomHousekeepingStatus({ housekeeping_status: 'cleaning', hk_status: 'dirty' })).toBe('cleaning');
    expect(getRoomHousekeepingStatus({ hk_status: 'inspected' })).toBe('inspected');
  });

  it('renders the persisted canonical status after a quick update', async () => {
    axiosGet
      .mockResolvedValueOnce({
        data: {
          rooms: [{
            id: 'room-104',
            room_number: '104',
            room_type: 'Standard',
            floor: '1',
            housekeeping_status: 'dirty',
            hk_status: 'dirty',
          }],
        },
      })
      .mockResolvedValueOnce({
        data: {
          rooms: [{
            id: 'room-104',
            room_number: '104',
            room_type: 'Standard',
            floor: '1',
            housekeeping_status: 'cleaning',
            hk_status: 'dirty',
          }],
        },
      });
    axiosPut.mockResolvedValue({ data: { new_status: 'cleaning' } });

    render(<HousekeepingMobileApp user={{ name: 'Test Staff' }} />);

    expect(await screen.findByText('dirty')).toBeInTheDocument();
    fireEvent.click(screen.getByTitle('Hızlı: Kontrol listesi olmadan temizleniyor olarak işaretle'));

    await waitFor(() => expect(axiosPut).toHaveBeenCalledWith(
      '/pms/housekeeping/rooms/room-104/status',
      { status: 'cleaning' },
    ));
    expect(await screen.findByText('cleaning')).toBeInTheDocument();
    expect(screen.queryByText('dirty')).not.toBeInTheDocument();
  });
});
