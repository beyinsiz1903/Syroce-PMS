import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ShiftAuditDetails } from '../POSExtensions';

describe('POS shift audit identity', () => {
  it('shows the persisted business day separately from the actual opening date', () => {
    render(<ShiftAuditDetails shift={{ id: 'dated', business_date: '2026-11-13', opened_at: '2026-11-27T00:00:00Z', status: 'open' }} />);
    expect(screen.getByText('İş günü: 2026-11-13')).toBeInTheDocument();
    expect(screen.getByText(/27.11.2026 03:00:00/)).toBeInTheDocument();
  });
  it('distinguishes shifts at the same outlet and preserves the actual event date', () => {
    render(<ShiftAuditDetails shift={{ id: 'shift-001', opened_at: '2026-11-24T22:10:00', closed_at: '2026-11-25T01:20:00Z', tx_count: 0, cash_sales: 0, currency: 'TRY', status: 'closed' }} />);
    expect(screen.getByText(/shift-001/)).toBeInTheDocument();
    expect(screen.getByText(/25.11.2026 01:10:00/)).toBeInTheDocument();
    expect(screen.getByText(/25.11.2026 04:20:00/)).toBeInTheDocument();
    expect(screen.getByText(/İşlem sayısı: 0/)).toBeInTheDocument();
    expect(screen.getByText(/Türkiye saati/)).toBeInTheDocument();
  });
  it('does not invent dates, a business day or zero movements for legacy missing data', () => {
    render(<ShiftAuditDetails shift={{ id: 'legacy', status: 'closed' }} />);
    expect(screen.getByText(/Açılış: —/)).toBeInTheDocument();
    expect(screen.getByText(/Kapanış: —/)).toBeInTheDocument();
    expect(screen.queryByText(/İşlem sayısı:/)).not.toBeInTheDocument();
    expect(screen.getByText(/İş günü kaydı yok/)).toBeInTheDocument();
  });
});
