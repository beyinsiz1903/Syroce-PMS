import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import RoomsTab, { formatCleaningDuration } from '@/components/pms/RoomsTab';

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
  it('formats long-running cleaning work in a human-readable duration', () => {
    expect(formatCleaningDuration(30)).toBe('30 dk');
    expect(formatCleaningDuration(90)).toBe('1 sa 30 dk');
    expect(formatCleaningDuration(163875)).toBe('113 gün');
  });

  it('does not render a stale cleaning task as a raw minute counter', () => {
    render(
      <RoomsTab
        rooms={[{
          ...room,
          room_number: '105',
          status: 'cleaning',
          housekeeping: {
            state: 'in_progress',
            estimated_minutes: 30,
            elapsed_minutes: 163875,
            progress_pct: 100,
          },
        }]}
        bookings={[]}
        businessDate="2026-08-28"
      />,
    );

    const cleaning = screen.getByTestId('room-cleaning-105');
    expect(cleaning).toHaveTextContent('113 gün açık');
    expect(cleaning).toHaveTextContent('24 saati aşan görev');
    expect(cleaning).not.toHaveTextContent('163875');
  });

  it('uses the room state when housekeeping task synchronization lags', () => {
    render(
      <RoomsTab
        rooms={[{
          ...room,
          room_number: '104',
          status: 'cleaning',
          housekeeping: {
            state: 'queued',
            estimated_minutes: 30,
          },
        }]}
        bookings={[]}
        businessDate="2026-08-28"
      />,
    );

    const cleaning = screen.getByTestId('room-cleaning-104');
    expect(cleaning).toHaveTextContent('pms.rooms.statusCleaning');
    expect(cleaning).not.toHaveTextContent('Temizlik bekliyor');
  });

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

    expect(screen.getByRole('button', { name: 'pms.rooms.makeBooking' })).toBeInTheDocument();
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

  it('opens the same room-block action from a room-card context menu', () => {
    render(
      <RoomsTab
        rooms={[room]}
        bookings={[]}
        businessDate="2026-08-28"
      />,
    );

    fireEvent.contextMenu(screen.getByTestId('room-card-208'), { clientX: 120, clientY: 180 });

    expect(screen.getByRole('menu', { name: 'Oda hızlı işlemleri' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Odayı blokla / arıza bildir' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Odayı satışa kapat');
  });

  it('marks a vacant room dirty from the room-card context menu', async () => {
    const axios = (await import('axios')).default;
    axios.put.mockResolvedValueOnce({ data: { success: true } });
    const onDataRefresh = vi.fn();

    render(
      <RoomsTab
        rooms={[room]}
        bookings={[]}
        businessDate="2026-08-28"
        onDataRefresh={onDataRefresh}
      />,
    );

    fireEvent.contextMenu(screen.getByTestId('room-card-208'), { clientX: 120, clientY: 180 });
    fireEvent.click(screen.getByRole('menuitem', { name: 'Kirli olarak işaretle' }));

    await waitFor(() => {
      expect(axios.put).toHaveBeenCalledWith(
        '/housekeeping/room/room-208/status',
        null,
        { params: { new_status: 'dirty' } },
      );
      expect(onDataRefresh).toHaveBeenCalledTimes(1);
    });
  });
});
