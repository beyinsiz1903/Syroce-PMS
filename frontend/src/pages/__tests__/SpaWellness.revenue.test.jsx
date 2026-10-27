import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SpaRevenueSummary, revenueText } from '@/pages/SpaWellness';

const money = (value, code = 'TRY') => `${value} ${code}`;

describe('SPA posted revenue', () => {
  it('shows full-comp original value separately from actual zero income', () => {
    render(<SpaRevenueSummary summary={{ revenue_by_currency: { TRY: 0 }, complimentary_value_by_currency: { TRY: 1500 }, revenue_complete: true }} money={money} />);
    expect(screen.getByText('Folyoya işlenen SPA geliri')).toBeInTheDocument();
    expect(screen.getByText('0 TRY')).toBeInTheDocument();
    expect(screen.getByText('İkram edilen hizmet değeri: 1500 TRY')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('labels missing source postings instead of presenting catalog price as income', () => {
    render(<SpaRevenueSummary summary={{ revenue: 0, revenue_by_currency: {}, unposted_appointments: 1, unposted_value_by_currency: { TRY: 1900 }, revenue_complete: false }} money={money} />);
    expect(screen.getByText('0 TRY')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('1 tamamlanan randevunun folyo kaydı yok');
    expect(screen.getByRole('status')).toHaveTextContent('1900 TRY');
  });

  it('never adds euros and dollars into one nominal total', () => {
    expect(revenueText({ revenue_by_currency: { EUR: 30, USD: 30 }, revenue: null }, money)).toBe('30 EUR · 30 USD');
  });
});
