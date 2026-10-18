import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { DollarSign } from 'lucide-react';
import { formatCurrency, KPICard } from '../ReportHelpers';

afterEach(() => cleanup());

describe('KPICard currency presentation', () => {
  it('does not hide cents on financial report values', () => {
    expect(formatCurrency(1000.49, 'TRY')).toContain('1.000,49');
    expect(formatCurrency(25.75, 'EUR')).toContain('25,75');
  });
  it('labels mixed currencies separately and explains that they are not converted', () => {
    render(
      <KPICard
        title="Toplam Gelir (30 Gün)"
        value={671076.48}
        currencyBreakdown={{ EUR: 635.48, TRY: 670441 }}
        icon={DollarSign}
      />,
    );

    expect(screen.getByTestId('currency-breakdown')).toBeInTheDocument();
    expect(screen.getByText('EUR')).toBeInTheDocument();
    expect(screen.getByText('TRY')).toBeInTheDocument();
    expect(screen.getByText('Ayrı para birimleridir; kur dönüşümü yapılmamıştır.')).toBeInTheDocument();
  });

  it('keeps a single currency compact', () => {
    render(
      <KPICard
        title="Toplam Gelir"
        value={1000}
        currencyBreakdown={{ TRY: 1000 }}
        icon={DollarSign}
      />,
    );

    expect(screen.queryByTestId('currency-breakdown')).not.toBeInTheDocument();
    expect(screen.queryByText('Ayrı para birimleridir; kur dönüşümü yapılmamıştır.')).not.toBeInTheDocument();
  });
});
