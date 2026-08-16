import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('axios', () => ({ default: { get } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));

import MobileFinance from '@/pages/MobileFinance';

describe('MobileFinance modal contract', () => {
  beforeEach(() => {
    get.mockReset();
    get.mockImplementation((url) => {
      if (url === '/finance/mobile/daily-collections') {
        return Promise.resolve({ data: { total_collected: 0, payment_count: 0 } });
      }
      if (url === '/finance/mobile/monthly-collections') {
        return Promise.resolve({ data: { total_collected: 0, collection_rate: 0 } });
      }
      if (url === '/finance/mobile/pending-receivables') {
        return Promise.resolve({ data: { total_pending: 0, receivables_count: 0, receivables: [] } });
      }
      if (url === '/finance/mobile/monthly-costs') {
        return Promise.resolve({ data: { total_costs: 0 } });
      }
      if (url === '/notifications/mobile/finance') {
        return Promise.resolve({ data: { notifications: [] } });
      }
      if (url === '/accounting/invoices') {
        return Promise.resolve({ data: { invoices: [] } });
      }
      if (url === '/finance/mobile/cash-flow-summary') {
        return Promise.resolve({ data: null });
      }
      if (url === '/finance/mobile/risk-alerts') {
        return Promise.resolve({
          data: {
            summary: { total_alerts: 1 },
            alerts: [{ id: 'risk-1', severity: 'high', title: 'Risk', message: 'Review' }],
          },
        });
      }
      if (url === '/finance/mobile/daily-expenses') {
        return Promise.resolve({ data: null });
      }
      if (url === '/finance/mobile/bank-balances') {
        return Promise.resolve({ data: null });
      }
      return Promise.reject(new Error(`unexpected request: ${url}`));
    });
  });

  afterEach(cleanup);

  it('renders provider risk data without an undefined modal helper crash', async () => {
    render(
      <MemoryRouter>
        <MobileFinance user={{ name: 'Test Operator' }} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(get).toHaveBeenCalledTimes(10));
    expect(await screen.findByText('Risk Yönetimi')).toBeInTheDocument();
    expect(screen.getByText('Review')).toBeInTheDocument();
  });
});
