import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import AdrRevparSection from '../AdrRevparSection';

describe('AdrRevparSection currency handling', () => {
  it('preserves previous-period ADR currency instead of displaying EUR as TRY', () => {
    render(<AdrRevparSection data={{}} s={{}} pc={{ prev_month_adr: 123, prev_month_adr_by_currency: { EUR: 123 } }} periodMetrics={{ adr_by_currency: { EUR: 100 }, revenue_source: 'mixed' }} reportPeriod="daily" />);
    expect(screen.getAllByText(text => text.includes('123,00') && text.includes('€')).length).toBeGreaterThan(0);
    expect(screen.queryByText(text => text.includes('123,00') && text.includes('₺'))).not.toBeInTheDocument();
    expect(screen.getByText('İşlenmiş + tahakkuk (eksik gün/döviz)')).toBeInTheDocument();
  });
  it('does not draw one performance chart when currencies differ between days', () => {
    render(<AdrRevparSection
      data={{ revenue_trend: [
        { label: '01 Eki', revenue: 10000, revenue_by_currency: { TRY: 10000 } },
        { label: '02 Eki', revenue: 200, revenue_by_currency: { EUR: 200 } },
      ] }}
      s={{}}
      pc={{}}
      periodMetrics={{}}
      reportPeriod="daily"
    />);

    expect(screen.getByText('Karma dövizli gelirler tek performans grafiğinde toplanmaz.')).toBeInTheDocument();
  });
});
