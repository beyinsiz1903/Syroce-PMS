import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

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

describe('Guest360Dialog sunum tutarlılığı', () => {
  it('Türkçe başlıkları ve TRY biçiminde finansal değerleri gösterir', () => {
    render(
      <Guest360Dialog
        open
        onClose={vi.fn()}
        selectedGuest360="guest-1"
        loadGuest360={vi.fn()}
        loadingGuest360={false}
        guest360Data={{
          guest: { id: 'guest-1', name: 'Test Misafir', loyalty_tier: 'standard' },
          profile: { loyalty_status: 'standard', loyalty_points: 250 },
          stats: { total_stays: 2, total_nights: 4, lifetime_value: 12500, average_adr: 3125 },
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

  it('yükleme durumunu kullanıcı dostu Türkçe metinle gösterir', () => {
    render(
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
});
