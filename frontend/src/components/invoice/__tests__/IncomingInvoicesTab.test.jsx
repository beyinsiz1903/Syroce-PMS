import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';

import IncomingInvoicesTab from '@/components/invoice/IncomingInvoicesTab';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: () => '' }) }));
vi.mock('@/context/CurrencyContext', () => ({ useCurrency: () => ({ amount: (value) => String(value) }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe('IncomingInvoicesTab API contract', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.get.mockResolvedValue({ data: { items: [] } });
    axios.post.mockResolvedValue({ data: { invoices_created: 0 } });
  });

  it('uses paths relative to the shared /api axios base URL', async () => {
    render(<IncomingInvoicesTab />);

    await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/integrations/incoming-invoices?limit=100'));
    expect(axios.get).not.toHaveBeenCalledWith(expect.stringMatching(/^\/api\//));

    fireEvent.click(screen.getByRole('button', { name: 'Eşitle (Sync)' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/integrations/incoming-invoices/sync', {}));
  });
});
