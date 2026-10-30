import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock('@/api/axios', () => ({
  default: { post },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key.endsWith('folyoya_ekle') ? 'Folyoya Ekle' : key,
  }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import EarlyLateChargeModal from '@/components/EarlyLateChargeModal';

describe('EarlyLateChargeModal currency contract', () => {
  beforeEach(() => {
    post.mockReset();
  });

  it('posts the calculated currency through the currency-aware extra charge endpoint', async () => {
    post
      .mockResolvedValueOnce({
        data: {
          applicable: true,
          amount: 25,
          nightly_rate: 100,
          nights: 1,
          currency: 'EUR',
          label: 'Erken Giriş — Erken',
        },
      })
      .mockResolvedValueOnce({ data: { success: true } });

    render(
      <EarlyLateChargeModal
        open
        onClose={vi.fn()}
        bookingId="booking-1"
        direction="early_checkin"
        serviceDate="2026-10-26"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Ücreti hesapla' }));
    expect(await screen.findByText(/25,00\s*€/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Folyoya Ekle' }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post).toHaveBeenLastCalledWith(
      '/pms/reservations/booking-1/add-extra-charge',
      expect.objectContaining({
        amount: 25,
        quantity: 1,
        input_currency: 'EUR',
        service_date: '2026-10-26',
        service_time: '10:00',
      })
    );
  });

  const quote = { applicable: true, amount: 56, nightly_rate: 112, nights: 5, currency: 'USD', label: 'Geç Çıkış' };
  const mount = () => render(<EarlyLateChargeModal open onClose={vi.fn()} bookingId="b" direction="late_checkout" defaultHour={14} serviceDate="2026-10-26" />);

  it('invalidates a calculated amount when the service hour changes', async () => {
    post.mockResolvedValue({ data: quote });
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Ücreti hesapla' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Folyoya Ekle' })).toBeEnabled());
    fireEvent.change(screen.getByLabelText('Hizmet saati'), { target: { value: '18:30' } });
    expect(screen.getByRole('button', { name: 'Folyoya Ekle' })).toBeDisabled();
    expect(screen.getByLabelText('Düzeltilmiş tutar')).toBeDisabled();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('ignores a slow quote for the previous hour', async () => {
    let resolve;
    post.mockReturnValue(new Promise(yes => { resolve = yes; }));
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Ücreti hesapla' }));
    fireEvent.change(screen.getByLabelText('Hizmet saati'), { target: { value: '19:00' } });
    await act(async () => resolve({ data: quote }));
    expect(screen.getByRole('button', { name: 'Folyoya Ekle' })).toBeDisabled();
  });

  it('requires a quote and reason for an override and submits a double click only once', async () => {
    post.mockResolvedValueOnce({ data: quote }).mockReturnValue(new Promise(() => {}));
    mount();
    expect(screen.getByLabelText('Düzeltilmiş tutar')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Ücreti hesapla' }));
    await waitFor(() => expect(screen.getByLabelText('Düzeltilmiş tutar')).toBeEnabled());
    fireEvent.change(screen.getByLabelText('Düzeltilmiş tutar'), { target: { value: '40' } });
    expect(screen.getByRole('button', { name: 'Folyoya Ekle' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Düzeltme nedeni'), { target: { value: 'Yönetici onaylı indirim' } });
    fireEvent.click(screen.getByRole('button', { name: 'Folyoya Ekle' }));
    fireEvent.click(screen.getByRole('button', { name: 'Folyoya Ekle' }));
    expect(post).toHaveBeenCalledTimes(2);
    expect(post).toHaveBeenLastCalledWith('/pms/reservations/b/add-extra-charge', expect.objectContaining({ amount: 40, input_currency: 'USD', service_time: '14:00', description: expect.stringContaining('Yönetici onaylı indirim') }));
  });

  it('blocks a blind repeat after an unknown write outcome', async () => {
    post.mockResolvedValueOnce({ data: quote }).mockRejectedValueOnce(new Error('network unavailable'));
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Ücreti hesapla' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Folyoya Ekle' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Folyoya Ekle' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('tekrar eklemeyin');
    expect(screen.getByRole('button', { name: 'Folyoya Ekle' })).toBeDisabled();
    expect(post).toHaveBeenCalledTimes(2);
  });
});
