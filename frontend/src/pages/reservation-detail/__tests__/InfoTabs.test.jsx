import { render, screen } from '@testing-library/react';
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
  });

  it('does not request or display the no-show risk score', () => {
    render(
      <GeneralInfoTab
        booking={{
          id: 'booking-a',
          status: 'confirmed',
          check_in: '2026-08-26',
          check_out: '2026-08-28',
          adults: 2,
          children: 0,
        }}
        guest={null}
        room={null}
      />,
    );

    expect(apiGet).not.toHaveBeenCalledWith(expect.stringContaining('/pms/no-show-risk/'));
    expect(screen.queryByTestId('no-show-risk-banner')).not.toBeInTheDocument();
    expect(screen.queryByText(/No-Show Risk Skoru/i)).not.toBeInTheDocument();
  });

  it('keeps guest alerts visible without restoring the risk score', async () => {
    apiGet.mockResolvedValue({
      data: {
        has_alerts: true,
        alerts: [{ id: 'alert-a', type: 'note', level: 'warning', message: 'Geç giriş notu' }],
      },
    });

    render(
      <GeneralInfoTab
        booking={{
          id: 'booking-a',
          status: 'confirmed',
          guest_id: 'guest-a',
          check_in: '2026-08-26',
          check_out: '2026-08-28',
          created_at: '2026-08-22T12:00:00Z',
          checked_in_at: '2026-08-26T11:00:00Z',
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
    expect(screen.queryByText(/No-Show Risk Skoru/i)).not.toBeInTheDocument();
  });
});
