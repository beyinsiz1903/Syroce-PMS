import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import FindRoomDialog from '../FindRoomDialog';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, fallback) => typeof fallback === 'string' ? fallback : fallback?.defaultValue || key }) }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn() } }));
const criteria = { check_in: '2026-11-10', check_out: '2026-11-12', guests: 2, room_type: 'any' };
const props = { open: true, onClose: vi.fn(), findRoomCriteria: criteria, setFindRoomCriteria: vi.fn(), businessDate: '2026-10-26', onRoomSelected: vi.fn() };

describe('available room search', () => {
  beforeEach(() => vi.clearAllMocks());
  it('does not query availability with reversed or zero-night dates', () => {
    render(<FindRoomDialog {...props} findRoomCriteria={{ ...criteria, check_out: criteria.check_in }} />);
    fireEvent.click(screen.getByRole('button', { name: 'common.search' }));
    expect(axios.get).not.toHaveBeenCalled();
    expect(screen.getByLabelText('booking.checkInDate')).toHaveAttribute('min', '2026-10-26');
  });

  it('ignores a delayed result after the search criteria change', async () => {
    let resolve;
    axios.get.mockReturnValue(new Promise(yes => { resolve = yes; }));
    const { rerender } = render(<FindRoomDialog {...props} />);
    fireEvent.click(screen.getByRole('button', { name: 'common.search' }));
    rerender(<FindRoomDialog {...props} findRoomCriteria={{ ...criteria, check_out: '2026-11-13' }} />);
    await act(async () => resolve({ data: { available_rooms: [{ id: 'old', room_number: 'OLD', capacity: 2 }] } }));
    expect(screen.queryByText('OLD')).not.toBeInTheDocument();
  });

  it('filters insufficient capacity and displays the actual room currency, not hard-coded dollars', async () => {
    const room = { id: 'r', room_number: 'QA104', currency: 'EUR', base_price: 112, capacity: 2 };
    axios.get.mockResolvedValue({ data: { available_rooms: [room, { id: 'small', room_number: 'TOO-SMALL', capacity: 1 }] } });
    render(<FindRoomDialog {...props} />);
    fireEvent.click(screen.getByRole('button', { name: 'common.search' }));
    expect(await screen.findByText(/112,00\s*€/)).toBeInTheDocument();
    expect(screen.queryByText(/TOO-SMALL/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Bu odayla rezervasyon oluştur' }));
    await waitFor(() => expect(props.onRoomSelected).toHaveBeenCalledWith(room));
  });
});
