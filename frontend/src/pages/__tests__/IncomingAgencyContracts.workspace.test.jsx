import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { apiGet, apiPost, toastSuccess } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  toastSuccess: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    get: (...args) => apiGet(...args),
    post: (...args) => apiPost(...args),
    isCancel: () => false,
  },
}));

vi.mock('sonner', () => ({
  toast: { success: toastSuccess, error: vi.fn() },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'tr' } }),
}));

import IncomingAgencyContracts from '@/pages/IncomingAgencyContracts';

const pendingContract = {
  id: 'contract-1',
  status: 'pending',
  agency_name: 'Atlas Turizm',
  agency_email: 'acente@example.com',
  agency_country: 'TR',
  contract_code: 'SZL-001',
  commission_pct: 12,
  agency_proposed_commission_pct: 12,
  payment_terms: 'net_15',
  valid_from: '2026-09-01',
  valid_to: '2027-08-31',
  currency: 'TRY',
  cancellation_policy: {
    free_until_days_before: 7,
    penalty_pct: 50,
    no_show_penalty_pct: 100,
  },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <IncomingAgencyContracts />
    </MemoryRouter>,
  );
}

describe('IncomingAgencyContracts workspace', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    toastSuccess.mockReset();
  });

  it('explains its B2B scope and renders a pending contract with working approval', async () => {
    apiGet.mockResolvedValue({
      data: {
        contracts: [pendingContract],
        counts: { pending: 1, approved: 2, history: 3 },
      },
    });
    apiPost.mockResolvedValue({ data: { ok: true } });
    const user = userEvent.setup();

    renderPage();

    expect(screen.getByText('B2B iş ortaklığı onay merkezi')).toBeInTheDocument();
    expect(screen.getByText(/HotelRunner kanal bağlantılarını değil/)).toBeInTheDocument();
    expect((await screen.findAllByText('Atlas Turizm')).length).toBeGreaterThan(0);
    expect(screen.getByTestId('agency-contract-summary')).toHaveTextContent(/Karar bekleyen\s*1/);

    await user.click(screen.getByTestId('approve-btn'));
    await user.click(screen.getByTestId('confirm-approve'));

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith(
        '/marketplace/incoming-requests/contract-1/approve',
        { notes: '', commission_pct_override: null },
      );
    });
    expect(toastSuccess).toHaveBeenCalled();
  });

  it('does not present an API failure as an empty inbox', async () => {
    apiGet.mockRejectedValue({ response: { status: 403, data: { detail: 'Bu işlem için yetkiniz yok' } } });

    renderPage();

    expect(await screen.findByTestId('agency-contract-load-error')).toHaveTextContent('Acente talepleri yüklenemedi');
    expect(screen.getByTestId('agency-contract-load-error')).toHaveTextContent('Bu işlem için yetkiniz yok');
    expect(screen.queryByText('Şu an bekleyen acente talebi yok.')).not.toBeInTheDocument();
  });
});
