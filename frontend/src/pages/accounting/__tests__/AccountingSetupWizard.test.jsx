import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { AccountingSetupWizard } from '@/pages/accounting/AccountingSetupWizard';

vi.mock('axios');

const setupState = {
  profile: null,
  checks: [
    { code: 'legal_profile', label: 'Yasal şirket ve vergi bilgileri', ready: false, required: true },
    { code: 'opening_balance', label: 'Açılış bakiyesi taslağı', ready: true, required: false },
  ],
  blockers: [{ code: 'legal_profile' }],
  ready: false,
  account_count: 0,
  period_count: 0,
  operational_mapping: { enabled: false },
  opening_balance_voucher: null,
};

describe('AccountingSetupWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.get.mockResolvedValue({ data: setupState });
  });

  it('starts with tenant legal identity and explains tenant isolation', async () => {
    render(<AccountingSetupWizard />);
    await waitFor(() => expect(screen.getByText('Otel Muhasebe Kurulumu')).toBeInTheDocument());
    expect(screen.getByText(/Her otelin vergi kimliği/)).toBeInTheDocument();
    expect(screen.getByText('Yasal unvan')).toBeInTheDocument();
    expect(screen.getByText('VKN / TCKN')).toBeInTheDocument();
  });
});
