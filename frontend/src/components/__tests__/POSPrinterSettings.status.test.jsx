import { describe, expect, it } from 'vitest';
import { statusBadge } from '../POSPrinterSettings';

describe('honest printer readiness', () => {
  it('does not present a successful simulation as a ready physical printer', () => {
    expect(statusBadge({ job_status: 'sent', driver: 'simulator' }).label).toBe('Simülasyon · gerçek baskı yok');
  });
  it('shows an uncertain in-progress dispatch in Turkish', () => {
    expect(statusBadge({ job_status: 'dispatching' }).label).toBe('Baskı sonucu bekleniyor');
  });
});
