import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import RoomsTab from '../RoomsTab';

vi.mock('axios', () => ({ default: { get: vi.fn().mockResolvedValue({ data: [] }) } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
const room = { id: 'r1', room_number: '101', room_type: 'Standart', status: 'dirty' };
const props = { rooms: [room], bookings: [], businessDate: '2026-10-18' };
beforeEach(() => vi.useFakeTimers());
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); });

describe('Room status background synchronization', () => {
  it('does not overlap slow refresh requests', async () => {
    let finish;
    const refresh = vi.fn(() => new Promise(resolve => { finish = resolve; }));
    render(<RoomsTab {...props} onDataRefresh={refresh} />);
    await act(async () => vi.advanceTimersByTimeAsync(90000));
    expect(refresh).toHaveBeenCalledTimes(1);
    await act(async () => finish());
    await act(async () => vi.advanceTimersByTimeAsync(30000));
    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it('keeps its refresh schedule when an equivalent room array arrives', async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    const view = render(<RoomsTab {...props} onDataRefresh={refresh} />);
    await act(async () => vi.advanceTimersByTimeAsync(20000));
    view.rerender(<RoomsTab {...props} rooms={[{ ...room }]} onDataRefresh={refresh} />);
    await act(async () => vi.advanceTimersByTimeAsync(10000));
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('pauses while hidden and stops polling after unmount', async () => {
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    const refresh = vi.fn().mockResolvedValue(undefined);
    const view = render(<RoomsTab {...props} onDataRefresh={refresh} />);
    await act(async () => vi.advanceTimersByTimeAsync(30000));
    expect(refresh).not.toHaveBeenCalled();
    visibility.mockReturnValue('visible');
    await act(async () => vi.advanceTimersByTimeAsync(30000));
    expect(refresh).toHaveBeenCalledTimes(1);
    view.unmount();
    await act(async () => vi.advanceTimersByTimeAsync(60000));
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
