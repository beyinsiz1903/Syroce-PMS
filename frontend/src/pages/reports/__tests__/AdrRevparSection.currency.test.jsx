import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import AdrRevparSection from '../AdrRevparSection';

describe('AdrRevparSection currency handling', () => {
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
