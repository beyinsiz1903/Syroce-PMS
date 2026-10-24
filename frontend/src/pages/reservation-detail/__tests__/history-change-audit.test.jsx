import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, fallback) => fallback || key }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import { HistoryTab } from '@/pages/reservation-detail/GuestServiceTabs';

afterEach(() => cleanup());

describe('reservation change audit history', () => {
  it('shows concession explanation, operator, native-currency amount and affected service', () => {
    render(<HistoryTab history={[{ id: 'audit-comp', action: 'concession_applied', actor: 'Ayşe Yılmaz',
      created_at: '2026-10-24T10:00:00Z', details: { amount_minor: 110000, currency: 'EUR', folio_id: 'F-2',
        reason: 'Misafir memnuniyeti', service_details: [{ id: 'spa', description: 'SPA masaj hizmeti' }] } }]} roomMoves={[]} />);
    expect(screen.getByText('İkram / indirim uygulandı')).toBeInTheDocument();
    expect(screen.getByText('Yapan: Ayşe Yılmaz')).toBeInTheDocument();
    expect(screen.getByText('Sebep: Misafir memnuniyeti')).toBeInTheDocument();
    expect(screen.getByText('Folyo: F-2')).toBeInTheDocument();
    expect(screen.getByText('Hizmetler: SPA masaj hizmeti')).toBeInTheDocument();
    expect(screen.getByText(/Tutar:/)).toHaveTextContent(/1[.,]100/);
  });
  it('shows the source and old/new stay dates for a timeline entry', () => {
    render(
      <HistoryTab
        history={[
          {
            id: 'activity-1',
            action: 'stay_dates_updated',
            actor: 'HotelRunner',
            created_at: '2026-09-06T09:00:00Z',
            details: {
              source: 'Kanal / OTA',
              channel: 'Expedia',
              changes: {
                check_out: {
                  from: '2026-09-06T12:00:00+03:00',
                  to: '2026-09-07T12:00:00+03:00',
                },
              },
            },
          },
        ]}
        roomMoves={[]}
      />,
    );

    expect(screen.getByText('Konaklama tarihleri güncellendi')).toBeInTheDocument();
    expect(screen.getByText('Kaynak: Kanal / OTA · Expedia')).toBeInTheDocument();
    expect(screen.getByText('Çıkış tarihi:').parentElement).toHaveTextContent(/06 Eyl 2026.*→ 07 Eyl 2026/);
    expect(screen.getByText('Yapan: HotelRunner')).toBeInTheDocument();
  });
});
