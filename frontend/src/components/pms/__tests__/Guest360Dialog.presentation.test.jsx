import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, useLocation } from 'react-router-dom';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_key, fallback) => fallback || 'Ekle' }),
}));

vi.mock('axios', () => ({
  default: { post: vi.fn().mockResolvedValue({ data: {} }) },
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), info: vi.fn(), success: vi.fn() },
}));

vi.mock('@/components/contact-center/CallButton', () => ({
  default: () => null,
}));

import Guest360Dialog from '@/components/pms/Guest360Dialog';

afterEach(() => cleanup());
const renderDialog = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>);
function Location() { const location = useLocation(); return <output data-testid="destination">{location.pathname}{location.search}</output>; }

describe('Guest360Dialog sunum tutarlılığı', () => {
  it.each([['Teklif Gönder', 'offer'], ['Mesaj Gönder', 'message']])('opens %s with only the exact guest id in the URL', (button, action) => {
    render(<MemoryRouter><Location /><Guest360Dialog open selectedGuest360="guest/1" guest360Data={{ guest: { id: 'guest/1', name: 'Deniz Kaya', email: 'private@example.com' }, profile: {}, stats: {}, stay_history: [] }} /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: button }));
    expect(screen.getByTestId('destination')).toHaveTextContent(`/messaging-dashboard?guest=guest%2F1&action=${action}`);
    expect(screen.getByTestId('destination')).not.toHaveTextContent('private');
    expect(screen.queryByText('Yaşam Boyu Değer')).not.toBeInTheDocument();
    expect(screen.getByText('Konaklama tutarı toplamı')).toBeInTheDocument();
  });
  it('reports a failed guest read and retries the same identity and section', () => {
    const loadGuest360 = vi.fn();
    renderDialog(<Guest360Dialog open onClose={vi.fn()} selectedGuest360="missing-guest" loadGuest360={loadGuest360} initialSection="history" error="Misafir profili yüklenemedi." />);
    expect(screen.getByRole('alert')).toHaveTextContent('Misafir profili yüklenemedi.');
    fireEvent.click(screen.getByRole('button', { name: 'Yeniden dene' }));
    expect(loadGuest360).toHaveBeenCalledWith('missing-guest', 'history');
  });

  it('Türkçe başlıkları ve API para biriminde finansal değerleri gösterir', () => {
    renderDialog(
      <Guest360Dialog
        open
        onClose={vi.fn()}
        selectedGuest360="guest-1"
        loadGuest360={vi.fn()}
        loadingGuest360={false}
        guest360Data={{
          guest: { id: 'guest-1', name: 'Test Misafir', loyalty_tier: 'standard' },
          profile: { loyalty_status: 'standard', loyalty_points: 250 },
          stats: { currency: 'TRY', total_stays: 2, total_nights: 4, lifetime_value: 12500, average_adr: 3125 },
          stay_history: [],
        }}
      />
    );

    expect(screen.getByText('Misafir 360° Profili')).toBeInTheDocument();
    expect(screen.getByText('Kimlik ve İletişim')).toBeInTheDocument();
    expect(screen.getByText('Toplam Konaklama')).toBeInTheDocument();
    expect(screen.getAllByText(/₺.*12\.500|12\.500.*₺/).length).toBeGreaterThan(0);
    expect(screen.getByText(/₺.*3\.125|3\.125.*₺/)).toBeInTheDocument();
    expect(screen.queryByText(/Guest 360° Profile/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/\$12500/)).not.toBeInTheDocument();
  });

  it('karma dövizli geçmişi tek para biriminde toplamak yerine ayrı gösterir', () => {
    renderDialog(
      <Guest360Dialog
        open
        onClose={vi.fn()}
        selectedGuest360="guest-fx"
        loadGuest360={vi.fn()}
        loadingGuest360={false}
        guest360Data={{
          guest: { id: 'guest-fx', name: 'Dövizli Misafir' },
          profile: { loyalty_status: 'standard' },
          stats: {
            currency: 'EUR',
            total_stays: 2,
            total_nights: 3,
            lifetime_value: 300,
            average_adr: 150,
            lifetime_value_by_currency: { EUR: 300, USD: 200 },
            average_adr_by_currency: { EUR: 150, USD: 200 },
          },
          stay_history: [],
        }}
      />
    );

    expect(screen.getAllByText(/300,00\s*€/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\$200\.00/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/500,00\s*€/)).not.toBeInTheDocument();
  });

  it('yükleme durumunu kullanıcı dostu Türkçe metinle gösterir', () => {
    renderDialog(
      <Guest360Dialog
        open
        onClose={vi.fn()}
        selectedGuest360="guest-1"
        loadGuest360={vi.fn()}
        loadingGuest360
        guest360Data={null}
      />
    );

    expect(screen.getByText('Misafir profili yükleniyor…')).toBeInTheDocument();
  });

  it('eski metin biçimindeki not ve etiketi sayfayı çökertmeden gösterir', () => {
    renderDialog(
      <Guest360Dialog
        open
        onClose={vi.fn()}
        selectedGuest360="guest-legacy"
        loadGuest360={vi.fn()}
        loadingGuest360={false}
        guest360Data={{
          guest: {
            id: 'guest-legacy',
            name: 'Eski Misafir',
            notes: 'Sessiz oda tercih ediyor',
            tags: 'VIP',
          },
          profile: { loyalty_status: 'standard' },
          stats: {},
          stay_history: { unexpected: 'legacy-object' },
        }}
      />
    );

    expect(screen.getByText('Sessiz oda tercih ediyor')).toBeInTheDocument();
    expect(screen.getByText('Eski kayıt')).toBeInTheDocument();
    expect(screen.getByText('VIP')).toBeInTheDocument();
    expect(screen.getByText('Kayıtlı konaklama geçmişi bulunamadı.')).toBeInTheDocument();
  });
});
