import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RoomChangeTab } from '@/pages/reservation-detail/OperationTabs';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock('axios', () => ({ default: { get, post } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn() }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

describe('RoomChangeTab upgrade pricing', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    get.mockResolvedValue({
      data: {
        room_types: [
          {
            type: 'Suite',
            base_price: 5000,
            rooms: [{ id: 'room-suite', room_number: '201', floor: 2, is_available: true }],
          },
        ],
      },
    });
    post.mockResolvedValue({ data: { success: true } });
  });

  it('forces a price decision and posts the total upgrade difference', async () => {
    render(
      <RoomChangeTab
        booking={{
          id: 'booking-a',
          room_id: 'room-standard',
          room_number: '101',
          check_in: '2026-09-26',
          check_out: '2026-09-27',
          total_amount: 3000,
          currency: 'TL',
        }}
        room={{ room_type: 'Standard', room_number: '101' }}
        roomMoves={[]}
        onRefresh={vi.fn()}
      />,
    );

    fireEvent.change(await screen.findByTestId('room-change-type-select'), { target: { value: 'Suite' } });
    fireEvent.change(screen.getByTestId('room-change-room-select'), { target: { value: 'room-suite' } });
    fireEvent.change(screen.getByTestId('room-change-reason-select'), { target: { value: 'Upgrade' } });

    expect(screen.getByText(/Üst kategori oda seçildi/)).toBeInTheDocument();
    expect(screen.getByTestId('room-change-submit-btn')).toBeDisabled();

    fireEvent.click(screen.getByLabelText(/Önerilen toplam farkı uygula/));
    expect(screen.getByTestId('room-change-submit-btn')).toBeEnabled();
    fireEvent.click(screen.getByTestId('room-change-submit-btn'));

    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/pms/reservations/booking-a/room-change',
      expect.objectContaining({ new_room_id: 'room-suite', reason: 'Upgrade', extra_charge: 2000 }),
    ));
  });
});
