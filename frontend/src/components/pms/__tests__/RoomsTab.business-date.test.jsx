import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import RoomsTab from '@/components/pms/RoomsTab';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => (key === 'pms.rooms' ? 'Odalar' : key) }),
}));

afterEach(() => cleanup());

const room = {
  id: 'room-208',
  room_number: '208',
  room_type: 'Suit Oda',
  floor: 2,
  capacity: 3,
  status: 'available',
};

const booking = {
  id: 'booking-28',
  room_number: '208',
  guest_name: 'Özgür Test',
  check_in: '2026-08-28',
  check_out: '2026-08-30',
  status: 'confirmed',
  total_amount: 14000,
  paid_amount: 0,
};

describe('RoomsTab PMS business date', () => {
  it('does not expose a future arrival relative to the open PMS day', () => {
    render(
      <RoomsTab
        rooms={[room]}
        bookings={[booking]}
        businessDate="2026-08-23"
      />,
    );

    const card = screen.getByTestId('room-card-208');
    expect(within(card).queryByText('Özgür Test')).not.toBeInTheDocument();
    expect(within(card).queryByText('Giriş Bekleniyor')).not.toBeInTheDocument();
    expect(within(card).queryByRole('button', { name: 'Giriş' })).not.toBeInTheDocument();
  });

  it('shows the arrival when the PMS day reaches its check-in date', () => {
    render(
      <RoomsTab
        rooms={[room]}
        bookings={[booking]}
        businessDate="2026-08-28"
      />,
    );

    const card = screen.getByTestId('room-card-208');
    expect(within(card).getByText('Özgür Test')).toBeInTheDocument();
    expect(within(card).getByText('Giriş Bekleniyor')).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Giriş' })).toBeInTheDocument();
  });

  it('allows a dirty vacant room to be booked and marked clean independently', async () => {
    const axios = (await import('axios')).default;
    axios.put.mockResolvedValueOnce({ data: { success: true } });
    const onDataRefresh = vi.fn();

    render(
      <RoomsTab
        rooms={[{ ...room, room_number: '109', status: 'dirty' }]}
        bookings={[]}
        businessDate="2026-08-28"
        onDataRefresh={onDataRefresh}
      />,
    );

    expect(screen.getByRole('button', { name: 'Rezervasyon Yap' })).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('mark-room-clean-109'));

    await waitFor(() => {
      expect(axios.put).toHaveBeenCalledWith(
        '/housekeeping/room/room-208/status',
        null,
        { params: { new_status: 'available' } },
      );
      expect(onDataRefresh).toHaveBeenCalledTimes(1);
    });
  });
});
