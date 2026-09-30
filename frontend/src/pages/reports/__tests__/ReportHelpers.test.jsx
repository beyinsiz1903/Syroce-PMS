import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { DollarSign } from 'lucide-react';
import { KPICard } from '../ReportHelpers';

afterEach(() => cleanup());

describe('KPICard currency presentation', () => {
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
