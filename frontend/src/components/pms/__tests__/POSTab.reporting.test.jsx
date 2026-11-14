import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import POSTab from '../POSTab';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
const { translation } = vi.hoisted(() => ({ translation: { t: key => key, i18n: { language: 'tr' } } }));
vi.mock('react-i18next', () => ({ useTranslation: () => translation }));

describe('front-office POS business-day and currency scope', () => {
  it('labels merged checks as history and displays the tax-inclusive order total', async () => {
    axios.get.mockImplementation(url => Promise.resolve({ data: url.includes('outlet-sales') ? {
      total_sales: 132, total_sales_by_currency: { TRY: 132 }, orders_by_currency: { TRY: 1 }, outlets: { restaurant: { orders: 1 } },
    } : url.includes('order-history') ? { orders: [
      { id: 'target', order_number: 'TARGET', status: 'completed', currency: 'TRY', total_amount: 120, grand_total: 132 },
      { id: 'source', order_number: 'SOURCE', status: 'merged', currency: 'TRY', total_amount: 80, grand_total: 88 },
      { id: 'unknown', order_number: 'UNKNOWN', status: 'unexpected', currency: 'TRY', total_amount: 5 },
    ] } : { orders: [] } }));
    render(<MemoryRouter><POSTab businessDate="2026-11-10" /></MemoryRouter>);
    expect(await screen.findByText('Birleştirildi')).toBeInTheDocument();
    expect(screen.getByText('Satış toplamına tekrar eklenmez.')).toBeInTheDocument();
    expect(screen.getByText('Durum doğrulanamadı')).toBeInTheDocument();
    expect(screen.queryByText(/120,00/)).not.toBeInTheDocument();
    expect(screen.getByText(/88,00/)).toBeInTheDocument();
  });
  it('requests the same accounting day and keeps each currency in its own total and average', async () => {
    axios.get.mockImplementation(url => Promise.resolve({ data: url.includes('outlet-sales') ? {
      total_sales: null, total_sales_by_currency: { TRY: 200, USD: 100 }, orders_by_currency: { TRY: 2, USD: 1 }, outlets: { bar: { orders: 3 } },
    } : { orders: [] } }));
    render(<MemoryRouter><POSTab businessDate="2026-10-26" /></MemoryRouter>);
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/pos/mobile/order-history?start_date=2026-10-26&end_date=2026-10-26&limit=20'));
    expect(axios.get).toHaveBeenCalledWith('/pos/outlet-sales-breakdown?start_date=2026-10-26&end_date=2026-10-26');
    expect(await screen.findByText('İş günü: 2026-10-26')).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText(/100,00/).length).toBeGreaterThan(0));
    expect(screen.queryByText(/300,00/)).not.toBeInTheDocument();
  });
});
