import { fmtDate, fmtTs, fmtTL, statusLabel } from '../helpers';

describe('reservation-detail/helpers', () => {
  describe('fmtDate', () => {
    it('returns dash for null/undefined', () => {
      expect(fmtDate(null)).toBe('-');
      expect(fmtDate(undefined)).toBe('-');
    });

    it('formats a valid ISO date string', () => {
      const result = fmtDate('2025-06-15T00:00:00');
      expect(result).toBeTruthy();
      expect(typeof result).toBe('string');
      expect(result).not.toBe('-');
    });

    it('formats a Date object', () => {
      const result = fmtDate(new Date(2025, 5, 15));
      expect(result).toBeTruthy();
      expect(result).not.toBe('-');
    });
  });

  describe('fmtTs', () => {
    it('returns empty for null/undefined', () => {
      expect(fmtTs(null)).toBe('');
      expect(fmtTs(undefined)).toBe('');
    });

    it('formats timestamp string to date-time', () => {
      const result = fmtTs('2025-06-15T14:30:45.000Z');
      expect(result).toBe('2025-06-15 14:30');
    });

    it('handles short strings', () => {
      const result = fmtTs('2025-06-15');
      expect(result).toBe('2025-06-15');
    });
  });

  describe('fmtTL', () => {
    it('formats zero for null/undefined', () => {
      expect(fmtTL(null)).toBe('0');
      expect(fmtTL(undefined)).toBe('0');
    });

    it('formats a positive number', () => {
      const result = fmtTL(1500);
      expect(result).toBeTruthy();
      expect(typeof result).toBe('string');
    });

    it('formats a float number', () => {
      const result = fmtTL(1234.56);
      expect(result).toBeTruthy();
    });
  });

  describe('statusLabel', () => {
    it('returns correct labels for known statuses', () => {
      expect(statusLabel('checked_in')).toBe('Giriş Yapildi');
      expect(statusLabel('confirmed')).toBe('Onaylandi');
      expect(statusLabel('checked_out')).toBe('Çıkış Yapildi');
      expect(statusLabel('cancelled')).toBe('İptal');
      expect(statusLabel('no_show')).toBe('No-Show');
    });

    it('returns the raw status for unknown statuses', () => {
      expect(statusLabel('pending')).toBe('pending');
      expect(statusLabel('custom_status')).toBe('custom_status');
    });

    it('returns Beklemede for null/undefined/empty', () => {
      expect(statusLabel(null)).toBe('Beklemede');
      expect(statusLabel(undefined)).toBe('Beklemede');
      expect(statusLabel('')).toBe('Beklemede');
    });
  });
});
