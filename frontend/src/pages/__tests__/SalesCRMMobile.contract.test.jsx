import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('axios', () => ({ default: { get } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));
vi.mock('@/components/PropertySwitcher', () => ({ default: () => null }));

import SalesCRMMobile from '@/pages/SalesCRMMobile';

describe('SalesCRMMobile provider data contract', () => {
  beforeEach(() => {
    get.mockReset();
    get.mockImplementation((url) => {
      if (url === '/sales/customers') return Promise.resolve({ data: { customers: [] } });
      if (url === '/sales/leads') {
        return Promise.resolve({
          data: {
            leads: [{ id: 'lead-1', guest_name: 'Test Lead', stage: undefined }],
          },
        });
      }
      if (url === '/sales/ota-pricing') return Promise.resolve({ data: { ota_prices: [] } });
      if (url === '/sales/follow-ups') return Promise.resolve({ data: { follow_ups: [] } });
      return Promise.reject(new Error(`unexpected request: ${url}`));
    });
  });

  afterEach(cleanup);

  it('keeps the leads view usable when optional provider fields are missing', async () => {
    render(
      <MemoryRouter>
        <SalesCRMMobile user={{ name: 'Test Operator' }} />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: "Lead'ler" }));

    expect(await screen.findByText('Test Lead')).toBeInTheDocument();
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
    expect(screen.getByText('Beklenen: ₺0')).toBeInTheDocument();
  });
});
