import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';

import BankReconciliationModule from '../BankReconciliationModule';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('BankReconciliationModule', () => {
  beforeEach(() => {
    axios.get.mockImplementation((url) => {
      if (url === '/banking/transactions') return Promise.resolve({ data: [] });
      if (url === '/banking/open-invoices') return Promise.resolve({ data: [] });
      return Promise.reject(new Error(`unexpected request: ${url}`));
    });
  });

  it('loads durable tenant data and never renders seeded financial examples', async () => {
    render(<BankReconciliationModule />);

    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
    expect(axios.get).toHaveBeenCalledWith('/banking/transactions');
    expect(axios.get).toHaveBeenCalledWith('/banking/open-invoices');
    expect(screen.getByRole('button', { name: /yenile/i })).toBeInTheDocument();
    expect(screen.queryByText(/simülasyon/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/booking\.com/i)).not.toBeInTheDocument();
  });
});
