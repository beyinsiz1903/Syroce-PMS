import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from '@/api/axios';
import { toast } from 'sonner';
import WalkinPage from '@/pages/WalkinPage';

vi.mock('@/api/axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'tr' } }),
}));

function GuestCardDestination() {
  const location = useLocation();
  return <div data-testid="guest-card-target">{location.state?.openBookingId}</div>;
}

async function completeWalkinForm() {
  render(<MemoryRouter initialEntries={['/walkin']}>
    <Routes>
      <Route path="/walkin" element={<WalkinPage tenant={{ currency: 'TRY' }} />} />
      <Route path="/app/reservation-calendar" element={<GuestCardDestination />} />
      <Route path="*" element={<div>Geçersiz hedef</div>} />
    </Routes>
  </MemoryRouter>);
  fireEvent.change(screen.getByTestId('walkin-name'), { target: { value: 'Deniz Karaca' } });
  fireEvent.click(screen.getByRole('button', { name: 'Devam' }));
  fireEvent.click(await screen.findByTestId('walkin-room-117'));
  fireEvent.click(screen.getByRole('button', { name: 'Devam' }));
  fireEvent.click(screen.getByTestId('walkin-submit'));
}

describe('walk-in guest card handoff', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: {
      business_date: '2026-11-12',
      rooms: [{ id: 'room-117', room_number: '117', room_type: 'Superior', rate: 1200 }],
    } });
  });

  it('opens the newly created booking through the existing guest-card route', async () => {
    api.post.mockResolvedValue({ data: { booking_id: 'walkin-booking-1', room_number: '117' } });
    await completeWalkinForm();
    expect(await screen.findByTestId('guest-card-target', {}, { timeout: 3000 }))
      .toHaveTextContent('walkin-booking-1');
    expect(api.post).toHaveBeenCalledExactlyOnceWith('/pms/walkin/checkin',
      expect.objectContaining({ guest_name: 'Deniz Karaca', room_id: 'room-117', total_amount: 1200, payment_amount: 0 }),
      { headers: { 'Idempotency-Key': expect.any(String) } });
    expect(screen.queryByText('Geçersiz hedef')).not.toBeInTheDocument();
  });

  it('keeps a failed check-in on the form without claiming success', async () => {
    api.post.mockRejectedValue({ response: { data: { detail: 'Oda artık müsait değil' } } });
    await completeWalkinForm();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('İşlem Hatası: Oda artık müsait değil'));
    expect(toast.success).not.toHaveBeenCalled();
    expect(screen.getByTestId('walkin-submit')).toBeEnabled();
    expect(screen.queryByTestId('guest-card-target')).not.toBeInTheDocument();
  });
});
