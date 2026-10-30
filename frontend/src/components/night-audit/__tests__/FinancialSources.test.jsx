import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Tabs } from '@/components/ui/tabs';
import FinancialTab from '../tabs/FinancialTab';
import ReportTab from '../tabs/ReportTab';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
afterEach(cleanup);

it('makes incomplete tax/source data visible and does not call mixed currency balanced', () => {
  render(<Tabs value="financial"><FinancialTab categoryLabels={{}} paymentMethodLabels={{}}
    StatCard={({ value, subValue }) => <div>{value}<span>{subValue}</span></div>}
    financialSummary={{ business_date: '2026-10-30', degraded: true, tax_unknown_count: 3,
      revenue: { total: null, total_by_currency: { TRY: 75, EUR: 10 }, by_category: {} },
      payments: {}, open_folios: {}, net_position: null, net_position_by_currency: { TRY: 15, EUR: 10 } }} /></Tabs>);
  expect(screen.getByRole('alert')).toHaveTextContent('3 kalemin vergi ayrımı eksik');
  expect(screen.getByRole('alert')).toHaveTextContent('kesin mutabakat yapmayın');
  expect(screen.getByText('Para birimi bazında değerlendirin')).toBeInTheDocument();
  expect(screen.queryByText('Dengeli')).not.toBeInTheDocument();
});

it('warns before interpreting an incomplete range report', () => {
  render(<Tabs value="report"><ReportTab categoryLabels={{}} paymentMethodLabels={{}} reportDates={{start: '2026-10-30', end: '2026-10-30'}}
    financialReport={{ tax_unknown_count: 2, summary: {} }} /></Tabs>);
  expect(screen.getByRole('alert')).toHaveTextContent('2 kalemin vergi ayrımı eksik');
});

it('warns when aggregate tax is known but its component split is not', () => {
  render(<Tabs value="financial"><FinancialTab categoryLabels={{}} paymentMethodLabels={{}}
    StatCard={({ value }) => <div>{value}</div>}
    financialSummary={{ tax_unknown_count: 0, tax_breakdown_incomplete_count: 1, revenue: {}, payments: {},
      open_folios: { balance: { total: null }, balance_by_currency: {
        TRY: { total: 100 }, USD: { total: -100 },
      } } }} /></Tabs>);
  expect(screen.getByRole('alert')).toHaveTextContent('1 kalemde vergi türü ayrımı eksik');
  expect(screen.getByRole('alert')).toHaveTextContent('payları tahmin edilmez');
  expect(screen.getByTestId('open-folios-card')).toHaveTextContent('TRY');
  expect(screen.getByTestId('open-folios-card')).toHaveTextContent('USD');
});
