import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { patch, post, navigate, toast } = vi.hoisted(() => ({ patch: vi.fn(), post: vi.fn(), navigate: vi.fn(), toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('axios', () => ({ default: { patch, post } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));
vi.mock('sonner', () => ({ toast }));
import RoomFeaturesPanel from '@/components/pms/RoomFeaturesPanel';

describe('RoomFeaturesPanel safe operational handoffs', () => {
  beforeEach(() => { vi.clearAllMocks(); patch.mockResolvedValue({ data: { dnd: true } }); });

  it('uses the canonical catalog/stock workspace instead of invented prices or direct charges', () => {
    render(<RoomFeaturesPanel room={{ id: 'r1', room_number: '101', booking_id: 'b1' }} />);
    fireEvent.click(screen.getByRole('button', { name: /Minibar ekranını aç/ }));
    expect(navigate).toHaveBeenCalledWith('/minibar');
    expect(post).not.toHaveBeenCalled();
    expect(screen.queryByText(/Su \(500ml\)|%30|%50|%100/)).not.toBeInTheDocument();
    expect(screen.getByText(/sabit bir ücret veya ücretsiz çıkış garantisi vermez/)).toBeInTheDocument();
  });

  it('prefers the public room ID and supplies the previous DND state', async () => {
    const onUpdate = vi.fn();
    render(<RoomFeaturesPanel room={{ id: 'public', _id: 'storage', dnd: false }} onUpdate={onUpdate} />);
    fireEvent.click(screen.getByRole('button', { name: 'Aktif Et' }));
    await waitFor(() => expect(patch).toHaveBeenCalledWith('/pms/rooms/public/features', { dnd: true, expected_dnd: false }));
    await waitFor(() => expect(screen.getByText('AKTİF')).toBeInTheDocument());
    expect(onUpdate).toHaveBeenCalledOnce();
  });

  it('resynchronizes state when another room is selected', () => {
    const view = render(<RoomFeaturesPanel room={{ id: 'first', dnd: true }} />);
    expect(screen.getByText('AKTİF')).toBeInTheDocument();
    view.rerender(<RoomFeaturesPanel room={{ id: 'second', dnd: false }} />);
    expect(screen.getByText('KAPALI')).toBeInTheDocument();
  });

  it('does not overwrite the new room with a late previous-room response', async () => {
    let resolve;
    patch.mockReturnValue(new Promise(done => { resolve = done; }));
    const view = render(<RoomFeaturesPanel room={{ id: 'first', dnd: false }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Aktif Et' }));
    view.rerender(<RoomFeaturesPanel room={{ id: 'second', dnd: false }} />);
    resolve({ data: { dnd: true } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Aktif Et' })).toBeEnabled());
    expect(screen.getByText('KAPALI')).toBeInTheDocument();
  });

  it('guards double submits and retains the old state on conflict', async () => {
    patch.mockRejectedValue({ response: { status: 409, data: { detail: 'DND başka bir oturumda değişti' } } });
    render(<RoomFeaturesPanel room={{ id: 'r1', dnd: false }} />);
    const button = screen.getByRole('button', { name: 'Aktif Et' });
    fireEvent.click(button); fireEvent.click(button);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('DND başka bir oturumda değişti'));
    expect(patch).toHaveBeenCalledOnce();
    expect(screen.getByText('KAPALI')).toBeInTheDocument();
  });

  it('does not send an unbound room write', () => {
    render(<RoomFeaturesPanel room={{ room_number: 'unknown' }} />);
    expect(screen.getByRole('button', { name: 'Aktif Et' })).toBeDisabled();
  });
});
