import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import RoomTypesSection from '../RoomTypesSection';
import { ChannelsSection } from '../ChannelsSection';
import { DepartmentsSection, HousekeepingSection, PaymentsSection } from '../OperationsSection';

vi.mock('recharts', () => {
  const Container = ({ children }) => <div>{children}</div>;
  const Empty = () => null;
  return { BarChart: Container, PieChart: Container, ResponsiveContainer: Container, Pie: Container,
    Bar: Empty, Cell: Empty, XAxis: Empty, YAxis: Empty, Tooltip: Empty, Legend: Empty, CartesianGrid: Empty };
});
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
afterEach(cleanup);

describe('Operational report breakdown semantics', () => {
  it('preserves retired/unassigned revenue without inventing current rooms or a per-room ratio', () => {
    render(<RoomTypesSection roomTypeData={[
      { name: 'Eski süit', total: 0, occupied: 0, occupancy: 0, revenue: 80, revenueByCurrency: { EUR: 80 } },
      { name: 'Eşleştirilmemiş', total: 0, occupied: 0, occupancy: 0, revenue: -5, revenueByCurrency: { USD: -5 } },
    ]} />);
    const table = screen.getByTestId('room-type-table');
    expect(table).toHaveClass('min-w-[760px]');
    expect(screen.getByText(/ADR veya RevPAR değildir/)).toBeInTheDocument();
    expect(within(table).getByText(/€80/)).toBeInTheDocument();
    expect(within(table).getByText(/\$-?5|-\$5/)).toBeInTheDocument();
    for (const row of within(table).getAllByRole('row').slice(1)) {
      expect(within(row).getAllByRole('cell').at(-1)).toHaveTextContent('-');
    }
  });

  it('shows unmatched POS money without reporting an average booking amount', () => {
    render(<ChannelsSection sourceData={[{ name: 'Rezervasyonla eşleştirilmemiş', count: 0, revenue: 30, revenueByCurrency: { EUR: 30 } }]} />);
    const table = screen.getByTestId('channel-table');
    expect(within(table).getByText(/€30/)).toBeInTheDocument();
    expect(within(table).getAllByRole('cell').at(-1)).toHaveTextContent('-');
    expect(screen.getByText(/rezervasyon adedi üretmez/)).toBeInTheDocument();
  });

  it('distinguishes current invoice counts from issue-period paid documents and collections', () => {
    render(<DepartmentsSection s={{}} hk={{}} maint={{ completed_month: 2 }} finance={{ pending_invoices: 3, paid_invoices_month: 4 }} />);
    expect(screen.getByText('Dönemde Tamamlanan')).toBeInTheDocument();
    expect(screen.getByText('Güncel Bekleyen')).toBeInTheDocument();
    expect(screen.getByText('Dönemde Düzenlenen, Ödenmiş')).toBeInTheDocument();
    expect(screen.getByText(/dönemin tahsilatı değildir/)).toBeInTheDocument();
  });

  it('labels the payment report invoice count as current rather than a selected-day value', () => {
    render(<PaymentsSection payments={{ total_pending: 3, rows: [] }} paymentData={[]} reportDate="2026-10-07" />);
    expect(screen.getByText('Güncel Bekleyen Fatura')).toBeInTheDocument();
    expect(screen.getByText(/Tarih filtresinden bağımsız/)).toBeInTheDocument();
  });

  it('states that housekeeping selects the latest relevant task per room, not every task', () => {
    render(<HousekeepingSection hk={{ rows: [] }} reportDate="2026-10-07" />);
    expect(screen.getByText(/oda başına son ilgili görev gösterilir/)).toBeInTheDocument();
  });
});
