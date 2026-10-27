import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, fallback) => fallback || key }),
}));

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock('@/api/axios', () => ({
  default: { get: apiGet },
}));

import { GeneralInfoTab } from '../InfoTabs';

describe('GeneralInfoTab', () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiGet.mockResolvedValue({ data: {} });
  });

  it('shows the actual last receipt method instead of a later Comp adjustment', () => {
    render(<GeneralInfoTab booking={{ id: 'summary-115' }} guest={null} room={null}
      summary={{ balance: 3400, reservation_total_due: 8200 }} payments={[
        { method: 'bank_transfer', amount: 4800, created_at: '2026-10-24T16:33:00Z' },
        { method: 'cash', amount: 1000, created_at: '2026-10-24T16:42:00Z' },
        { method: 'discount', amount: 7300, created_at: '2026-10-24T20:49:00Z' },
      ]} />);
    expect(screen.getByText('Son tahsilat yöntemi').parentElement).toHaveTextContent('Nakit');
    expect(screen.getByTestId('general-payment-info')).not.toHaveTextContent('discount');
    expect(screen.getByTestId('general-payment-info')).toHaveTextContent('Toplam kalan ödeme8.200 TL');
  });

  it('does not present a fully Comp or source-settled stay as a cash receipt', () => {
    render(<GeneralInfoTab booking={{ id: 'comp' }} summary={{ balance: 0 }}
      payments={[{ method: 'discount', amount: 100 }, { method: 'wallet', amount: 50 }]} />);
    expect(screen.getByText('Son tahsilat yöntemi').parentElement).toHaveTextContent('Tahsilat kaydı yok');
  });

  it('does not claim no receipts when payment rows were not provided', () => {
    render(<GeneralInfoTab booking={{ id: 'missing-payments' }} summary={{ balance: 0 }} />);
    expect(screen.getByText('Son tahsilat yöntemi').parentElement).toHaveTextContent('Doğrulanamadı');
  });

  it('shows the booked category before a physical room has been assigned', async () => {
    await act(async () => {
      render(<GeneralInfoTab booking={{ id: 'unassigned-exely', room_type: 'Deluxe' }} guest={null} room={null} />);
    });
    expect(screen.getByText('Oda Tipi').parentElement).toHaveTextContent('Deluxe');
    expect(screen.getByText('Oda No').parentElement).toHaveTextContent('-');
  });

  it('preserves the assigned room category when a room is present', async () => {
    await act(async () => {
      render(<GeneralInfoTab booking={{ id: 'assigned', room_type: 'Standard' }} guest={null} room={{ room_type: 'Deluxe', room_number: '201' }} />);
    });
    expect(screen.getByText('Oda Tipi').parentElement).toHaveTextContent('Deluxe');
    expect(screen.getByText('Oda No').parentElement).toHaveTextContent('201');
  });

  it('does not label an unverified Exely bed count as three adults and no children', async () => {
    await act(async () => {
      render(<GeneralInfoTab
        booking={{ id: 'synthetic-exely', channel: 'exely', adults: 3, children: 0, guests_count: 3 }}
        guest={null} room={null}
      />);
    });
    expect(screen.getAllByText('Doğrulanmadı')).toHaveLength(2);
    expect(screen.getByTestId('exely-demographics-warning')).toBeInTheDocument();
    expect(screen.getByText('Toplam Konuk').parentElement.parentElement).toHaveTextContent('3');
  });

  it.each(['confirmed', 'guaranteed', 'pending', 'checked_in', 'in_house', 'checked_out', 'cancelled', 'no_show'])(
    'does not request or display a predicted no-show warning for a %s booking', async (status) => {
      apiGet.mockImplementation((url) => {
        if (url.includes('/no-show-risk/')) return Promise.resolve({ data: { score: 65, level: 'medium', factors: [{ label: 'Ödeme yapılmamış' }] } });
        return Promise.resolve({ data: {} });
      });
      await act(async () => {
        render(
          <GeneralInfoTab
            booking={{
              id: 'booking-a',
              status,
              check_in: '2026-08-26',
              check_out: '2026-08-28',
              adults: 2,
              children: 0,
            }}
            guest={null}
            room={null}
          />,
        );
      });

      expect(screen.queryByTestId('no-show-risk-banner')).not.toBeInTheDocument();
      expect(screen.queryByText(/No-show riski/i)).not.toBeInTheDocument();
      expect(apiGet).not.toHaveBeenCalled();
    },
  );

  it('preserves actual no-show history after removing the prediction', () => {
    const onSwitchTab = vi.fn();
    render(<GeneralInfoTab booking={{ id: 'actual-no-show', status: 'no_show' }}
      history={[{ id: 'no-show-event', action: 'marked_noshow', actor: 'Ayşe Kaya', created_at: '2026-10-25T14:00:00Z' }]}
      onSwitchTab={onSwitchTab} />);

    expect(screen.getByText('No-show işaretlendi')).toBeInTheDocument();
    expect(screen.getByText(/Ayşe Kaya/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Tüm Geçmiş' }));
    expect(onSwitchTab).toHaveBeenCalledWith('history');
    expect(screen.queryByTestId('no-show-risk-banner')).not.toBeInTheDocument();
    expect(apiGet).not.toHaveBeenCalled();
  });

  it('keeps guest alerts visible and does not score an in-house stay', async () => {
    apiGet.mockImplementation((url) => Promise.resolve({
      data: url.includes('/highlights')
        ? { has_alerts: true, alerts: [{ id: 'alert-a', type: 'note', level: 'warning', message: 'Geç giriş notu' }] }
        : {},
    }));

    render(
      <GeneralInfoTab
        booking={{
          id: 'booking-a',
          guest_id: 'guest-a',
          check_in: '2026-08-26',
          check_out: '2026-08-28',
          created_at: '2026-08-22T12:00:00Z',
          checked_in_at: '2026-08-26T11:00:00Z',
          status: 'checked_in',
          special_requests: 'Sessiz oda',
        }}
        guest={{
          id: 'guest-a',
          name: 'Test Misafir',
          email: 'guest@example.com',
          phone: '+905555555555',
          nationality: 'TR',
          vip_status: true,
          total_stays: 2,
        }}
        room={{ room_number: '101', room_type: 'Deluxe', floor: 1, view: 'sea', bed_type: 'king' }}
        summary={{ balance: 100, total_amount: 500, total_payments: 400, total_deposits: 50 }}
        payments={[{ method: 'virtual_card', amount: 400 }]}
        deposits={[{ amount: 50 }]}
        notes={[{ id: 'note-a', content: 'Karşılama notu', created_at: '2026-08-22T12:00:00Z' }]}
        history={[{ id: 'history-a', action: 'reservation_created', created_at: '2026-08-22T12:00:00Z' }]}
        company={{ name: 'Test Acente' }}
      />,
    );

    expect(await screen.findByText('Geç giriş notu')).toBeInTheDocument();
    expect(apiGet).toHaveBeenCalledTimes(1);
    expect(apiGet).toHaveBeenCalledWith('/pms/guests/guest-a/highlights');
    expect(screen.getByText('Tekrar misafir — 2. ziyareti')).toBeInTheDocument();
    expect(screen.getByText('Sessiz oda')).toBeInTheDocument();
    expect(screen.getByText('Test Acente')).toBeInTheDocument();
    expect(screen.queryByTestId('no-show-risk-banner')).not.toBeInTheDocument();
  });

  it('shows the reservation currency instead of a hard-coded TL label', () => {
    render(
      <GeneralInfoTab
        booking={{ id: 'booking-eur', currency: 'EUR' }}
        guest={null}
        room={null}
        summary={{ balance: 145.45, total_amount: 145.45, total_payments: 0 }}
        payments={[]}
        deposits={[]}
      />,
    );

    expect(screen.getByText('Para Birimi').parentElement).toHaveTextContent('EUR');
  });
});
