import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useState } from 'react';
import { MemoryRouter } from 'react-router-dom';
import AuditTimelinePage from '../AuditTimelinePage';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('axios', () => ({ default: { get } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key, i18n: { language: 'tr' } }) }));

import {
  auditActionLabel,
  auditEntityLabel,
  friendlyAction,
  summarizeUserAgent,
  auditActorLabel,
  auditRequestPath,
  TimelineEvent,
  ChainVerificationScope,
} from '../AuditTimelinePage';

describe('işlem kayıtları kullanıcı dili', () => {
  it('doğrulama sınırını ve tarama sırasında gelen yeni kayıtları açıklar', () => {
    render(<ChainVerificationScope chain={{ as_of_seq: 6655, last_seq: 6655, observed_latest_seq: 6656, concurrent_appends: true }} />);
    expect(screen.getByTestId('chain-verification-scope')).toHaveTextContent('Tarama başlangıç sınırı: #6655');
    expect(screen.getByText(/bu kayıtlar sonraki taramada kontrol edilir/)).toBeInTheDocument();
  });

  it('sınırlı taramayı bütün zincirin kabulü gibi sunmaz', () => {
    render(<ChainVerificationScope chain={{ as_of_seq: 10000, last_seq: 5000, truncated: true }} />);
    expect(screen.getByText(/tüm zincir doğrulanmış sayılmaz/)).toBeInTheDocument();
  });

  it('ekran daha geniş sınır ister ve tamamlanmamış taramayı yeşil göstermez', async () => {
    get.mockImplementation(url => Promise.resolve({ data: url.includes('/chain/verify')
      ? { ok: true, truncated: true, checked: 50000, as_of_seq: 60000, last_seq: 50000, breaks: [] }
      : url.includes('/timeline') ? { events: [] } : null }));
    render(<MemoryRouter><AuditTimelinePage user={{}} tenant={{}} onLogout={() => {}} /></MemoryRouter>);
    const status = await screen.findByTestId('chain-status');
    expect(status).toHaveTextContent('Sınırlı tarama');
    expect(status).toHaveClass('bg-amber-50');
    expect(get).toHaveBeenCalledWith('/audit/chain/verify', expect.objectContaining({ params: { limit: 50000 } }));
  });
  it('teknik işlem ve varlık adlarını anlaşılır Türkçeye çevirir', () => {
    expect(auditActionLabel('login success')).toBe('Oturum açıldı');
    expect(auditActionLabel('token_refresh')).toBe('Oturum süresi yenilendi');
    expect(auditActionLabel('gl.report.exported')).toBe('Muhasebe raporu dışa aktarıldı');
    expect(auditEntityLabel('gl_report')).toBe('Genel Muhasebe Raporu');
    expect(auditEntityLabel('pos_transaction')).toBe('Restoran POS');
    expect(auditEntityLabel('gl_voucher')).toBe('Muhasebe fişi');
    expect(auditActionLabel('gl_voucher_approved')).toBe('Muhasebe fişi gerekçeyle onaylandı');
    expect(auditActionLabel('gl_voucher_policy_changed')).toBe('Tesisin fiş onay politikası değiştirildi');
    expect(auditActionLabel('charge_split')).toBe('Hizmet bedeli diğer folyoya aktarıldı');
    expect(auditActionLabel('charge_received')).toBe('Diğer folyodan hizmet bedeli alındı');
  });

  it('API hareketlerini modül adıyla özetler', () => {
    expect(friendlyAction({
      action: 'POST /api/pms/bookings',
      http_method: 'POST',
      target_type: 'booking',
    })).toBe('Rezervasyon oluşturma isteği');
  });

  it('komutları ayırır, bilinmeyen POST için oluşturma iddiasında bulunmaz', () => {
    expect(friendlyAction({ action: 'POST /api/pms/bookings/b-1/check-in', target_type: 'pms' })).toBe('Giriş (check-in) işlemi');
    expect(friendlyAction({ action: 'POST /api/auth/refresh', target_type: 'auth' })).toBe('Oturum yenileme isteği');
    expect(friendlyAction({ action: 'POST /api/pms/search', target_type: 'pms' })).toBe('PMS: API işlem isteği');
    expect(auditRequestPath({ action: 'POST /api/pms/search?token=private' })).toBe('/api/pms/search');
    expect(auditActorLabel({ actor_id: 'operator-42', actor_role: 'admin' })).toBe('operator-42');
  });

  it('açıklama, tam kimlik, istek ve kayıtlı değişiklikleri gösterir', () => {
    const event = { id: 'evt-1', operation_name: 'room.updated', actor_id: 'operator-42', actor_role: 'admin', target_id: 'room-full-identifier', details: '203 numaralı oda temizlendi', before_snapshot: { room_status: 'dirty' }, after_snapshot: { room_status: 'clean' }, metadata: { room_number: '203' } };
    function Example() {
      const [expanded, setExpanded] = useState(false);
      return <TimelineEvent event={event} expanded={expanded} onToggle={() => setExpanded(!expanded)} t={key => key} i18n={{ language: 'tr' }} />;
    }
    render(<Example />);
    expect(screen.getByText('203 numaralı oda temizlendi')).toBeTruthy();
    expect(screen.getByText('room-full-identifier')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Ayrıntılar/ }));
    expect(screen.getByText('Kirli')).toBeTruthy();
    expect(screen.getByText('Temiz')).toBeTruthy();
    expect(screen.getByText('Ek bilgiler')).toBeTruthy();
  });

  it('snapshot olmayan eski kayıtta ayrıntıları açar, kayıp bilgiyi açıklar', () => {
    render(<TimelineEvent event={{ action: 'POST /api/pms/search?token=private', target_type: 'pms', http_status: 200 }} expanded t={key => key} i18n={{ language: 'tr' }} />);
    expect(screen.getByText(/değişen alanlar doğrulanamıyor/)).toBeTruthy();
    expect(screen.getByText(/HTTP 200/)).toBeTruthy();
    expect(screen.queryByText(/token=private/)).toBeNull();
  });

  it('ham user-agent yerine okunabilir cihaz özeti üretir', () => {
    expect(summarizeUserAgent(
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/152.0.0.0 Safari/537.36',
    )).toBe('Chrome 152.0.0.0 · macOS');
    expect(summarizeUserAgent('')).toBe('Bilinmeyen cihaz');
  });

  it('ikramı, tutarı, kullanıcıyı ve gerekçeyi merkezi logda anlaşılır gösterir', () => {
    expect(auditEntityLabel('reservation')).toBe('Rezervasyon');
    expect(auditActionLabel('concession_rejected')).toBe('Bekleyen ikram / indirim iptal edildi');
    render(<TimelineEvent event={{ action: 'concession_applied', target_type: 'reservation',
      actor_name: 'Ayşe Yılmaz', details: '7200.00 TRY oda ikramı. Gerekçe: Yönetim misafiri',
      override_reason: 'Yönetim misafiri', after_snapshot: { amount_minor: 720000, reason: 'Yönetim misafiri' } }}
      expanded t={key => key} i18n={{ language: 'tr' }} />);
    expect(screen.getByText('İkram / indirim uygulandı')).toBeTruthy();
    expect(screen.getByText('7200.00 TRY oda ikramı. Gerekçe: Yönetim misafiri')).toBeTruthy();
    expect(screen.getByText(/Ayşe Yılmaz/)).toBeTruthy();
    expect(screen.getAllByText('Yönetim misafiri').length).toBeGreaterThan(0);
  });
});
