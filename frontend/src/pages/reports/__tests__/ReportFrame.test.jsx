import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import ReportFrame from '../ReportFrame';

afterEach(() => cleanup());

describe('ReportFrame', () => {
  it('adds printable hotel, period and audit metadata around every report', () => {
    render(
      <ReportFrame
        reportName="Otelde Konaklayanlar"
        reportDate="2026-09-30"
        periodLabel="Seçili gün"
        contract={{
          dataSource: 'Onaylı folyo hareketleri',
          dateScope: 'Seçili iş günü',
          financialScope: 'Tahsilat ayrı tutulur',
          currencyRule: 'Dövizler ayrı gösterilir',
        }}
        refreshedAt="02.10.2026 10:39:00"
        tenant={{ property_name: 'Denizli Oteli' }}
        user={{ full_name: 'Murat Zincir' }}
      >
        <div>Rapor içeriği</div>
      </ReportFrame>,
    );

    expect(screen.getByRole('region', { name: 'Otelde Konaklayanlar raporu' })).toBeInTheDocument();
    expect(screen.getByText('Denizli Oteli')).toBeInTheDocument();
    expect(screen.getByText('Murat Zincir')).toBeInTheDocument();
    expect(screen.getByText('Seçili gün')).toBeInTheDocument();
    expect(screen.getByText('Rapor içeriği')).toBeInTheDocument();
    expect(screen.getByTestId('report-data-contract')).toHaveTextContent('Bu rapor nasıl hesaplanır?');
    expect(screen.getByTestId('report-data-contract')).toHaveTextContent('Onaylı folyo hareketleri');
  });
});
