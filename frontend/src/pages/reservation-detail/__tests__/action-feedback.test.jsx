import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from 'sonner';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, fallback) => fallback || key }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn() }));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

const { axiosGet, axiosPost, axiosMock } = vi.hoisted(() => {
  const get = vi.fn();
  const post = vi.fn();
  return {
    axiosGet: get,
    axiosPost: post,
    axiosMock: Object.assign(vi.fn(), {
      get,
      post,
      put: vi.fn(),
      delete: vi.fn(),
      defaults: { headers: { common: {} } },
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
    }),
  };
});
vi.mock('axios', () => ({ default: axiosMock }));

import { FoliosTab } from '@/pages/reservation-detail/FoliosTab';
import { OnlinePaymentTab } from '@/pages/reservation-detail/OnlinePaymentTab';
import { DailyRatesTab, ExtraChargesTab } from '@/pages/reservation-detail/PricingTabs';

beforeEach(() => {
  axiosGet.mockReset();
  axiosPost.mockReset();
  toast.error.mockReset();
  toast.success.mockReset();
});

afterEach(() => cleanup());

describe('reservation detail action feedback', () => {
  it('rejects a same-account cari transfer before posting', async () => {
    axiosGet.mockResolvedValue({
      data: { accounts: [{ id: 'agency-a', name: 'Test Acente', account_type: 'agency' }] },
    });
    render(
      <FoliosTab
        folios={[]}
        charges={[]}
        payments={[]}
        extra_charges={[]}
        summary={{}}
        booking={{ id: 'booking-a' }}
        onRefresh={vi.fn()}
        onSwitchTab={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId('btn-acenteye-aktar'));
    const panel = await screen.findByTestId('cari-agency-transfer-form');
    await waitFor(() => expect(within(panel).getAllByRole('combobox')).toHaveLength(2));
    const [source, target] = within(panel).getAllByRole('combobox');
    fireEvent.change(source, { target: { value: 'agency-a' } });
    fireEvent.change(target, { target: { value: 'agency-a' } });
    fireEvent.change(within(panel).getByRole('spinbutton'), { target: { value: '10' } });
    fireEvent.click(within(panel).getByRole('button', { name: /kaydet/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Kaynak ve hedef cari hesap farklı olmalı');
    });
    expect(axiosPost).not.toHaveBeenCalled();
  });

  it('shows an explicitly zeroed split charge and exposes a named split action', () => {
    render(
      <ExtraChargesTab
        extra_charges={[{ id: 'charge-a', description: 'Test Masrafı', total: 0, amount: 25 }]}
        charges={[]}
        booking={{ id: 'booking-a' }}
        allBookings={[]}
      />,
    );

    expect(screen.getByText('0 TL')).toBeInTheDocument();
    expect(screen.queryByText('25 TL')).toBeNull();
    expect(screen.getByRole('button', { name: 'Test Masrafı masrafını böl' })).toBeInTheDocument();
  });

  it('blocks zero extra charges before the API call', async () => {
    render(
      <ExtraChargesTab
        extra_charges={[]}
        charges={[]}
        booking={{ id: 'booking-a' }}
        allBookings={[]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /ekle/i }));
    const inputs = screen.getAllByRole('spinbutton');
    fireEvent.change(inputs[0], { target: { value: '0' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Ekle' }).at(-1));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(axiosPost).not.toHaveBeenCalled();
  });

  it('blocks a zero daily rate before the API call', async () => {
    render(
      <DailyRatesTab
        dailyRates={[{ id: 'rate-a', date: '2026-08-17', rate: 10 }]}
        booking={{ id: 'booking-a' }}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Düzenle' }));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Günlük fiyat sıfırdan büyük olmalıdır'));
    expect(axiosMock.put).not.toHaveBeenCalled();
  });

  it('requires a reason before marking a reservation complimentary', async () => {
    render(
      <DailyRatesTab
        dailyRates={[{ id: 'rate-a', date: '2026-08-18', rate: 10 }]}
        booking={{ id: 'booking-a' }}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Comp Ver' }));
    fireEvent.click(screen.getByRole('button', { name: 'Comp Olarak Kaydet' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Comp gerekçesi en az 3 karakter olmalı'));
    expect(axiosPost).not.toHaveBeenCalled();
  });

  it('marks an unposted reservation complimentary with an audit reason', async () => {
    axiosPost.mockResolvedValue({ data: { success: true } });
    const onRefresh = vi.fn();
    render(
      <DailyRatesTab
        dailyRates={[{ id: 'rate-a', date: '2026-08-18', rate: 10 }]}
        booking={{ id: 'booking-a' }}
        onRefresh={onRefresh}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Comp Ver' }));
    fireEvent.change(screen.getByPlaceholderText('Comp gerekçesi (zorunlu)'), { target: { value: 'Misafir memnuniyeti' } });
    fireEvent.click(screen.getByRole('button', { name: 'Comp Olarak Kaydet' }));

    await waitFor(() => expect(axiosPost).toHaveBeenCalledWith(
      '/pms/reservations/booking-a/mark-complimentary',
      { reason: 'Misafir memnuniyeti' },
    ));
    expect(onRefresh).toHaveBeenCalled();
  });

  it('locks daily rates before the current PMS business date', () => {
    render(
      <DailyRatesTab
        dailyRates={[
          { id: 'rate-closed', date: '2026-08-17', rate: 400 },
          { id: 'rate-open', date: '2026-08-18', rate: 500 },
        ]}
        booking={{ id: 'booking-a' }}
        businessDate="2026-08-18"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Düzenle' }));

    expect(screen.getAllByRole('textbox')).toHaveLength(1);
    expect(screen.getByText('Gün sonu kapalı')).toBeInTheDocument();
  });

  it('normalizes a Turkish decimal comma before saving daily rates', async () => {
    render(
      <DailyRatesTab
        dailyRates={[{ id: 'rate-a', date: '2026-08-18', rate: 10 }]}
        booking={{ id: 'booking-a' }}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Düzenle' }));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '1250,50' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));

    await waitFor(() => expect(axiosMock.put).toHaveBeenCalledWith(
      '/pms/reservations/booking-a/daily-rates',
      { rates: [{ id: 'rate-a', date: '2026-08-18', rate: 1250.5 }] },
    ));
  });

  it('exposes the virtual-card delete icon as a named action', async () => {
    axiosGet.mockResolvedValue({
      data: {
        has_vcc: true,
        vcc: {
          card_type: 'virtual',
          card_mask: '**** **** **** 0000',
          source: 'Test',
          view_count: 0,
          max_views: 3,
          locked: false,
        },
      },
    });

    render(<OnlinePaymentTab booking={{ id: 'booking-a' }} />);

    expect(await screen.findByRole('button', { name: 'Sanal kartı sil' })).toBeInTheDocument();
  });
});
