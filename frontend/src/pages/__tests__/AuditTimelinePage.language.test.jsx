import { describe, expect, it } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useState } from 'react';

import {
  auditActionLabel,
  auditEntityLabel,
  friendlyAction,
  summarizeUserAgent,
  auditActorLabel,
  auditRequestPath,
  TimelineEvent,
} from '../AuditTimelinePage';

describe('işlem kayıtları kullanıcı dili', () => {
  it('teknik işlem ve varlık adlarını anlaşılır Türkçeye çevirir', () => {
    expect(auditActionLabel('login success')).toBe('Oturum açıldı');
    expect(auditActionLabel('token_refresh')).toBe('Oturum süresi yenilendi');
    expect(auditActionLabel('gl.report.exported')).toBe('Muhasebe raporu dışa aktarıldı');
    expect(auditEntityLabel('gl_report')).toBe('Genel Muhasebe Raporu');
    expect(auditEntityLabel('pos_transaction')).toBe('Restoran POS');
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
});
