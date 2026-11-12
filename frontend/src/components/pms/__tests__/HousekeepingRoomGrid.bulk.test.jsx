import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), success: vi.fn(), warning: vi.fn() }));
vi.mock('axios', () => ({ default: { get: mocks.get, put: mocks.put } }));
vi.mock('sonner', () => ({ toast: { success: mocks.success, warning: mocks.warning, error: vi.fn() } }));
vi.mock('@/lib/websocket', () => ({ websocket: { connect: vi.fn().mockRejectedValue(new Error('offline test')) } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, options) => options?.room ? `${options.room} numaralı odayı seç` : key.split('.').at(-1) }) }));

import HousekeepingRoomGrid from '@/components/pms/HousekeepingRoomGrid';

describe('housekeeping bulk conflict readback', () => {
  it('reports the actual changed count and refreshes instead of presenting stale rooms as cleaned', async () => {
    mocks.success.mockClear();
    mocks.warning.mockClear();
    mocks.get.mockResolvedValue({ data: { rooms: [
      { id: 'r1', room_number: '101', housekeeping_status: 'dirty' },
      { id: 'r2', room_number: '102', housekeeping_status: 'dirty' },
    ] } });
    mocks.put.mockResolvedValue({ data: { success: false, updated_count: 1, conflicted_room_ids: ['r2'] } });
    const changed = vi.fn();
    render(<HousekeepingRoomGrid onChange={changed} />);
    fireEvent.click(await screen.findByLabelText('101 numaralı odayı seç'));
    fireEvent.click(screen.getByLabelText('102 numaralı odayı seç'));
    fireEvent.click(screen.getByTestId('bulk-update-btn'));
    fireEvent.click(within(screen.getByTestId('bulk-update-btn').parentElement).getByRole('button', { name: 'clean' }));
    await waitFor(() => expect(mocks.warning).toHaveBeenCalledWith('1 oda güncellendi. 1 odanın durumu değişti; listeyi kontrol edin.'));
    expect(mocks.success).not.toHaveBeenCalled();
    expect(mocks.put).toHaveBeenCalledWith('/pms/housekeeping/rooms/bulk-status', null, { params: { room_ids: ['r1', 'r2'], status: 'clean' } });
    await waitFor(() => expect(changed).toHaveBeenCalledOnce());
    expect(mocks.get.mock.calls.length).toBeGreaterThan(1);
  });
});
