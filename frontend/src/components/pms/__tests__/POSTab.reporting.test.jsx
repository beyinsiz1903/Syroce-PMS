import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import POSTab from '../POSTab';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key, i18n: { language: 'tr' } }) }));

describe('front-office POS business-day and currency scope', () => {
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
