import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { RoomBlockCreateDialog } from '@/components/pms/RoomBlockDialogs';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key, fallback) => (typeof fallback === 'string' ? fallback : _key),
  }),
}));

afterEach(() => cleanup());

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

describe('RoomBlockCreateDialog', () => {
  it('selects a room from the rooms supplied by the PMS module', async () => {
    const room = { id: 'room-test', room_number: 'QT2ED0', room_type: 'standard' };
    const setSelectedRoom = vi.fn();

    render(
      <RoomBlockCreateDialog
        open
        onClose={() => {}}
        rooms={[room]}
        selectedRoom={null}
        setSelectedRoom={setSelectedRoom}
        newRoomBlock={{
          type: 'out_of_order',
          reason: '',
          details: '',
          start_date: '',
          end_date: '',
          allow_sell: false,
        }}
        setNewRoomBlock={() => {}}
        onSubmit={() => {}}
        loading={false}
      />,
    );

    fireEvent.click(screen.getAllByRole('combobox')[0]);
    fireEvent.click(await screen.findByRole('option', { name: 'Room QT2ED0 (standard)' }));

    expect(setSelectedRoom).toHaveBeenCalledWith(room);
  });
});
