import { describe, expect, it } from 'vitest';

import {
  auditActionLabel,
  auditEntityLabel,
  friendlyAction,
  summarizeUserAgent,
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
    })).toBe('Rezervasyon: oluşturdu / işlem yaptı');
  });

  it('ham user-agent yerine okunabilir cihaz özeti üretir', () => {
    expect(summarizeUserAgent(
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/152.0.0.0 Safari/537.36',
    )).toBe('Chrome 152.0.0.0 · macOS');
    expect(summarizeUserAgent('')).toBe('Bilinmeyen cihaz');
  });
});
