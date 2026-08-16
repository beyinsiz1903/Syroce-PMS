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
import { ExtraChargesTab } from '@/pages/reservation-detail/PricingTabs';

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
