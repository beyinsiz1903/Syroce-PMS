import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';

import FnBCostingModule from '../FnBCostingModule';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('FnBCostingModule durable data contract', () => {
  beforeEach(() => {
    axios.get.mockImplementation((url) => {
      if (url === '/fnb-cost/variance') {
        return Promise.resolve({
          data: {
            period: { start: '2026-08-07', end: '2026-08-13' },
            rows: [],
            totals: { theoretical_cost: 0, actual_cost: 0, variance_cost: 0 },
          },
        });
      }
      if (url === '/fnb-cost/recipes') {
        return Promise.resolve({ data: { recipes: [] } });
      }
      return Promise.reject(new Error(`unexpected request: ${url}`));
    });
  });

  it('loads real variance and recipe endpoints instead of seeded sample data', async () => {
    render(<FnBCostingModule />);

    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
    expect(axios.get).toHaveBeenCalledWith('/fnb-cost/variance', {
      params: expect.objectContaining({ start: expect.any(String), end: expect.any(String) }),
    });
    expect(axios.get).toHaveBeenCalledWith('/fnb-cost/recipes');
    fireEvent.click(screen.getByRole('button', { name: /ürün reçeteleri/i }));
    expect(screen.getByText('Kayıtlı reçete bulunamadı.')).toBeInTheDocument();
    expect(screen.queryByText(/cheeseburger/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/dana kıyma/i)).not.toBeInTheDocument();
  });
});
